"""Højde backoffice API (/api/hojde/backoffice): the overview, week planning, quotes, task preparation (zone, weather,
the checklist gate), the flight log, equipment and compliance documents. Staff only, always with a second factor
(app/hojde/access.py). Some actions need a role — sending quotes: kundeansvarlig; marking ready, logging flights and
equipment: pilot; delivering: analytiker — and administrators pass everything. Every change is audited in the same
transaction.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app import db, events, webhooks
from app.hojde import ops, rules
from app.hojde.access import HojdeContext, require_staff
from app.hojde.providers import zones
from app.logs import audit, changed

router = APIRouter(prefix="/api/hojde/backoffice", tags=["hojde"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v):
    return v.isoformat() if v else None


def _who(ctx: HojdeContext) -> dict:
    return {"actor_id": ctx.principal.user_id, "meta": ctx.principal.meta}


# ── Rows → JSON ─────────────────────────────────────────────────────────────────────────────────────────────────────

def equipment_usage(e: dict) -> str:
    if e["kind"] == "batteri":
        return "—" if e["cycles"] is None else f"{e['cycles']} cyklusser"
    if e["kind"] == "drone":
        return f"{e['usage_minutes'] // 60} t {e['usage_minutes'] % 60} min"
    return "—"


def equipment_item(e: dict) -> dict:
    return {"id": e["id"], "name": e["name"], "kind": e["kind"], "model": e["model"], "serial": e["serial"],
            "c_class": e["c_class"], "usage": equipment_usage(e), "next_service": e["next_service"], "status": e["status"]}


FLIGHT_SELECT = """
    select f.*, l.name as location_name, p.name as pilot_name, e.model as drone_model, e.c_class as drone_class
    from hojde_flights f join hojde_locations l on l.id = f.location_id join hojde_members p on p.id = f.pilot_id
    join hojde_equipment e on e.id = f.drone_id"""


def flight_item(f: dict) -> dict:
    drone = " · ".join(x for x in (f["drone_model"].removeprefix("DJI "), f["drone_class"]) if x)
    return {"id": f["id"], "number": f["number"], "started_at": _iso(f["started_at"]), "location": f["location_name"],
            "pilot": f["pilot_name"], "drone": drone, "sorties": f["sorties"],
            "minutes_per_sortie": f["minutes_per_sortie"], "wind_ms": float(f["wind_ms"]), "incident": f["incident"]}


TASK_LIST_SELECT = """
    select t.id, t.number, t.scheduled_at, t.status, l.id as location_id, l.name as location_name, l.lat, l.lng,
           l.restricted_zone, org.name as customer, s.title as service, p.name as pilot
    from hojde_tasks t join hojde_locations l on l.id = t.location_id join hojde_orders o on o.id = t.order_id
    join hojde_organizations org on org.id = o.org_id join hojde_services s on s.id = o.service_id
    left join hojde_members p on p.id = t.pilot_id"""


def task_list_item(t: dict, with_weather: bool) -> dict:
    weather = None
    if with_weather:
        hours, verdict = ops.flight_weather(t["location_id"], t["lat"], t["lng"], t["scheduled_at"])
        near = next((h for h in hours if h.at <= t["scheduled_at"] < h.at + timedelta(hours=1)), hours[0] if hours else None)
        if near:
            weather = {"wind_ms": near.wind_ms, "dry": near.precipitation_mm == 0, "ok": verdict.ok}
    return {"id": t["id"], "number": t["number"], "scheduled_at": _iso(t["scheduled_at"]),
            "location": {"id": t["location_id"], "name": t["location_name"]}, "customer": t["customer"],
            "service": t["service"], "pilot": t["pilot"], "status": t["status"],
            "zone": "tilladelse" if t["restricted_zone"] else "fri", "weather": weather}


async def _backlog(conn, now: datetime) -> tuple[list[dict], list[dict]]:
    """Orders waiting for a quote, and orders ready to be put in the calendar."""
    rows = await db.fetch_all(conn, """
        select o.id, o.number, o.status, o.frequency, o.visits, o.preferred_to, l.name as location, s.title as service,
               s.needs_quote, org.name as customer,
               (select count(*) from hojde_tasks t where t.order_id = o.id) as tasks,
               exists (select 1 from hojde_tasks t where t.order_id = o.id and t.scheduled_at > %s) as ahead
        from hojde_orders o join hojde_locations l on l.id = o.location_id join hojde_services s on s.id = o.service_id
        join hojde_organizations org on org.id = o.org_id
        where o.status in ('afventer_godkendelse', 'godkendt', 'planlagt')
        order by o.preferred_to nulls last, o.created_at""", (now,))

    def item(o):
        return {"order_id": o["id"], "number": o["number"], "status": o["status"], "frequency": o["frequency"],
                "location": o["location"], "service": o["service"], "customer": o["customer"],
                "visit_number": o["tasks"] + 1 if o["frequency"] == "abonnement" else None, "visits": o["visits"],
                "preferred_to": _iso(o["preferred_to"])}

    quotes = [item(o) for o in rows if o["status"] == "afventer_godkendelse" and o["needs_quote"]]
    unplanned = [item(o) for o in rows if o["status"] == "godkendt"
                 or (o["status"] == "afventer_godkendelse" and not o["needs_quote"])
                 or (o["status"] == "planlagt" and o["frequency"] == "abonnement" and (o["visits"] or 0) > o["tasks"]
                     and not o["ahead"])]
    return quotes, unplanned


async def _task_for_update(conn, task_id: int) -> dict:
    task = await db.fetch_one(conn, """
        select t.*, l.restricted_zone, o.status as order_status, o.frequency, o.visits, o.number as order_number
        from hojde_tasks t join hojde_locations l on l.id = t.location_id join hojde_orders o on o.id = t.order_id
        where t.id = %s for update of t, o""", (task_id,))
    if task is None:
        raise HTTPException(404, "Opgaven findes ikke")
    return task


def _editable(task: dict) -> None:
    if task["status"] in ("floejet", "leveret"):
        raise HTTPException(409, "Opgaven er fløjet og kan ikke længere forberedes")


async def task_detail(conn, task_id: int) -> dict:
    t = await db.fetch_one(conn, """
        select t.*, o.id as order_id, o.number as order_number, o.frequency, o.visits, o.report_recipient,
               o.contact_name as order_contact, o.contact_phone as order_phone, s.title as service_title,
               s.line as service_line, org.name as customer
        from hojde_tasks t join hojde_orders o on o.id = t.order_id join hojde_services s on s.id = o.service_id
        join hojde_organizations org on org.id = o.org_id where t.id = %s""", (task_id,))
    if t is None:
        raise HTTPException(404, "Opgaven findes ikke")
    loc = await db.fetch_one(conn, "select * from hojde_locations where id = %s", (t["location_id"],))
    pilot = await db.fetch_one(conn, "select id, name, roles, certificates from hojde_members where id = %s",
                               (t["pilot_id"],)) if t["pilot_id"] else None
    drone = await db.fetch_one(conn, "select * from hojde_equipment where id = %s", (t["drone_id"],)) if t["drone_id"] else None
    checklist = await db.fetch_all(conn, """select c.key, c.label, c.short, c.done_at, c.done_by, m.name as done_by_name,
                                                   m.kind as done_by_kind
                                            from hojde_checklist_items c left join hojde_members m on m.id = c.done_by
                                            where c.task_id = %s order by c.sort""", (task_id,))
    flights = await db.fetch_all(conn, f"{FLIGHT_SELECT} where f.task_id = %s order by f.started_at desc", (task_id,))
    hours, verdict = ops.flight_weather(loc["id"], loc["lat"], loc["lng"], t["scheduled_at"])
    around = [h for h in hours if t["scheduled_at"] - timedelta(hours=1) < h.at <= t["scheduled_at"] + timedelta(hours=2)][:3]
    zone = zones.check(lat=loc["lat"], lng=loc["lng"], restricted_zone=loc["restricted_zone"])
    readiness = await ops.task_readiness(conn, task_id)
    return {
        "id": t["id"], "number": t["number"], "order_id": t["order_id"], "order_number": t["order_number"],
        "status": t["status"], "phase": t["phase"], "scheduled_at": _iso(t["scheduled_at"]),
        "service": {"title": t["service_title"], "line": t["service_line"]},
        "location": {k: loc[k] for k in ("id", "name", "type", "address", "lat", "lng", "contact_name", "contact_phone",
                                         "access_notes", "restricted_zone")},
        "customer": t["customer"], "visit_number": t["visit_number"], "visits": t["visits"],
        "subscription": f"{t['visits'] or '?'} besøg" if t["frequency"] == "abonnement" else None,
        "report_recipient": t["report_recipient"],
        "contact": ", ".join(x for x in (t["order_contact"], t["order_phone"]) if x),
        "pilot": pilot,
        "drone": equipment_item(drone) if drone else None,
        "zone": {"status": "tilladelse" if zone.restricted else "fri",
                 "permit_registered": t["permit_registered_at"] is not None, "coordinates": zone.coordinates,
                 "max_altitude_m": zone.max_altitude_m, "notam": zone.notam},
        "weather": {"hours": [{"at": _iso(h.at), "wind_ms": h.wind_ms, "gust_ms": h.gust_ms,
                               "precipitation_mm": h.precipitation_mm, "visibility_km": h.visibility_km} for h in around],
                    "ok": verdict.ok, "reasons": verdict.reasons},
        "checklist": [{"key": c["key"], "label": c["label"], "short": c["short"], "done": c["done_at"] is not None,
                       "done_by": None if c["done_at"] is None else
                       ("Kunden" if c["done_by"] is None or c["done_by_kind"] == "customer" else c["done_by_name"])}
                      for c in checklist],
        "readiness": {"ready": readiness.ready, "missing": readiness.missing, "message": readiness.message},
        "flights": [flight_item(f) for f in flights],
    }


# ── Overview ────────────────────────────────────────────────────────────────────────────────────────────────────────

@router.get("/overview")
async def overview(ctx: HojdeContext = Depends(require_staff())):
    now = _now()
    today = rules.local_day(now)
    tomorrow = (date.fromisoformat(today) + timedelta(days=1)).isoformat()
    async with db.connection() as conn:
        tasks = await db.fetch_all(conn, f"""{TASK_LIST_SELECT} where t.scheduled_at >= %s and t.scheduled_at < %s
                                            order by t.scheduled_at""",
                                   (rules.local_time(today, 0), rules.local_time(tomorrow, 0)))
        review = await db.fetch_all(conn, """select f.visit_date, l.name as location from hojde_findings f
                                             join hojde_locations l on l.id = f.location_id
                                             where f.qc_state = 'afventer'""")
        docs = await db.fetch_all(conn, "select kind, title, expires_at from hojde_compliance_documents order by created_at")
        pilots = (await db.fetch_one(conn, """select count(*) as n from hojde_members where kind = 'staff'
                                              and status = 'aktiv' and 'pilot' = any(roles)"""))["n"]
        quotes, unplanned = await _backlog(conn, now)
    by_location: dict[str, int] = {}
    for f in review:
        by_location[f["location"]] = by_location.get(f["location"], 0) + 1
    certs = [d for d in docs if d["kind"] == "pilotcertifikat"]
    valid = sum(1 for d in certs if rules.compliance_state(d["expires_at"], now)["state"] == "gyldig")
    compliance = []
    for d in docs:
        if d["kind"] == "pilotcertifikat":
            continue
        s = rules.compliance_state(d["expires_at"], now)
        compliance.append({"title": f"{d['title']} gyldig" if s["state"] == "gyldig" else f"{d['title']} skal fornyes",
                           "state": s["state"], "days": s.get("days")})
    if certs:
        compliance.append({"title": f"Pilotcertifikater: {valid} af {max(len(certs), pilots)} gyldige",
                           "state": "gyldig" if valid == len(certs) else "udloeber", "days": None})
    compliance.sort(key=lambda c: c["state"] == "gyldig")
    flights = [task_list_item(t, True) for t in tasks]
    return {
        "today": _iso(now),
        "stats": {"flights_today": len(flights),
                  "flights_on_weather_hold": sum(1 for f in flights if f["status"] == "vejrforbehold"),
                  "findings_to_review": len(review),
                  "findings_to_review_visits": len({(f["location"], f["visit_date"]) for f in review}),
                  "quotes_to_send": len(quotes), "orders_to_plan": len(unplanned)},
        "flights": flights,
        "awaiting_analysis": [{"location": k, "findings": v} for k, v in by_location.items()],
        "compliance": compliance,
    }


@router.get("/staff")
async def staff(ctx: HojdeContext = Depends(require_staff())):
    async with db.connection() as conn:
        return await db.fetch_all(conn, """select id, name, roles, certificates from hojde_members
                                           where kind = 'staff' and status = 'aktiv' order by name""")


# ── Planning ────────────────────────────────────────────────────────────────────────────────────────────────────────

@router.get("/tasks")
async def week(week: str = Query("", pattern=r"^(\d{4}-\d{2}-\d{2})?$"), ctx: HojdeContext = Depends(require_staff())):
    now = _now()
    day = date.fromisoformat(week) if week else date.fromisoformat(rules.local_day(now))
    start = day - timedelta(days=day.weekday())
    async with db.connection() as conn:
        tasks = await db.fetch_all(conn, f"""{TASK_LIST_SELECT} where t.scheduled_at >= %s and t.scheduled_at < %s
                                            order by t.scheduled_at""",
                                   (rules.local_time(start.isoformat(), 0),
                                    rules.local_time((start + timedelta(days=7)).isoformat(), 0)))
        quotes, unplanned = await _backlog(conn, now)
    return {"week_start": start.isoformat(), "week": start.isocalendar().week,
            "tasks": [task_list_item(t, False) for t in tasks], "unplanned": unplanned, "quotes_to_send": quotes}


class QuoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount_ore: int = Field(gt=0, le=2_000_000_000)


@router.post("/orders/{order_id}/quote")
async def send_quote(order_id: int, body: QuoteIn, ctx: HojdeContext = Depends(require_staff("kundeansvarlig"))):
    async with db.connection() as conn:
        order = await db.fetch_one(conn, "select id, status, org_id from hojde_orders where id = %s for update", (order_id,))
        if order is None:
            raise HTTPException(404, "Bestillingen findes ikke")
        to = ops.transition(order["status"], "send_quote")
        await conn.execute("update hojde_orders set status = %s, quote_ore = %s, quote_sent_at = now() where id = %s",
                           (to, body.amount_ore, order_id))
        await audit(conn, "update", **_who(ctx), table="hojde_orders", row_id=order_id,
                    before={"status": order["status"]}, after={"status": to, "quote_ore": body.amount_ore},
                    step="send_quote", member_id=ctx.staff.id)
        await webhooks.emit(conn, "hojde.quote.sent", {"order_id": order_id, "organization_id": order["org_id"]})
    return {"ok": True}


async def _assert_pilot(conn, member_id: int) -> None:
    pilot = await db.fetch_one(conn, """select id from hojde_members where id = %s and kind = 'staff'
                                        and status = 'aktiv' and 'pilot' = any(roles)""", (member_id,))
    if pilot is None:
        raise HTTPException(422, "Piloten findes ikke")


class PlanIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scheduled_at: datetime
    pilot_id: int | None = None


@router.post("/orders/{order_id}/plan", status_code=201)
async def plan(order_id: int, body: PlanIn, ctx: HojdeContext = Depends(require_staff())):
    if body.scheduled_at.tzinfo is None:
        raise HTTPException(422, "Tidspunktet skal have en tidszone")
    async with db.connection() as conn:
        if body.pilot_id:
            await _assert_pilot(conn, body.pilot_id)
        task = await ops.plan_order(conn, order_id, body.scheduled_at, body.pilot_id, **_who(ctx))
        return await task_detail(conn, task["id"])


@router.post("/weather/check")
async def weather_check(ctx: HojdeContext = Depends(require_staff())):
    async with db.connection() as conn:
        changes = await ops.apply_weather_rule(conn, _now(), **_who(ctx))
    return {"changes": changes}


# ── Task preparation ────────────────────────────────────────────────────────────────────────────────────────────────

@router.get("/tasks/{task_id}")
async def task(task_id: int, ctx: HojdeContext = Depends(require_staff())):
    async with db.connection() as conn:
        return await task_detail(conn, task_id)


class TaskIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pilot_id: int | None = None
    drone_id: int | None = None


@router.patch("/tasks/{task_id}")
async def update_task(task_id: int, body: TaskIn, ctx: HojdeContext = Depends(require_staff())):
    fields = {k: getattr(body, k) for k in body.model_fields_set}
    async with db.connection() as conn:
        t = await _task_for_update(conn, task_id)
        _editable(t)
        if fields.get("pilot_id"):
            await _assert_pilot(conn, fields["pilot_id"])
        if fields.get("drone_id"):
            drone = await db.fetch_one(conn, "select kind, status from hojde_equipment where id = %s", (fields["drone_id"],))
            if drone is None or drone["kind"] != "drone":
                raise HTTPException(422, "Dronen findes ikke")
            if not rules.equipment_pickable(drone["status"]):
                raise HTTPException(409, "Udstyr med status Til kontrol eller Til service kan ikke vælges")
        before, after = changed({k: t[k] for k in fields}, fields)
        if after:
            # A new pilot or drone after "klar" sends the task back to preparation.
            if t["status"] == "klar":
                after.update(status="forberedelse", phase="forberedelse", ready_at=None)
                before.update(status="klar", phase=t["phase"], ready_at=t["ready_at"])
            sets = ", ".join(f"{k} = %({k})s" for k in after)
            await conn.execute(f"update hojde_tasks set {sets} where id = %(id)s", {**after, "id": task_id})
            await audit(conn, "update", **_who(ctx), table="hojde_tasks", row_id=task_id, before=before, after=after,
                        member_id=ctx.staff.id)
        return await task_detail(conn, task_id)


class ChecklistIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    done: bool


@router.post("/tasks/{task_id}/checklist/{key}")
async def toggle_checklist(task_id: int, key: str, body: ChecklistIn, ctx: HojdeContext = Depends(require_staff())):
    if key == rules.ZONE_PERMIT_KEY:
        raise HTTPException(409, "Tilladelsen registreres med “Registrér tilladelse”")
    async with db.connection() as conn:
        t = await _task_for_update(conn, task_id)
        _editable(t)
        item = await db.fetch_one(conn, "select id, done_at from hojde_checklist_items where task_id = %s and key = %s",
                                  (task_id, key))
        if item is None:
            raise HTTPException(404, "Punktet findes ikke")
        await conn.execute("""update hojde_checklist_items set done_at = case when %s then now() end,
                              done_by = case when %s then %s::bigint end where id = %s""",
                           (body.done, body.done, ctx.staff.id, item["id"]))
        await audit(conn, "update", **_who(ctx), table="hojde_checklist_items", row_id=item["id"],
                    before={"done": item["done_at"] is not None}, after={"done": body.done}, task_id=task_id, key=key,
                    member_id=ctx.staff.id)
        if not body.done and t["status"] == "klar":
            await conn.execute("""update hojde_tasks set status = 'forberedelse', phase = 'forberedelse', ready_at = null
                                  where id = %s""", (task_id,))
            await audit(conn, "update", **_who(ctx), table="hojde_tasks", row_id=task_id, before={"status": "klar"},
                        after={"status": "forberedelse"}, reason="checklist_reopened", member_id=ctx.staff.id)
        return await task_detail(conn, task_id)


@router.post("/tasks/{task_id}/permit")
async def register_permit(task_id: int, ctx: HojdeContext = Depends(require_staff())):
    async with db.connection() as conn:
        t = await _task_for_update(conn, task_id)
        _editable(t)
        if not t["restricted_zone"]:
            raise HTTPException(409, "Lokationen ligger ikke i en restriktionszone")
        await conn.execute("update hojde_tasks set permit_registered_at = now() where id = %s", (task_id,))
        await conn.execute("""update hojde_checklist_items set done_at = now(), done_by = %s
                              where task_id = %s and key = %s""", (ctx.staff.id, task_id, rules.ZONE_PERMIT_KEY))
        await audit(conn, "update", **_who(ctx), table="hojde_tasks", row_id=task_id,
                    before={"permit_registered_at": t["permit_registered_at"]}, after={"permit_registered": True},
                    member_id=ctx.staff.id)
        return await task_detail(conn, task_id)


@router.post("/tasks/{task_id}/ready")
async def mark_ready(task_id: int, ctx: HojdeContext = Depends(require_staff("pilot"))):
    async with db.connection() as conn:
        t = await _task_for_update(conn, task_id)
        if t["status"] != "forberedelse":
            raise HTTPException(409, "Kun opgaver i forberedelse kan markeres klar")
        r = await ops.task_readiness(conn, task_id)
        if not r.ready:
            raise HTTPException(409, r.message)
        if t["pilot_id"] is None:
            raise HTTPException(409, "Vælg en pilot først")
        await conn.execute("""update hojde_tasks set status = 'klar', phase = 'flyvning', ready_at = now(), ready_by = %s
                              where id = %s""", (ctx.staff.id, task_id))
        await audit(conn, "update", **_who(ctx), table="hojde_tasks", row_id=task_id, before={"status": t["status"]},
                    after={"status": "klar"}, member_id=ctx.staff.id)
        await webhooks.emit(conn, "hojde.task.ready", {"task_id": task_id, "order_id": t["order_id"]})
        return await task_detail(conn, task_id)


class RescheduleIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    scheduled_at: datetime
    reason: Literal["vejr", "andet"]
    note: str = Field("", max_length=1000)


@router.post("/tasks/{task_id}/reschedule")
async def reschedule(task_id: int, body: RescheduleIn, ctx: HojdeContext = Depends(require_staff())):
    if body.scheduled_at.tzinfo is None or body.scheduled_at <= _now():
        raise HTTPException(422, "Vælg et tidspunkt i fremtiden")
    async with db.connection() as conn:
        t = await _task_for_update(conn, task_id)
        _editable(t)
        order_to = ops.transition(t["order_status"], "schedule")
        await conn.execute("""update hojde_tasks set scheduled_at = %s, status = 'forberedelse', phase = 'forberedelse',
                              ready_at = null where id = %s""", (body.scheduled_at, task_id))
        await conn.execute("""update hojde_orders set scheduled_at = %s, status = %s, access_confirmed_at = null
                              where id = %s""", (body.scheduled_at, order_to, t["order_id"]))
        await conn.execute("""update hojde_checklist_items set done_at = null, done_by = null
                              where task_id = %s and key = 'access'""", (task_id,))
        await audit(conn, "update", **_who(ctx), table="hojde_tasks", row_id=task_id,
                    before={"scheduled_at": t["scheduled_at"], "status": t["status"]},
                    after={"scheduled_at": body.scheduled_at, "status": "forberedelse"}, reason=body.reason,
                    note_length=len(body.note), member_id=ctx.staff.id)
        if order_to != t["order_status"]:
            await audit(conn, "update", **_who(ctx), table="hojde_orders", row_id=t["order_id"],
                        before={"status": t["order_status"]}, after={"status": order_to}, reason="rescheduled")
        return await task_detail(conn, task_id)


class FlightIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    started_at: datetime
    sorties: int = Field(ge=1, le=50)
    minutes_per_sortie: int = Field(ge=1, le=120)
    wind_ms: float = Field(ge=0, le=40)
    battery_ids: list[int] = Field(default_factory=list, max_length=20)
    incident: str | None = Field(None, max_length=500)


@router.post("/tasks/{task_id}/flights", status_code=201)
async def log_flight(task_id: int, body: FlightIn, ctx: HojdeContext = Depends(require_staff("pilot"))):
    if body.started_at.tzinfo is None:
        raise HTTPException(422, "Tidspunktet skal have en tidszone")
    async with db.connection() as conn:
        t = await _task_for_update(conn, task_id)
        if t["status"] not in ("klar", "floejet"):
            raise HTTPException(409, "Opgaven skal være markeret klar, før en flyvning logges")
        if t["drone_id"] is None or t["pilot_id"] is None:
            raise HTTPException(409, "Opgaven mangler pilot eller drone")
        batteries = sorted(set(body.battery_ids))
        if batteries:
            n = (await db.fetch_one(conn, "select count(*) as n from hojde_equipment where kind = 'batteri' and id = any(%s)",
                                    (batteries,)))["n"]
            if n != len(batteries):
                raise HTTPException(422, "Ukendt batteri")
        number = await ops.next_flight_number(conn)
        flight = await db.fetch_one(conn, """
            insert into hojde_flights (number, task_id, location_id, pilot_id, drone_id, battery_ids, started_at, sorties,
                                       minutes_per_sortie, wind_ms, incident)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning id""",
            (number, task_id, t["location_id"], t["pilot_id"], t["drone_id"], batteries, body.started_at, body.sorties,
             body.minutes_per_sortie, body.wind_ms, body.incident or None))
        await audit(conn, "create", **_who(ctx), table="hojde_flights", row_id=flight["id"],
                    after={"number": number, "task_id": task_id, "sorties": body.sorties, "incident": bool(body.incident)},
                    member_id=ctx.staff.id)
        minutes = body.sorties * body.minutes_per_sortie
        await conn.execute("update hojde_equipment set usage_minutes = usage_minutes + %s where id = %s",
                           (minutes, t["drone_id"]))
        await audit(conn, "update", **_who(ctx), table="hojde_equipment", row_id=t["drone_id"],
                    after={"usage_minutes": f"+{minutes}"}, flight=number)
        for b in batteries:
            await conn.execute("update hojde_equipment set cycles = coalesce(cycles, 0) + %s where id = %s",
                               (body.sorties, b))
            await audit(conn, "update", **_who(ctx), table="hojde_equipment", row_id=b,
                        after={"cycles": f"+{body.sorties}"}, flight=number)
        if t["status"] != "floejet":
            await conn.execute("update hojde_tasks set status = 'floejet', phase = 'data' where id = %s", (task_id,))
            await audit(conn, "update", **_who(ctx), table="hojde_tasks", row_id=task_id, before={"status": t["status"]},
                        after={"status": "floejet"}, flight=number)
        out = flight_item(await db.fetch_one(conn, f"{FLIGHT_SELECT} where f.id = %s", (flight["id"],)))
    await events.emit("hojde.flight.logged", ref=str(flight["id"]), value=minutes)
    return out


@router.post("/tasks/{task_id}/deliver")
async def deliver(task_id: int, ctx: HojdeContext = Depends(require_staff("analytiker"))):
    """Stand-in for report publishing (P4): the visit is delivered to the customer."""
    async with db.connection() as conn:
        t = await _task_for_update(conn, task_id)
        if t["status"] != "floejet":
            raise HTTPException(409, "Kun fløjne opgaver kan leveres")
        tasks = (await db.fetch_one(conn, "select count(*) as n from hojde_tasks where order_id = %s", (t["order_id"],)))["n"]
        last_visit = t["frequency"] != "abonnement" or (t["visits"] or 0) <= tasks
        await conn.execute("update hojde_tasks set status = 'leveret', phase = 'leverance' where id = %s", (task_id,))
        await audit(conn, "update", **_who(ctx), table="hojde_tasks", row_id=task_id, before={"status": "floejet"},
                    after={"status": "leveret"}, member_id=ctx.staff.id)
        if last_visit:
            to = ops.transition(t["order_status"], "deliver")
            await conn.execute("update hojde_orders set status = %s, delivered_at = now() where id = %s", (to, t["order_id"]))
            await audit(conn, "update", **_who(ctx), table="hojde_orders", row_id=t["order_id"],
                        before={"status": t["order_status"]}, after={"status": to})
        await webhooks.emit(conn, "hojde.task.delivered", {"task_id": task_id, "order_id": t["order_id"]})
        return await task_detail(conn, task_id)


# ── Equipment ───────────────────────────────────────────────────────────────────────────────────────────────────────

@router.get("/equipment")
async def equipment(ctx: HojdeContext = Depends(require_staff())):
    async with db.connection() as conn:
        rows = await db.fetch_all(conn, "select * from hojde_equipment order by sort, name")
    return [equipment_item(e) for e in rows]


class EquipmentIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    kind: Literal["drone", "batteri", "andet"]
    model: str = Field(min_length=1, max_length=100)
    serial: str = Field("", max_length=100)
    c_class: Literal["C0", "C1", "C2", "C3", "C4"] | None = None
    next_service: str = Field("", max_length=100)


@router.post("/equipment", status_code=201)
async def create_equipment(body: EquipmentIn, ctx: HojdeContext = Depends(require_staff("pilot"))):
    async with db.connection() as conn:
        row = await db.fetch_one(conn, """
            insert into hojde_equipment (name, kind, model, serial, c_class, next_service, cycles, sort)
            values (%s, %s, %s, %s, %s, %s, %s, (select coalesce(max(sort), 0) + 1 from hojde_equipment))
            returning *""",
            (body.name, body.kind, body.model, body.serial, body.c_class, body.next_service,
             0 if body.kind == "batteri" else None))
        await audit(conn, "create", **_who(ctx), table="hojde_equipment", row_id=row["id"],
                    after={"name": row["name"], "kind": row["kind"], "model": row["model"]}, member_id=ctx.staff.id)
    return equipment_item(row)


class EquipmentStatusIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["klar", "til_kontrol", "til_service"]


@router.patch("/equipment/{equipment_id}")
async def update_equipment(equipment_id: int, body: EquipmentStatusIn, ctx: HojdeContext = Depends(require_staff("pilot"))):
    async with db.connection() as conn:
        e = await db.fetch_one(conn, "select status from hojde_equipment where id = %s for update", (equipment_id,))
        if e is None:
            raise HTTPException(404, "Udstyret findes ikke")
        row = await db.fetch_one(conn, "update hojde_equipment set status = %s where id = %s returning *",
                                 (body.status, equipment_id))
        if e["status"] != body.status:
            await audit(conn, "update", **_who(ctx), table="hojde_equipment", row_id=equipment_id,
                        before={"status": e["status"]}, after={"status": body.status}, member_id=ctx.staff.id)
    return equipment_item(row)


# ── Flight log and compliance ───────────────────────────────────────────────────────────────────────────────────────

@router.get("/compliance")
async def compliance(ctx: HojdeContext = Depends(require_staff())):
    now = _now()
    async with db.connection() as conn:
        flights = await db.fetch_all(conn, f"{FLIGHT_SELECT} order by f.started_at desc limit 200")
        incidents = (await db.fetch_one(conn, "select count(*) as n from hojde_flights where incident is not null"))["n"]
        docs = await db.fetch_all(conn, """select d.id, d.kind, d.title, d.reference, d.expires_at, m.name as holder
                                           from hojde_compliance_documents d left join hojde_members m on m.id = d.holder_id
                                           order by d.kind, d.created_at""")
    return {
        "flights": [flight_item(f) for f in flights],
        "documents": [{"id": d["id"], "kind": d["kind"],
                       "title": f"{d['holder']} · {d['title']}" if d["holder"] else d["title"],
                       "reference": d["reference"], "expires_at": _iso(d["expires_at"]),
                       **{"state": rules.compliance_state(d["expires_at"], now)}} for d in docs],
        "incidents": incidents,
    }
