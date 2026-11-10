"""Højde, phase 1: the schema, the demo seed, memberships linked at first login, the access guards with their second
factor, planning an order, the weather rule and GDPR. The rules themselves are in test_hojde_rules.py."""

import dataclasses
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app import config, db, gdpr
from app.hojde import access, admin, ops, rules, seed
from app.logs import RequestMeta
from app.sessions import Principal
from tests.helpers import SoftAuthenticator, register_passkey, stepup


async def email_login(client, email: str) -> dict:
    r = await client.post("/api/auth/otp/start", json={"email": email})
    assert r.status_code == 200, r.text
    r = await client.post("/api/auth/otp/verify", json={"email": email, "code": r.json()["dev_code"]})
    assert r.status_code == 200, r.text
    return r.json()


async def seeded(today=None) -> dict:
    async with db.connection() as conn:
        return await seed.seed(conn, today)


async def me(client) -> dict:
    r = await client.get("/api/hojde/me")
    assert r.status_code == 200, r.text
    return r.json()


def member_row(conn, email):
    return conn.execute("select id, user_id, status, name, email, anonymised_at from hojde_members where email = %s",
                        (email,)).fetchone()


# ── Seed ────────────────────────────────────────────────────────────────────────────────────────────────────────────

async def test_seed_builds_the_demo_tenant_and_can_run_again(owner_conn):
    first = await seeded()
    again = await seeded()
    assert first["counts"] == again["counts"]
    c = again["counts"]
    assert (c["hojde_organizations"], c["hojde_members"], c["hojde_locations"], c["hojde_services"]) == (4, 8, 8, 5)
    assert (c["hojde_orders"], c["hojde_flights"], c["hojde_equipment"]) == (11, 3, 8)
    numbers = [r[0] for r in owner_conn.execute("select number from hojde_tasks order by number").fetchall()]
    assert len(numbers) == len(set(numbers)) == c["hojde_tasks"] == 12
    # Nordhavn lies in a restricted zone: its checklist has the zone permit; access was confirmed by the customer.
    items = owner_conn.execute("""
        select c.key, c.done_at is not null, c.done_by from hojde_checklist_items c
        join hojde_tasks t on t.id = c.task_id join hojde_orders o on o.id = t.order_id
        where o.number = 'B-1043' order by c.sort""").fetchall()
    assert [i[0] for i in items] == ["risk", "batteries", "access", "route", "cordon"]
    assert items[2][1:] == (True, None)
    zone = owner_conn.execute("""select count(*) from hojde_checklist_items c join hojde_tasks t on t.id = c.task_id
                                 join hojde_locations l on l.id = t.location_id
                                 where l.restricted_zone and c.key = 'zone_permit'""").fetchone()[0]
    assert zone == 4
    # Names live only in hojde_members: certificates and flights point at the member.
    assert owner_conn.execute("select count(*) from hojde_compliance_documents where title like '%Emil%'").fetchone()[0] == 0
    audit = owner_conn.execute("select detail from audit_log where detail->>'via' = 'hojde.seed' order by id").fetchall()
    assert len(audit) == 2 and audit[1][0]["counts"]["hojde_members"] == 8


async def test_seed_puts_tomorrows_blok_b_flight_on_weather_hold(owner_conn):
    today = datetime.now(rules.TIME_ZONE).date()
    await seeded(today)
    status = owner_conn.execute("""select t.status, o.status from hojde_tasks t join hojde_orders o on o.id = t.order_id
                                   where o.number = 'B-1042'""").fetchone()
    assert status == ("vejrforbehold", "vejrforbehold")
    holds = owner_conn.execute("""select count(*) from audit_log where table_name = 'hojde_tasks'
                                  and detail->>'via' = 'weather_rule'""").fetchone()[0]
    assert holds >= 1


async def test_seed_refuses_in_production(monkeypatch, capsys):
    monkeypatch.setattr(config, "settings", dataclasses.replace(config.settings, environment="production"))
    assert await seed._main() == 1
    assert "produktion" in capsys.readouterr().out


# ── Memberships and first login ─────────────────────────────────────────────────────────────────────────────────────

async def test_staff_and_customer_are_linked_at_first_login(make_client, owner_conn):
    await seeded()
    await email_login(make_client(), "niels@example.com")  # the first user becomes the Gær super admin
    emil, mette = make_client(), make_client()
    await email_login(emil, "Emil@hojde.example")
    await email_login(mette, "mh@kystparken.example")

    body = await me(emil)
    assert body["landing"] == "/backoffice" and body["customer"] is None
    assert body["staff"]["roles"] == ["administrator", "analytiker", "pilot"]
    assert body["staff"]["role_labels"] == ["Administrator", "Analytiker", "Pilot"]
    assert body["mfa"] == {"required": True, "has_factor": False, "proven": False}

    body = await me(mette)
    assert body["landing"] == "/portal" and body["staff"] is None
    assert body["customer"]["org_name"] == "Boligforeningen Kystparken"
    assert body["customer"]["can_manage_organization"] is True and body["customer"]["require_2fa"] is True
    assert body["mfa"]["required"] is True

    row = member_row(owner_conn, "emil@hojde.example")
    user_id = owner_conn.execute("select id from users where email = 'emil@hojde.example'").fetchone()[0]
    assert row[1] == user_id and row[2] == "aktiv"
    logged = owner_conn.execute("""select actor_user_id, before, after, detail->>'via' from audit_log
                                   where table_name = 'hojde_members' and row_id = %s""", (str(row[0]),)).fetchall()
    assert logged == [(user_id, {"user_id": None, "status": "aktiv"}, {"user_id": user_id, "status": "aktiv"},
                       "first_login")]
    await me(emil)  # linked once: no second audit entry
    assert owner_conn.execute("select count(*) from audit_log where table_name = 'hojde_members' and row_id = %s",
                              (str(row[0]),)).fetchone()[0] == 1


async def test_invitations_link_within_7_days_and_deactivated_members_never(make_client, owner_conn):
    await seeded()
    sofie = make_client()
    await email_login(sofie, "sb@kystparken.example")      # invited yesterday
    assert (await me(sofie))["landing"] == "/portal"
    assert member_row(owner_conn, "sb@kystparken.example")[2] == "aktiv"

    owner_conn.execute("""insert into hojde_members (email, name, kind, org_id, roles, status, invitation_sent_at)
                          select 'late@example.com', 'Sen', 'customer', id, '{kundebruger}', 'inviteret',
                                 now() - interval '8 days' from hojde_organizations where name = 'Demo Ejendomme'""")
    late = make_client()
    await email_login(late, "late@example.com")
    assert (await me(late))["landing"] is None
    assert member_row(owner_conn, "late@example.com")[1:3] == (None, "inviteret")

    peter = make_client()
    await email_login(peter, "pl@kystparken.example")      # deaktiveret
    body = await me(peter)
    assert body["landing"] is None and body["mfa"]["required"] is False
    assert member_row(owner_conn, "pl@kystparken.example")[1] is None


async def test_people_without_a_membership_get_nothing(make_client):
    await seeded()
    client = make_client()
    await email_login(client, "stranger@example.com")
    assert await me(client) == {"staff": None, "customer": None, "customers": [], "landing": None,
                                "mfa": {"required": False, "has_factor": False, "proven": False}}
    assert (await make_client().get("/api/hojde/me")).status_code == 401


async def test_x_hojde_org_picks_only_among_own_organisations(make_client, owner_conn):
    await seeded()
    orgs = dict(owner_conn.execute("select name, id from hojde_organizations").fetchall())
    owner_conn.execute("""insert into hojde_members (email, name, kind, org_id, roles)
                          values ('mh@kystparken.example', 'Mette Holm', 'customer', %s, '{kundebruger}')""",
                       (orgs["Demo Ejendomme"],))
    mette = make_client()
    await email_login(mette, "mh@kystparken.example")
    assert [c["org_name"] for c in (await me(mette))["customers"]] == ["Boligforeningen Kystparken", "Demo Ejendomme"]
    r = await mette.get("/api/hojde/me", headers={"x-hojde-org": str(orgs["Demo Ejendomme"])})
    assert r.json()["customer"]["org_name"] == "Demo Ejendomme" and r.json()["mfa"]["required"] is False
    r = await mette.get("/api/hojde/me", headers={"x-hojde-org": str(orgs["Demo Grusgrav"])})
    assert r.json()["customer"]["org_name"] == "Boligforeningen Kystparken"


async def test_staff_need_a_second_factor_proven_in_the_session(make_client):
    await seeded()
    emil = make_client()
    await email_login(emil, "emil@hojde.example")
    authenticator = SoftAuthenticator()
    await register_passkey(emil, authenticator)
    assert (await me(emil))["mfa"]["has_factor"] is True
    r = await stepup(emil, authenticator)
    assert r.status_code == 200, r.text
    assert (await me(emil))["mfa"] == {"required": True, "has_factor": True, "proven": True}


# ── Guards ──────────────────────────────────────────────────────────────────────────────────────────────────────────

def principal(mfa_at=None) -> Principal:
    return Principal(session_id=1, user_id=1, email="x@example.com", phone=None, role="user", scope="full",
                     display_name=None, meta=RequestMeta(), mfa_at=mfa_at)


def membership(kind="staff", roles=("pilot",), require_2fa=False) -> access.Membership:
    return access.Membership(id=1, kind=kind, org_id=None if kind == "staff" else 1, org_name=None,
                             require_2fa=require_2fa, name="X", email="x@example.com", roles=tuple(roles),
                             location_scope="alle", location_ids=(), may_order=False)


def test_guards_check_membership_role_and_second_factor():
    now = datetime.now(timezone.utc)
    pilot = access.HojdeContext(principal(now), staff=membership(), has_factor=True)
    assert access.staff_of(pilot, "pilot").id == 1
    with pytest.raises(HTTPException) as e:
        access.staff_of(pilot, "analytiker", "kundeansvarlig")
    assert e.value.status_code == 403 and e.value.detail == "Kræver rollen analytiker eller kundeansvarlig"
    boss = access.HojdeContext(principal(now), staff=membership(roles=("administrator",)), has_factor=True)
    assert access.staff_of(boss, "analytiker").id == 1

    with pytest.raises(HTTPException) as e:
        access.staff_of(access.HojdeContext(principal(), staff=membership(), has_factor=False))
    assert e.value.headers["X-Gaer-Error"] == "mfa_setup_required"
    with pytest.raises(HTTPException) as e:
        access.staff_of(access.HojdeContext(principal(), staff=membership(), has_factor=True))
    assert e.value.headers["X-Gaer-Error"] == "stepup_required"

    with pytest.raises(HTTPException) as e:
        access.customer_of(pilot)
    assert e.value.detail == "Du er ikke tilknyttet en kundeorganisation"
    user = membership("customer", ("kundebruger",))
    relaxed = access.HojdeContext(principal(), staff=None, customers=[user], customer=user)
    assert access.customer_of(relaxed) is user                       # no 2FA required by this organisation
    with pytest.raises(HTTPException) as e:
        access.customer_admin_of(relaxed)
    assert e.value.detail == "Kun for kundeadministratorer"
    strict_member = membership("customer", ("kundeadministrator",), require_2fa=True)
    strict = access.HojdeContext(principal(), staff=None, customers=[strict_member], customer=strict_member)
    with pytest.raises(HTTPException):
        access.customer_admin_of(strict)
    with pytest.raises(HTTPException) as e:
        access.staff_of(strict)
    assert e.value.detail == "Kun for Højdes medarbejdere"


async def test_first_staff_member_comes_from_the_cli(make_client, owner_conn):
    async with db.connection() as conn:
        created = await admin.add_staff(conn, " Boss@Hojde.dk ", "Boss", ["administrator"])
        again = await admin.add_staff(conn, "boss@hojde.dk", "Boss", ["administrator", "pilot"])
        with pytest.raises(ValueError):
            await admin.add_staff(conn, "boss@hojde.dk", "Boss", ["kundebruger"])
    assert created["id"] == again["id"] and again["roles"] == ["administrator", "pilot"]
    assert owner_conn.execute("""select action from audit_log where table_name = 'hojde_members'
                                 and detail->>'via' = 'cli' order by id""").fetchall() == [("create",), ("update",)]
    boss = make_client()
    await email_login(boss, "boss@hojde.dk")
    assert (await me(boss))["staff"]["roles"] == ["administrator", "pilot"]


# ── Planning and the weather rule ───────────────────────────────────────────────────────────────────────────────────

async def order_id(conn, number: str) -> int:
    return (await db.fetch_one(conn, "select id from hojde_orders where number = %s", (number,)))["id"]


async def test_planning_needs_an_approved_quote_and_builds_the_checklist(owner_conn):
    await seeded()
    when = datetime.now(timezone.utc) + timedelta(days=20)
    async with db.connection() as conn:
        with pytest.raises(HTTPException) as e:   # 3D-model needs a quote; B-1047's quote is sent, not approved
            await ops.plan_order(conn, await order_id(conn, "B-1047"), when, None, actor_id=None, meta=RequestMeta())
    assert e.value.status_code == 409
    async with db.connection() as conn:
        with pytest.raises(HTTPException) as e:   # B-1042 already has a planned task
            await ops.plan_order(conn, await order_id(conn, "B-1042"), when, None, actor_id=None, meta=RequestMeta())
    assert e.value.detail == "Bestillingen har allerede en planlagt opgave"

    async with db.connection() as conn:          # B-1048 (termografi) needs a quote too; approve it first
        oid = await order_id(conn, "B-1048")
        await conn.execute("update hojde_orders set status = 'godkendt' where id = %s", (oid,))
        task = await ops.plan_order(conn, oid, when, None, actor_id=None, meta=RequestMeta())
        readiness = await ops.task_readiness(conn, task["id"])
    assert task["number"].startswith(f"OP-{when.astimezone(rules.TIME_ZONE).year}-")
    assert readiness.ready is False
    assert readiness.message == "6 punkter mangler: risikovurdering, batterier, adgang, flyverute, afspærring og drone."
    assert owner_conn.execute("select status from hojde_orders where number = 'B-1048'").fetchone()[0] == "planlagt"
    assert owner_conn.execute("""select count(*) from audit_log where (table_name, row_id) in
                                 (('hojde_tasks', %s), ('hojde_orders', %s))""",
                              (str(task["id"]), str(oid))).fetchone()[0] == 2


async def test_weather_rule_holds_and_clears(owner_conn):
    await seeded()
    async with db.connection() as conn:
        oid = await order_id(conn, "B-1042")
        task = await db.fetch_one(conn, "select id, scheduled_at from hojde_tasks where order_id = %s", (oid,))
        loc = await db.fetch_one(conn, "select l.id from hojde_locations l join hojde_orders o on o.location_id = l.id "
                                       "where o.id = %s", (oid,))
        # Move blok B to coordinates where the flight is fine: the hold is lifted.
        fine = seed.coordinates_for(56.0, 10.0, task["scheduled_at"], True)
        await conn.execute("update hojde_locations set lat = %s, lng = %s where id = %s", (fine["lat"], fine["lng"], loc["id"]))
        changes = await ops.apply_weather_rule(conn, task["scheduled_at"] - timedelta(hours=1))
    assert [(c["task_number"], c["from"], c["to"]) for c in changes if c["order_id"] == oid][0][1:] == \
        ("vejrforbehold", "forberedelse")
    assert owner_conn.execute("select status from hojde_orders where id = %s", (oid,)).fetchone()[0] == "planlagt"


# ── GDPR ────────────────────────────────────────────────────────────────────────────────────────────────────────────

async def test_gdpr_export_and_erasure_keep_the_logbook_but_remove_the_person(make_client, owner_conn):
    await seeded()
    await email_login(make_client(), "niels@example.com")
    anders = make_client()
    await email_login(anders, "anders@hojde.example")
    await me(anders)
    user_id = owner_conn.execute("select id from users where email = 'anders@hojde.example'").fetchone()[0]
    member_id = member_row(owner_conn, "anders@hojde.example")[0]

    async with db.connection() as conn:
        data = await gdpr.build_user_export(conn, user_id)
    h = data["hojde"]
    assert [m["email"] for m in h["memberships"]] == ["anders@hojde.example"]
    assert {f["number"] for f in h["flights_as_pilot"]} == {"FL-0925", "FL-0931"}
    assert len(h["certificates"]) == 1 and len(h["tasks_as_pilot"]) >= 5

    await gdpr.erase_user(user_id, actor_id=user_id, meta=RequestMeta(), reason="test")
    row = owner_conn.execute("select name, email, user_id, status, anonymised_at from hojde_members where id = %s",
                             (member_id,)).fetchone()
    assert row[0] == "Slettet bruger" and row[1] == f"slettet-{member_id}@slettet.invalid"
    assert row[2] is None and row[3] == "deaktiveret" and row[4] is not None
    assert owner_conn.execute("select count(*) from hojde_flights where pilot_id = %s", (member_id,)).fetchone()[0] == 2
    erasure = owner_conn.execute("select detail from audit_log where action = 'gdpr.erasure'").fetchone()[0]
    assert erasure["hojde_members"] == 1
    # The same e-mail signing up again does not get the old membership back.
    again = make_client()
    await email_login(again, "anders@hojde.example")
    assert (await me(again))["landing"] is None
