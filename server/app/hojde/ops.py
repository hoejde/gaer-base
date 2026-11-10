"""Højde operations shared by the API and the seed: numbering, turning an order into a task with its pre-flight
checklist, and the weather rule. Every change is audited in the caller's transaction."""

from datetime import datetime, timedelta

from fastapi import HTTPException

from app import db
from app.hojde import rules
from app.hojde.providers import weather
from app.logs import RequestMeta, audit

FLIGHT_WINDOW_MINUTES = 60  # a flight is judged over this window from the planned start


# ── Numbers ─────────────────────────────────────────────────────────────────────────────────────────────────────────

async def _next(conn, table: str, prefix: str, first: int) -> str:
    # One number at a time per series, so two orders created at once don't both get B-1049.
    await conn.execute("select pg_advisory_xact_lock(hashtext(%s))", (f"hojde.number:{prefix}",))
    rows = await db.fetch_all(conn, f"select number from {table} where number like %s", (prefix + "%",))
    return rules.next_number(prefix, [r["number"] for r in rows], first)


async def next_order_number(conn) -> str:
    return await _next(conn, "hojde_orders", "B-", 1001)


async def next_task_number(conn, at: datetime) -> str:
    return await _next(conn, "hojde_tasks", f"OP-{at.astimezone(rules.TIME_ZONE).year}-", 401)


async def next_flight_number(conn) -> str:
    return await _next(conn, "hojde_flights", "FL-", 1)


# ── Checklist ───────────────────────────────────────────────────────────────────────────────────────────────────────

RISK_TEMPLATE = {"bygning": "Bygning, by", "byggeplads": "Byggeplads, by", "omraade": "Åbent område"}


def checklist_template(location_type: str, restricted_zone: bool, *, access_confirmed: bool,
                       repeat_visit: bool) -> list[dict]:
    items = [
        {"key": "risk", "label": f"Risikovurdering udfyldt fra skabelon “{RISK_TEMPLATE.get(location_type, 'Generel')}”",
         "short": "risikovurdering", "done": False},
        {"key": "batteries", "label": "Batterier ladet og registreret", "short": "batterier", "done": False},
        {"key": "access", "label": "Kunden har bekræftet adgang og kontaktperson", "short": "adgang",
         "done": access_confirmed},
        {"key": "route", "label": "Flyverute fra sidste besøg indlæst (faste fotopunkter)" if repeat_visit
         else "Flyverute planlagt", "short": "flyverute", "done": False},
    ]
    if restricted_zone:
        items.append({"key": rules.ZONE_PERMIT_KEY, "label": "Tilladelse til restriktionszone registreret",
                      "short": "tilladelse", "done": False})
    items.append({"key": "cordon", "label": "Afspærring af start- og landingsområde planlagt", "short": "afspærring",
                  "done": False})
    return items


async def task_readiness(conn, task_id: int) -> rules.Readiness:
    task = await db.fetch_one(conn, """
        select t.permit_registered_at, l.restricted_zone, e.status as drone_status
        from hojde_tasks t join hojde_locations l on l.id = t.location_id
        left join hojde_equipment e on e.id = t.drone_id where t.id = %s""", (task_id,))
    items = await db.fetch_all(conn, "select key, short, done_at from hojde_checklist_items where task_id = %s "
                                     "order by sort", (task_id,))
    return rules.readiness([rules.ChecklistEntry(i["key"], i["short"], i["done_at"] is not None) for i in items],
                           restricted_zone=task["restricted_zone"],
                           permit_registered=task["permit_registered_at"] is not None,
                           drone_status=task["drone_status"])


# ── Orders → tasks ──────────────────────────────────────────────────────────────────────────────────────────────────

def transition(current: str, action: str) -> str:
    to = rules.next_order_status(current, action)
    if to is None:
        raise HTTPException(409, f"Bestillingen kan ikke ændres fra status “{current}”")
    return to


async def plan_order(conn, order_id: int, scheduled_at: datetime, pilot_id: int | None, *, actor_id: int | None,
                     meta: RequestMeta) -> dict:
    """Plans a visit: a task with its checklist; the order becomes planlagt."""
    order = await db.fetch_one(conn, """
        select o.id, o.status, o.frequency, o.visits, o.location_id, o.access_confirmed_at, s.needs_quote,
               l.type as location_type, l.restricted_zone
        from hojde_orders o join hojde_services s on s.id = o.service_id join hojde_locations l on l.id = o.location_id
        where o.id = %s for update of o""", (order_id,))
    if order is None:
        raise HTTPException(404, "Bestillingen findes ikke")
    if order["status"] == "afventer_godkendelse" and order["needs_quote"]:
        raise HTTPException(409, "Ydelsen kræver et tilbud, som kunden har godkendt, før den kan planlægges")
    status = transition(order["status"], "schedule")
    tasks = await db.fetch_all(conn, "select status from hojde_tasks where order_id = %s", (order_id,))
    if order["frequency"] == "abonnement" and order["visits"] is not None and len(tasks) >= order["visits"]:
        raise HTTPException(409, "Alle besøg i abonnementet er planlagt")
    if order["frequency"] == "enkelt" and any(t["status"] != "leveret" for t in tasks):
        raise HTTPException(409, "Bestillingen har allerede en planlagt opgave")
    number = await next_task_number(conn, scheduled_at)
    task = await db.fetch_one(conn, """
        insert into hojde_tasks (number, order_id, location_id, scheduled_at, pilot_id, visit_number)
        values (%s, %s, %s, %s, %s, %s) returning id, number, scheduled_at, status""",
        (number, order_id, order["location_id"], scheduled_at, pilot_id,
         len(tasks) + 1 if order["frequency"] == "abonnement" else None))
    template = checklist_template(order["location_type"], order["restricted_zone"],
                                  access_confirmed=order["access_confirmed_at"] is not None,
                                  repeat_visit=bool(tasks))
    for sort, item in enumerate(template):
        # An item already done here was confirmed by the customer: done_at without done_by.
        await conn.execute("""insert into hojde_checklist_items (task_id, key, label, short, sort, done_at)
                              values (%s, %s, %s, %s, %s, case when %s then now() end)""",
                           (task["id"], item["key"], item["label"], item["short"], sort, item["done"]))
    await conn.execute("update hojde_orders set status = %s, scheduled_at = %s where id = %s",
                       (status, scheduled_at, order_id))
    await audit(conn, "create", actor_id=actor_id, meta=meta, table="hojde_tasks", row_id=task["id"],
                after={"number": number, "order_id": order_id, "scheduled_at": scheduled_at, "pilot_id": pilot_id})
    if status != order["status"]:
        await audit(conn, "update", actor_id=actor_id, meta=meta, table="hojde_orders", row_id=order_id,
                    before={"status": order["status"]}, after={"status": status})
    return task


# ── Weather ─────────────────────────────────────────────────────────────────────────────────────────────────────────

def flight_weather(location_id: int, lat: float | None, lng: float | None, at: datetime):
    hours = weather.forecast(location_id=location_id, lat=lat, lng=lng, day=at)
    return hours, rules.weather_verdict(hours, at, FLIGHT_WINDOW_MINUTES)


async def apply_weather_rule(conn, now: datetime, *, horizon_hours: int = 48, actor_id: int | None = None,
                             meta: RequestMeta | None = None) -> list[dict]:
    """A planned flight in the next 48 hours with wind over 10 m/s or precipitation goes on vejrforbehold (task and
    order); one whose forecast cleared goes back. The customer sees the hold in the portal as soon as it is set —
    by the day before at the latest."""
    meta = meta or RequestMeta()
    tasks = await db.fetch_all(conn, """
        select t.id, t.number, t.status, t.scheduled_at, t.ready_at, t.order_id, o.status as order_status,
               l.id as location_id, l.lat, l.lng
        from hojde_tasks t join hojde_orders o on o.id = t.order_id join hojde_locations l on l.id = t.location_id
        where t.status in ('forberedelse', 'klar', 'vejrforbehold') and t.scheduled_at between %s and %s
        order by t.scheduled_at
        for update of t, o""", (now, now + timedelta(hours=horizon_hours)))
    changes = []
    for t in tasks:
        _, verdict = flight_weather(t["location_id"], t["lat"], t["lng"], t["scheduled_at"])
        if not verdict.ok and t["status"] != "vejrforbehold":
            task_to, order_action = "vejrforbehold", "weather_hold"
        elif verdict.ok and t["status"] == "vejrforbehold":
            task_to, order_action = ("klar" if t["ready_at"] else "forberedelse"), "weather_clear"
        else:
            continue
        await conn.execute("update hojde_tasks set status = %s where id = %s", (task_to, t["id"]))
        await audit(conn, "update", actor_id=actor_id, meta=meta, table="hojde_tasks", row_id=t["id"],
                    before={"status": t["status"]}, after={"status": task_to}, via="weather_rule",
                    reasons=verdict.reasons)
        order_to = rules.next_order_status(t["order_status"], order_action)
        if order_to:
            await conn.execute("update hojde_orders set status = %s where id = %s", (order_to, t["order_id"]))
            await audit(conn, "update", actor_id=actor_id, meta=meta, table="hojde_orders", row_id=t["order_id"],
                        before={"status": t["order_status"]}, after={"status": order_to}, via="weather_rule")
        changes.append({"task_id": t["id"], "task_number": t["number"], "order_id": t["order_id"],
                        "from": t["status"], "to": task_to, "reasons": verdict.reasons})
    return changes
