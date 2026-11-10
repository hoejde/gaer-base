"""Højde backoffice API (/api/hojde/backoffice): staff with a second factor, roles per action, the overview, week
planning, quotes, task preparation with the checklist gate, the flight log, delivery, equipment and the weather job.
Runs against the demo tenant from app.hojde.seed."""

from datetime import datetime, timedelta, timezone

import pytest

from app import db
from app.hojde import ops, rules
from tests.test_hojde import email_login
from tests.test_hojde_portal import login, order_id, tenant  # noqa: F401  (fixtures)

B = "/api/hojde/backoffice"


def task_of(conn, number: str) -> int:
    return conn.execute("select t.id from hojde_tasks t join hojde_orders o on o.id = t.order_id where o.number = %s "
                        "order by t.scheduled_at desc limit 1", (number,)).fetchone()[0]


def equipment(conn, name: str) -> int:
    return conn.execute("select id from hojde_equipment where name = %s", (name,)).fetchone()[0]


async def test_backoffice_is_for_staff_with_a_second_factor(tenant, make_client, login):
    emil = make_client()
    await email_login(emil, "emil@hojde.example")
    r = await emil.get(f"{B}/overview")
    assert r.status_code == 403 and r.headers["X-Gaer-Error"] == "mfa_setup_required"
    mette = await login("mh@kystparken.example")
    r = await mette.get(f"{B}/overview")
    assert r.status_code == 403 and r.json()["detail"] == "Kun for Højdes medarbejdere"
    emil = await login("emil@hojde.example")
    assert (await emil.get(f"{B}/overview")).status_code == 200


async def test_overview_and_week(tenant, login):
    emil = await login("emil@hojde.example")
    body = (await emil.get(f"{B}/overview")).json()
    assert body["stats"]["flights_today"] == 2
    assert body["stats"]["findings_to_review"] == 9 and body["stats"]["findings_to_review_visits"] == 1
    assert body["stats"]["quotes_to_send"] == 1                     # B-1048 termografi
    assert body["awaiting_analysis"] == [{"location": "Kystparken blok B", "findings": 9}]
    assert {f["customer"] for f in body["flights"]} == {"Demo Bygherre A/S", "Demo Ejendomme"}
    assert all(f["weather"] is not None for f in body["flights"])
    insurance = next(c for c in body["compliance"] if c["title"].startswith("Ansvarsforsikring"))
    assert insurance["state"] == "udloeber" and body["compliance"][0] == insurance
    assert body["compliance"][-1]["title"] == "Pilotcertifikater: 2 af 2 gyldige"

    week = (await emil.get(f"{B}/tasks")).json()
    today = datetime.now(rules.TIME_ZONE).date()
    assert week["week"] == today.isocalendar().week and week["week_start"] == (today - timedelta(days=today.weekday())).isoformat()
    assert [q["number"] for q in week["quotes_to_send"]] == ["B-1048"]
    nxt = (await emil.get(f"{B}/tasks?week={(today + timedelta(days=7)).isoformat()}")).json()
    assert nxt["week"] == (today + timedelta(days=7)).isocalendar().week
    assert (await emil.get(f"{B}/tasks?week=x")).status_code == 422
    staff = (await emil.get(f"{B}/staff")).json()
    assert [s["name"] for s in staff] == ["Anders", "Emil", "Kundeansvarlig"]


async def test_quotes_need_kundeansvarlig(tenant, login, owner_conn):
    anders = await login("anders@hojde.example")
    oid = order_id(owner_conn, "B-1048")
    r = await anders.post(f"{B}/orders/{oid}/quote", json={"amount_ore": 1250000})
    assert r.status_code == 403 and r.json()["detail"] == "Kræver rollen kundeansvarlig"
    salg = await login("salg@hojde.example")
    assert (await salg.post(f"{B}/orders/{oid}/quote", json={"amount_ore": 1250000})).status_code == 200
    assert owner_conn.execute("select status, quote_ore from hojde_orders where id = %s", (oid,)).fetchone() == \
        ("tilbud_sendt", 1250000)
    assert (await salg.post(f"{B}/orders/{oid}/quote", json={"amount_ore": 1})).status_code == 409


async def test_from_plan_to_delivery(tenant, login, owner_conn):
    emil = await login("emil@hojde.example")
    anders = await login("anders@hojde.example")
    oid = order_id(owner_conn, "B-1047")
    owner_conn.execute("update hojde_orders set status = 'godkendt' where id = %s", (oid,))
    pilot = owner_conn.execute("select id from hojde_members where email = 'anders@hojde.example'").fetchone()[0]
    when = (datetime.now(timezone.utc) + timedelta(days=3)).replace(microsecond=0)
    r = await emil.post(f"{B}/orders/{oid}/plan", json={"scheduled_at": when.isoformat(), "pilot_id": pilot})
    assert r.status_code == 201, r.text
    task = r.json()
    assert task["pilot"]["name"] == "Anders" and task["zone"]["status"] == "fri"
    assert [c["key"] for c in task["checklist"]] == ["risk", "batteries", "access", "route", "cordon"]
    assert task["readiness"]["message"] == "6 punkter mangler: risikovurdering, batterier, adgang, flyverute, afspærring og drone."
    tid = task["id"]

    r = await anders.post(f"{B}/tasks/{tid}/ready")
    assert r.status_code == 409 and r.json()["detail"].startswith("6 punkter mangler")
    r = await emil.patch(f"{B}/tasks/{tid}", json={"drone_id": equipment(owner_conn, "Drone 2")})
    assert r.status_code == 409                                     # til service
    assert (await emil.patch(f"{B}/tasks/{tid}", json={"drone_id": equipment(owner_conn, "Drone 1")})).status_code == 200
    for key in ("risk", "batteries", "access", "route", "cordon"):
        r = await anders.post(f"{B}/tasks/{tid}/checklist/{key}", json={"done": True})
    assert r.json()["readiness"]["ready"] is True
    assert {c["done_by"] for c in r.json()["checklist"]} == {"Anders"}

    salg = await login("salg@hojde.example")
    assert (await salg.post(f"{B}/tasks/{tid}/ready")).json()["detail"] == "Kræver rollen pilot"
    r = await anders.post(f"{B}/tasks/{tid}/ready")
    assert r.status_code == 200 and r.json()["status"] == "klar"
    r = await anders.post(f"{B}/tasks/{tid}/checklist/cordon", json={"done": False})
    assert r.json()["status"] == "forberedelse"                     # reopening an item undoes "klar"
    await anders.post(f"{B}/tasks/{tid}/checklist/cordon", json={"done": True})
    assert (await anders.post(f"{B}/tasks/{tid}/ready")).json()["status"] == "klar"

    drone = equipment(owner_conn, "Drone 1")
    usage = owner_conn.execute("select usage_minutes from hojde_equipment where id = %s", (drone,)).fetchone()[0]
    battery = equipment(owner_conn, "Batteri 1")
    r = await anders.post(f"{B}/tasks/{tid}/flights", json={"started_at": when.isoformat(), "sorties": 3,
                                                            "minutes_per_sortie": 20, "wind_ms": 5.5,
                                                            "battery_ids": [battery]})
    assert r.status_code == 201, r.text
    flight = r.json()
    assert flight["number"] == "FL-0932" and flight["pilot"] == "Anders" and flight["drone"] == "Mini 5 Pro · C0"
    assert owner_conn.execute("select usage_minutes from hojde_equipment where id = %s", (drone,)).fetchone()[0] == usage + 60
    assert owner_conn.execute("select cycles from hojde_equipment where id = %s", (battery,)).fetchone()[0] == 44
    assert owner_conn.execute("select status from hojde_tasks where id = %s", (tid,)).fetchone()[0] == "floejet"

    assert (await anders.post(f"{B}/tasks/{tid}/deliver")).json()["detail"] == "Kræver rollen analytiker"
    r = await emil.post(f"{B}/tasks/{tid}/deliver")
    assert r.status_code == 200 and r.json()["status"] == "leveret"
    assert owner_conn.execute("select status from hojde_orders where id = %s", (oid,)).fetchone()[0] == "leveret"
    log = (await emil.get(f"{B}/compliance")).json()
    assert log["flights"][0]["number"] == "FL-0932" and log["incidents"] == 1
    actions = owner_conn.execute("""select table_name, count(*) from audit_log
                                    where table_name in ('hojde_flights', 'hojde_equipment') group by 1 order by 1""").fetchall()
    assert actions == [("hojde_equipment", 2), ("hojde_flights", 1)]


async def test_zone_permit_is_registered_not_ticked(tenant, login, owner_conn):
    emil = await login("emil@hojde.example")
    tid = task_of(owner_conn, "B-1018")                              # Nordhavn, restricted zone, today
    r = await emil.post(f"{B}/tasks/{tid}/checklist/zone_permit", json={"done": True})
    assert r.status_code == 409
    r = await emil.post(f"{B}/tasks/{tid}/permit")
    body = r.json()
    assert body["zone"]["permit_registered"] is True
    assert next(c for c in body["checklist"] if c["key"] == "zone_permit")["done"] is True
    other = task_of(owner_conn, "B-1043")
    assert (await emil.post(f"{B}/tasks/{other}/permit")).status_code == 409


async def test_rescheduling_resets_access_and_readiness(tenant, login, owner_conn):
    emil = await login("emil@hojde.example")
    tid = task_of(owner_conn, "B-1043")
    when = (datetime.now(timezone.utc) + timedelta(days=12)).replace(microsecond=0)
    r = await emil.post(f"{B}/tasks/{tid}/reschedule", json={"scheduled_at": when.isoformat(), "reason": "vejr"})
    assert r.status_code == 200, r.text
    assert datetime.fromisoformat(r.json()["scheduled_at"]) == when
    assert next(c for c in r.json()["checklist"] if c["key"] == "access")["done"] is False
    order = owner_conn.execute("select status, access_confirmed_at, scheduled_at from hojde_orders where number = 'B-1043'").fetchone()
    assert order[0] == "planlagt" and order[1] is None and order[2] == when
    past = {"scheduled_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(), "reason": "andet"}
    assert (await emil.post(f"{B}/tasks/{tid}/reschedule", json=past)).status_code == 422


async def test_equipment_and_the_weather_job(tenant, login, owner_conn):
    anders = await login("anders@hojde.example")
    r = await anders.post(f"{B}/equipment", json={"name": "Batteri 6", "kind": "batteri", "model": "Intelligent Flight Battery"})
    assert r.status_code == 201 and r.json()["usage"] == "0 cyklusser"
    r = await anders.patch(f"{B}/equipment/{r.json()['id']}", json={"status": "til_kontrol"})
    assert r.json()["status"] == "til_kontrol"
    names = [e["name"] for e in (await anders.get(f"{B}/equipment")).json()]
    assert names[0] == "Drone 1" and names[-1] == "Batteri 6"

    assert owner_conn.execute("select interval_seconds from job_schedules where name = 'hojde.weather'").fetchone() == (3600,)
    result = await ops.weather_job({}, {})
    assert "changes" in result
