"""Højde customer portal API (/api/hojde/portal): scope, the order flow, quotes, cancelling, access, the organisation
and invitations. Runs against the demo tenant from app.hojde.seed."""

from datetime import datetime, timedelta, timezone

import pytest

from app import db
from app.hojde import invitations, seed
from tests.helpers import SoftAuthenticator, register_passkey, stepup
from tests.test_hojde import email_login


@pytest.fixture
async def tenant():
    async with db.connection() as conn:
        await seed.seed(conn)


@pytest.fixture
def login(make_client):
    """A customer signed in with a code and a passkey proven in the session (Kystparken requires 2FA)."""
    async def factory(email: str):
        client = make_client()
        await email_login(client, email)
        authenticator = SoftAuthenticator()
        await register_passkey(client, authenticator)
        assert (await stepup(client, authenticator)).status_code == 200
        return client
    return factory


def order_id(conn, number: str) -> int:
    return conn.execute("select id from hojde_orders where number = %s", (number,)).fetchone()[0]


def location_id(conn, name: str) -> int:
    return conn.execute("select id from hojde_locations where name = %s", (name,)).fetchone()[0]


ORDER = {"contact_name": "Jens Pedersen", "preferred_from": "2099-01-05", "preferred_to": "2099-01-20"}


async def test_the_organisations_2fa_policy_guards_the_portal(tenant, make_client, login):
    first = make_client()
    await email_login(first, "niels@example.com")
    mette = make_client()
    await email_login(mette, "mh@kystparken.example")
    r = await mette.get("/api/hojde/portal/overview")
    assert r.status_code == 403 and r.headers["X-Gaer-Error"] == "mfa_setup_required"
    mette = await login("mh@kystparken.example")
    assert (await mette.get("/api/hojde/portal/overview")).status_code == 200
    staff = make_client()
    await email_login(staff, "emil@hojde.example")
    r = await staff.get("/api/hojde/portal/overview")
    assert r.status_code == 403 and r.json()["detail"] == "Du er ikke tilknyttet en kundeorganisation"


async def test_overview_shows_stats_and_what_waits_on_the_customer(tenant, login):
    mette = await login("mh@kystparken.example")
    body = (await mette.get("/api/hojde/portal/overview")).json()
    assert body["first_name"] == "Mette" and body["can_order"] is True
    assert body["stats"]["locations"] == 5
    assert body["stats"]["critical_findings"] == 1                # the 9 awaiting review are not shown
    assert body["open_findings"] == {"kritisk": 1, "moderat": 6, "lav": 9}
    kinds = {(a["kind"], a["text"].split(" ")[0]) for a in body["actions"]}
    assert ("approve_quote", "Tilbud") in kinds and ("confirm_access", "Bekræft") in kinds
    assert [d["label"] for d in body["deliveries"]] == ["Inspektion", "3D-model", "Inspektion"]
    assert {o["number"] for o in body["upcoming"]} == {"B-1042", "B-1043"}


async def test_limited_users_see_only_their_locations(tenant, login, owner_conn):
    jens = await login("jp@kystparken.example")
    items = (await jens.get("/api/hojde/portal/locations")).json()["items"]
    assert sorted(i["name"] for i in items) == ["Kystparken blok A", "Kystparken blok B", "Kystparken blok C"]
    assert items[0]["name"] == "Kystparken blok C"                # most critical findings first
    assert items[0]["open_findings"] == {"kritisk": 1, "moderat": 4, "lav": 4}
    assert (await jens.get(f"/api/hojde/portal/locations/{location_id(owner_conn, 'Strandvejen 8')}")).status_code == 404
    numbers = {o["number"] for o in (await jens.get("/api/hojde/portal/orders")).json()["past"]}
    assert "B-1032" not in numbers and "B-1039" in numbers
    search = (await jens.get("/api/hojde/portal/locations?q=blok%20b&type=bygning")).json()
    assert [i["name"] for i in search["items"]] == ["Kystparken blok B"] and search["total"] == 3
    # Another organisation's order is not there at all.
    assert (await jens.post(f"/api/hojde/portal/orders/{order_id(owner_conn, 'B-1018')}/approve")).status_code == 404


async def test_location_detail_has_visits_findings_and_orders(tenant, login, owner_conn):
    mette = await login("mh@kystparken.example")
    body = (await mette.get(f"/api/hojde/portal/locations/{location_id(owner_conn, 'Kystparken blok C')}")).json()
    assert body["location"]["contact_name"] == "Jens Pedersen, vicevært"
    assert [v["service"] for v in body["visits"]] == ["Bygningsinspektion", "Besøg"]
    assert body["visits"][0]["findings"] == 9 and body["first_visit"] == body["visits"][-1]["date"]
    assert len(body["findings"]) == 10 and all("approved_by" not in f for f in body["findings"])
    assert [o["number"] for o in body["orders"]] == ["B-1039"]


async def test_ordering_with_a_new_location(tenant, login, owner_conn):
    mette = await login("mh@kystparken.example")
    service = owner_conn.execute("select id from hojde_services where key = 'bygningsinspektion'").fetchone()[0]
    new_location = {"name": "Kystparken blok D", "type": "bygning", "address": "Strandvejen 16, 2900 Hellerup"}
    r = await mette.post("/api/hojde/portal/orders", json={**ORDER, "service_id": service, "new_location": new_location,
                                                          "subject": "tag"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["number"] == "B-1049" and body["status"] == "afventer_godkendelse"
    assert body["location"]["name"] == "Kystparken blok D" and body["can_cancel"] is True
    logged = owner_conn.execute("""select table_name from audit_log where action = 'create'
                                   and table_name in ('hojde_orders', 'hojde_locations') order by id""").fetchall()
    assert logged[-2:] == [("hojde_locations",), ("hojde_orders",)]

    both = {**ORDER, "service_id": service, "new_location": new_location, "location_id": 1}
    assert (await mette.post("/api/hojde/portal/orders", json=both)).status_code == 422
    sub = {**ORDER, "service_id": service, "location_id": body["location"]["id"], "frequency": "abonnement"}
    assert (await mette.post("/api/hojde/portal/orders", json=sub)).status_code == 422
    past = {**ORDER, "service_id": service, "location_id": body["location"]["id"], "preferred_from": "2020-01-01"}
    assert (await mette.post("/api/hojde/portal/orders", json=past)).json()["detail"] == "Tidligst kan ikke ligge før i dag"

    lars = await login("lk@tagfirma.example")                      # may not order
    r = await lars.post("/api/hojde/portal/orders", json={**ORDER, "service_id": service,
                                                         "location_id": location_id(owner_conn, "Kystparken blok C")})
    assert r.status_code == 403 and r.json()["detail"] == "Din bruger må ikke bestille opgaver"


async def test_approving_a_quote(tenant, login, owner_conn):
    mette = await login("mh@kystparken.example")
    oid = order_id(owner_conn, "B-1047")
    r = await mette.post(f"/api/hojde/portal/orders/{oid}/approve")
    assert r.status_code == 200 and r.json()["status"] == "godkendt"
    member = owner_conn.execute("select id from hojde_members where email = 'mh@kystparken.example'").fetchone()[0]
    assert owner_conn.execute("select quote_approved_by from hojde_orders where id = %s", (oid,)).fetchone()[0] == member
    assert (await mette.post(f"/api/hojde/portal/orders/{oid}/approve")).status_code == 409


async def test_cancelling_until_24_hours_before(tenant, login, owner_conn):
    mette = await login("mh@kystparken.example")
    later = order_id(owner_conn, "B-1043")                          # planned in 8 days
    r = await mette.post(f"/api/hojde/portal/orders/{later}/cancel")
    assert r.status_code == 200 and r.json()["status"] == "aflyst"
    assert owner_conn.execute("select count(*) from hojde_tasks where order_id = %s", (later,)).fetchone()[0] == 0
    soon = order_id(owner_conn, "B-1042")
    owner_conn.execute("update hojde_orders set scheduled_at = %s where id = %s",
                       (datetime.now(timezone.utc) + timedelta(hours=2), soon))
    r = await mette.post(f"/api/hojde/portal/orders/{soon}/cancel")
    assert r.status_code == 409 and "24 timer" in r.json()["detail"]


async def test_confirming_access_ticks_the_checklist(tenant, login, owner_conn):
    jens = await login("jp@kystparken.example")
    oid = order_id(owner_conn, "B-1042")
    r = await jens.post(f"/api/hojde/portal/orders/{oid}/confirm-access")
    assert r.status_code == 200 and r.json()["access_confirmed_at"]
    item = owner_conn.execute("""select c.done_at is not null, m.email from hojde_checklist_items c
                                 join hojde_tasks t on t.id = c.task_id join hojde_members m on m.id = c.done_by
                                 where t.order_id = %s and c.key = 'access'""", (oid,)).fetchone()
    assert item == (True, "jp@kystparken.example")
    body = (await jens.get("/api/hojde/portal/overview")).json()
    assert not any(a["kind"] == "confirm_access" and a["order_id"] == oid for a in body["actions"])


async def test_organisation_users_and_invitations(tenant, login, owner_conn, capsys):
    jens = await login("jp@kystparken.example")
    r = await jens.get("/api/hojde/portal/organization")
    assert r.status_code == 403 and r.json()["detail"] == "Kun for kundeadministratorer"

    mette = await login("mh@kystparken.example")
    body = (await mette.get("/api/hojde/portal/organization")).json()
    by_email = {m["email"]: m for m in body["members"]}
    assert by_email["mh@kystparken.example"]["is_me"] and by_email["mh@kystparken.example"]["two_factor"] is True
    assert by_email["jp@kystparken.example"]["location_names"] == ["Kystparken blok A", "Kystparken blok B",
                                                                   "Kystparken blok C"]
    assert by_email["sb@kystparken.example"]["invitation_expires_at"] and by_email["sb@kystparken.example"]["two_factor"] is None

    blok_c = location_id(owner_conn, "Kystparken blok C")
    r = await mette.post("/api/hojde/portal/organization/invitations",
                         json={"email": " Ny@Firma.DK ", "role": "kundebruger", "location_scope": "udvalgte",
                               "location_ids": [blok_c], "may_order": True})
    assert r.status_code == 201, r.text
    new = next(m for m in r.json()["members"] if m["email"] == "ny@firma.dk")
    assert new["status"] == "inviteret" and new["name"] == "ny" and new["location_names"] == ["Kystparken blok C"]
    job = owner_conn.execute("select payload from jobs where kind = 'hojde.invitation.mail'").fetchone()[0]
    assert job == {"member_id": new["id"]}
    assert await invitations.send_invitation(job, {}) == {"sent": True}
    out = capsys.readouterr().out
    assert "subject=Invitation til Boligforeningen Kystparken på Højde" in out and "Mette Holm har inviteret dig" in out

    again = await mette.post("/api/hojde/portal/organization/invitations",
                             json={"email": "ny@firma.dk", "role": "kundebruger"})
    assert again.status_code == 409
    foreign = location_id(owner_conn, "Nordhavn byggefelt 7")
    r = await mette.post("/api/hojde/portal/organization/invitations",
                         json={"email": "x@firma.dk", "role": "kundebruger", "location_scope": "udvalgte",
                               "location_ids": [foreign]})
    assert r.status_code == 422

    me_id = by_email["mh@kystparken.example"]["id"]
    assert (await mette.post(f"/api/hojde/portal/organization/members/{me_id}/deactivate")).status_code == 409
    jens_id = by_email["jp@kystparken.example"]["id"]
    r = await mette.post(f"/api/hojde/portal/organization/members/{jens_id}/deactivate")
    assert r.status_code == 200
    r = await jens.get("/api/hojde/portal/overview")
    assert r.status_code == 403
    r = await mette.post(f"/api/hojde/portal/organization/members/{jens_id}/reactivate")
    assert next(m for m in r.json()["members"] if m["id"] == jens_id)["status"] == "aktiv"
    assert (await jens.get("/api/hojde/portal/overview")).status_code == 200


async def test_organisation_settings_and_2fa_switch(tenant, login, make_client, owner_conn):
    mette = await login("mh@kystparken.example")
    r = await mette.patch("/api/hojde/portal/organization", json={"cvr": "12345678", "ean": "", "require_2fa": False})
    assert r.status_code == 200, r.text
    org = r.json()["organization"]
    assert org["cvr"] == "12345678" and org["ean"] is None and org["require_2fa"] is False
    logged = owner_conn.execute("""select before, after from audit_log where table_name = 'hojde_organizations'""").fetchone()
    assert logged == ({"cvr": None, "require_2fa": True}, {"cvr": "12345678", "require_2fa": False})
    assert (await mette.patch("/api/hojde/portal/organization", json={"cvr": "12"})).status_code == 422

    # Without the 2FA policy, a customer admin who has no second factor can still use the portal, but may not
    # switch the policy on: they would lock themselves out.
    owner_conn.execute("delete from passkeys")
    plain = make_client()
    await email_login(plain, "mh@kystparken.example")
    assert (await plain.get("/api/hojde/portal/overview")).status_code == 200
    r = await plain.patch("/api/hojde/portal/organization", json={"require_2fa": True})
    assert r.status_code == 409
