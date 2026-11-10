"""Højde customer portal API (/api/hojde/portal): overview, locations, the service catalogue, orders and the order
wizard, and the organisation (users, invitations, settings).

Everything is scoped to the caller's organisation (app/hojde/access.py), and customer users limited to selected
locations only see those — other rows answer 404. Ordering, creating locations, approving quotes and cancelling need
the right to order; the organisation is for customer admins. Every change is audited in the same transaction.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app import db, events, webhooks
from app.hojde import invitations, ops, rules
from app.hojde.access import HojdeContext, Membership, customer_admin_of, customer_of, require_customer
from app.logs import audit, changed
from app.security import EMAIL_RE

router = APIRouter(prefix="/api/hojde/portal", tags=["hojde"])

LocationType = Literal["bygning", "byggeplads", "omraade"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ordering(ctx: HojdeContext, message: str) -> Membership:
    m = customer_of(ctx)
    if not rules.can_order(m.roles, m.may_order):
        raise HTTPException(403, message)
    return m


def _scope(m: Membership, alias: str = "l") -> tuple[str, dict]:
    """SQL condition on hojde_locations `alias`: the member's organisation, and their locations if limited."""
    limited = not rules.is_customer_admin(m.roles) and m.location_scope == "udvalgte"
    sql = f"{alias}.org_id = %(org)s" + (f" and {alias}.id = any(%(locs)s)" if limited else "")
    return sql, {"org": m.org_id, "locs": list(m.location_ids)}


def _iso(v):
    return v.isoformat() if v else None


def _lower_first(s: str) -> str:
    """"Inspektion" → "inspektion", but "3D-model" stays."""
    return s[0].lower() + s[1:] if len(s) > 1 and s[1] == s[1].lower() else s


def _day_month(at: datetime) -> str:
    return at.astimezone(rules.TIME_ZONE).strftime("%d.%m")


# ── Rows → JSON ─────────────────────────────────────────────────────────────────────────────────────────────────────

ORDER_SELECT = """
    select o.id, o.number, o.status, o.frequency, o.visits, o.scheduled_at, o.quote_ore, o.quote_sent_at,
           o.access_confirmed_at, o.delivered_at, o.created_at, o.subject,
           l.id as location_id, l.name as location_name,
           s.id as service_id, s.title as service_title, s.line as service_line, s.short_label,
           (select p.name from hojde_tasks t left join hojde_members p on p.id = t.pilot_id
            where t.order_id = o.id order by t.scheduled_at desc limit 1) as pilot
    from hojde_orders o join hojde_locations l on l.id = o.location_id join hojde_services s on s.id = o.service_id"""


def order_item(o: dict, now: datetime) -> dict:
    return {
        "id": o["id"], "number": o["number"],
        "location": {"id": o["location_id"], "name": o["location_name"]},
        "service": {"id": o["service_id"], "title": o["service_title"], "line": o["service_line"],
                    "short_label": o["short_label"]},
        "status": o["status"], "frequency": o["frequency"], "visits": o["visits"],
        "scheduled_at": _iso(o["scheduled_at"]), "pilot": o["pilot"], "quote_ore": o["quote_ore"],
        "access_confirmed_at": _iso(o["access_confirmed_at"]), "created_at": _iso(o["created_at"]),
        "can_cancel": rules.customer_can_cancel(o["status"], o["scheduled_at"], now),
    }


async def _orders(conn, m: Membership, extra: str = "", params: dict | None = None, order_by: str = "") -> list[dict]:
    scope, p = _scope(m)
    rows = await db.fetch_all(conn, f"{ORDER_SELECT} where {scope} {extra} {order_by}", {**p, **(params or {})})
    now = _now()
    return [order_item(r, now) for r in rows]


async def _order_for_update(conn, m: Membership, order_id: int) -> dict:
    scope, p = _scope(m)
    row = await db.fetch_one(conn, f"""select o.* from hojde_orders o join hojde_locations l on l.id = o.location_id
                                      where o.id = %(id)s and {scope} for update of o""", {**p, "id": order_id})
    if row is None:
        raise HTTPException(404, "Bestillingen findes ikke")
    return row


async def _order_out(conn, m: Membership, order_id: int) -> dict:
    return (await _orders(conn, m, "and o.id = %(id)s", {"id": order_id}))[0]


def location_item(l: dict) -> dict:
    return {k: l[k] for k in ("id", "name", "type", "address", "lat", "lng", "contact_name", "contact_phone",
                              "access_notes", "restricted_zone")}


def finding_item(f: dict) -> dict:
    return {"id": f["id"], "number": f["number"], "title": f["title"], "note": f["note"], "severity": f["severity"],
            "status": f["status"], "confidence": f["confidence"], "owner": f["owner"], "change": f["change"],
            "visit_date": _iso(f["visit_date"]), "order_number": f["order_number"]}


VISIBLE = "f.qc_state in ('godkendt', 'rettet')"   # rules.visible_to_customer
OPEN = "f.status in ('ny', 'planlagt')"


def _severity_counts(rows) -> dict:
    out = {"kritisk": 0, "moderat": 0, "lav": 0}
    for r in rows:
        out[r["severity"]] += r.get("n", 1)
    return out


# ── Overview ────────────────────────────────────────────────────────────────────────────────────────────────────────

@router.get("/overview")
async def overview(ctx: HojdeContext = Depends(require_customer)):
    m = customer_of(ctx)
    scope, p = _scope(m)
    now = _now()
    year_start = datetime(now.astimezone(rules.TIME_ZONE).year, 1, 1, tzinfo=rules.TIME_ZONE)
    async with db.connection() as conn:
        locs = await db.fetch_all(conn, f"select created_at from hojde_locations l where {scope}", p)
        open_findings = await db.fetch_all(conn, f"""select f.severity, f.visit_date from hojde_findings f
                                                    join hojde_locations l on l.id = f.location_id
                                                    where {scope} and {VISIBLE} and {OPEN}""", p)
        resolved = await db.fetch_all(conn, f"""select f.resolved_at from hojde_findings f
                                               join hojde_locations l on l.id = f.location_id
                                               where {scope} and {VISIBLE} and f.status = 'udbedret'""", p)
        upcoming = await db.fetch_all(conn, f"""{ORDER_SELECT} where {scope} and o.status not in ('leveret', 'aflyst')
                                               order by o.scheduled_at nulls last, o.created_at""", p)
        delivered = await db.fetch_all(conn, f"""{ORDER_SELECT} where {scope} and o.status = 'leveret'
                                                order by coalesce(o.delivered_at, o.scheduled_at, o.created_at) desc
                                                limit 3""", p)
    critical = [f for f in open_findings if f["severity"] == "kritisk"]
    flights = [o for o in upcoming if o["scheduled_at"] and o["scheduled_at"] > now
               and o["status"] in ("planlagt", "vejrforbehold")]
    flights.sort(key=lambda o: o["scheduled_at"])
    actions = []
    for o in upcoming:
        if o["status"] == "tilbud_sendt":
            actions.append({"kind": "approve_quote", "order_id": o["id"],
                            "text": f"Tilbud på {_lower_first(o['short_label'])} af {o['location_name']} "
                                    f"venter på din godkendelse."})
        elif (o["scheduled_at"] and not o["access_confirmed_at"] and now < o["scheduled_at"] < now + timedelta(days=7)
              and o["status"] in ("planlagt", "vejrforbehold")):
            deadline = _day_month(rules.weather_notice_deadline(o["scheduled_at"]))
            actions.append({"kind": "confirm_access", "order_id": o["id"],
                            "text": f"Bekræft adgang til {o['location_name']} inden {deadline}, så flyvningen kan "
                                    f"gennemføres."})
    return {
        "first_name": m.name.split(" ")[0],
        "can_order": rules.can_order(m.roles, m.may_order),
        "stats": {
            "locations": len(locs),
            "locations_this_year": sum(1 for l in locs if l["created_at"] >= year_start),
            "critical_findings": len(critical),
            "critical_since_last_week": sum(1 for f in critical if now - f["visit_date"] < timedelta(days=7)),
            "resolved_findings": len(resolved),
            "resolved_last_quarter": sum(1 for f in resolved if f["resolved_at"]
                                         and now - f["resolved_at"] < timedelta(days=91)),
            "next_flight": {"at": _iso(flights[0]["scheduled_at"]), "location": flights[0]["location_name"]}
            if flights else None,
        },
        "actions": actions,
        "deliveries": [{"order_id": o["id"], "label": o["short_label"],
                        "title": f"{o['location_name']} · {o['subject']}" if o["subject"] else o["location_name"],
                        "date": _iso(o["delivered_at"] or o["scheduled_at"] or o["created_at"])} for o in delivered],
        "open_findings": _severity_counts(open_findings),
        "upcoming": [order_item(o, now) for o in flights[:5]],
    }


# ── Locations ───────────────────────────────────────────────────────────────────────────────────────────────────────

class LocationIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=200)
    type: LocationType
    address: str = Field(min_length=1, max_length=300)
    contact_name: str = Field("", max_length=200)
    contact_phone: str = Field("", max_length=40)
    access_notes: str = Field("", max_length=2000)


async def _create_location(conn, ctx: HojdeContext, m: Membership, body: LocationIn) -> dict:
    row = await db.fetch_one(conn, """
        insert into hojde_locations (org_id, name, type, address, contact_name, contact_phone, access_notes)
        values (%s, %s, %s, %s, %s, %s, %s) returning *""",
        (m.org_id, body.name, body.type, body.address, body.contact_name, body.contact_phone, body.access_notes))
    await audit(conn, "create", actor_id=ctx.principal.user_id, meta=ctx.principal.meta, table="hojde_locations",
                row_id=row["id"], after={"name": row["name"], "type": row["type"]}, member_id=m.id)
    return row


@router.get("/locations")
async def locations(q: str = Query("", max_length=100), type: str = Query("", max_length=20),
                    ctx: HojdeContext = Depends(require_customer)):
    m = customer_of(ctx)
    scope, p = _scope(m)
    where = [scope]
    if q.strip():
        where.append("(l.name ilike %(q)s or l.address ilike %(q)s)")
        p["q"] = "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    if type in rules.LOCATION_TYPES:
        where.append("l.type = %(type)s")
        p["type"] = type
    now = _now()
    async with db.connection() as conn:
        total = (await db.fetch_one(conn, f"select count(*) as n from hojde_locations l where {scope}", p))["n"]
        rows = await db.fetch_all(conn, f"""
            select l.*,
                   (select max(coalesce(o.scheduled_at, o.delivered_at)) from hojde_orders o
                    where o.location_id = l.id and o.status = 'leveret') as last_visit,
                   (select min(o.scheduled_at) from hojde_orders o where o.location_id = l.id
                    and o.status not in ('leveret', 'aflyst') and o.scheduled_at > %(now)s) as next_visit
            from hojde_locations l where {' and '.join(where)}""", {**p, "now": now})
        counts = await db.fetch_all(conn, f"""
            select f.location_id, f.severity, count(*) as n from hojde_findings f
            join hojde_locations l on l.id = f.location_id
            where {scope} and {VISIBLE} and {OPEN} group by f.location_id, f.severity""", p)
    items = []
    for r in rows:
        items.append({**location_item(r), "last_visit": _iso(r["last_visit"]), "next_visit": _iso(r["next_visit"]),
                      "open_findings": _severity_counts([c for c in counts if c["location_id"] == r["id"]])})
    # Most findings first, as on the screen.
    items.sort(key=lambda i: (-i["open_findings"]["kritisk"], -i["open_findings"]["moderat"], i["name"].lower()))
    return {"total": total, "items": items}


@router.post("/locations", status_code=201)
async def create_location(body: LocationIn, ctx: HojdeContext = Depends(require_customer)):
    m = _ordering(ctx, "Din bruger må ikke oprette lokationer")
    async with db.connection() as conn:
        return location_item(await _create_location(conn, ctx, m, body))


@router.get("/locations/{location_id}")
async def location(location_id: int, ctx: HojdeContext = Depends(require_customer)):
    m = customer_of(ctx)
    scope, p = _scope(m)
    async with db.connection() as conn:
        loc = await db.fetch_one(conn, f"select l.* from hojde_locations l where l.id = %(id)s and {scope}",
                                 {**p, "id": location_id})
        if loc is None:
            raise HTTPException(404, "Lokationen findes ikke")
        findings = await db.fetch_all(conn, f"""select f.* from hojde_findings f where f.location_id = %s and {VISIBLE}
                                               order by f.visit_date desc, f.number""", (location_id,))
        orders = await _orders(conn, m, "and o.location_id = %(loc)s", {"loc": location_id},
                               "order by o.created_at desc")
        delivered = await db.fetch_all(conn, """
            select o.number, coalesce(o.scheduled_at, o.delivered_at, o.created_at) as date, s.title
            from hojde_orders o join hojde_services s on s.id = o.service_id
            where o.location_id = %s and o.status = 'leveret'""", (location_id,))
    visits = [{"date": _iso(o["date"]), "service": o["title"], "order_number": o["number"],
               "findings": sum(1 for f in findings if f["order_number"] == o["number"])} for o in delivered]
    # Earlier visits known only from their findings (history from before the platform).
    earlier: dict[datetime, int] = {}
    for f in findings:
        if not f["order_number"]:
            earlier[f["visit_date"]] = earlier.get(f["visit_date"], 0) + 1
    visits += [{"date": _iso(d), "service": "Besøg", "order_number": None, "findings": n} for d, n in earlier.items()]
    visits.sort(key=lambda v: v["date"], reverse=True)
    return {"location": location_item(loc), "visits": visits, "first_visit": visits[-1]["date"] if visits else None,
            "findings": [finding_item(f) for f in findings], "orders": orders}


# ── Catalogue and orders ────────────────────────────────────────────────────────────────────────────────────────────

@router.get("/services")
async def services(ctx: HojdeContext = Depends(require_customer)):
    customer_of(ctx)
    async with db.connection() as conn:
        rows = await db.fetch_all(conn, """select id, key, line, title, short_label, description, specs, price_from_ore,
                                                  price_unit, industry, equipment, permit_class, needs_quote
                                           from hojde_services where active order by sort, id""")
    return rows


@router.get("/orders")
async def orders(ctx: HojdeContext = Depends(require_customer)):
    m = customer_of(ctx)
    async with db.connection() as conn:
        items = await _orders(conn, m, order_by="order by o.scheduled_at nulls last, o.created_at desc")
    upcoming = [o for o in items if rules.is_upcoming(o["status"])]
    past = sorted((o for o in items if not rules.is_upcoming(o["status"])),
                  key=lambda o: o["scheduled_at"] or o["created_at"], reverse=True)
    return {"upcoming": upcoming, "past": past,
            "subscriptions": sum(1 for o in upcoming if o["frequency"] == "abonnement")}


class OrderIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    service_id: int
    location_id: int | None = None
    new_location: LocationIn | None = None     # "Ny lokation" in the wizard
    contact_name: str = Field(min_length=1, max_length=200)
    contact_phone: str = Field("", max_length=40)
    access_notes: str = Field("", max_length=2000)
    frequency: Literal["enkelt", "abonnement"] = "enkelt"
    visits: int | None = Field(None, ge=2, le=52)
    preferred_from: date
    preferred_to: date
    time_of_day: Literal["hele_dagen", "formiddag", "eftermiddag"] = "hele_dagen"
    subject: str = Field("", max_length=200)
    notes: str = Field("", max_length=4000)
    report_recipient: str = Field("", max_length=200)

    @model_validator(mode="after")
    def check(self):
        if (self.location_id is None) == (self.new_location is None):
            raise ValueError("Vælg en lokation eller opret en ny")
        if self.preferred_to < self.preferred_from:
            raise ValueError("Senest skal være efter tidligst")
        if self.frequency == "abonnement" and self.visits is None:
            raise ValueError("Angiv antal besøg")
        if self.frequency == "enkelt":
            self.visits = None
        return self


@router.post("/orders", status_code=201)
async def create_order(body: OrderIn, ctx: HojdeContext = Depends(require_customer)):
    m = _ordering(ctx, "Din bruger må ikke bestille opgaver")
    if body.preferred_from < datetime.now(rules.TIME_ZONE).date():
        raise HTTPException(422, "Tidligst kan ikke ligge før i dag")
    async with db.connection() as conn:
        service = await db.fetch_one(conn, "select id, key from hojde_services where id = %s and active",
                                     (body.service_id,))
        if service is None:
            raise HTTPException(422, "Ydelsen findes ikke")
        if body.new_location is not None:
            location_id = (await _create_location(conn, ctx, m, body.new_location))["id"]
        else:
            scope, p = _scope(m)
            loc = await db.fetch_one(conn, f"select l.id from hojde_locations l where l.id = %(id)s and {scope}",
                                     {**p, "id": body.location_id})
            if loc is None:
                raise HTTPException(404, "Lokationen findes ikke")
            location_id = loc["id"]
        number = await ops.next_order_number(conn)
        row = await db.fetch_one(conn, """
            insert into hojde_orders (number, org_id, location_id, service_id, status, frequency, visits, preferred_from,
                                      preferred_to, time_of_day, contact_name, contact_phone, access_notes, subject,
                                      notes, report_recipient, created_by)
            values (%s, %s, %s, %s, 'afventer_godkendelse', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            returning id""",
            (number, m.org_id, location_id, service["id"], body.frequency, body.visits, body.preferred_from,
             body.preferred_to, body.time_of_day, body.contact_name, body.contact_phone, body.access_notes,
             body.subject, body.notes, body.report_recipient, m.id))
        await audit(conn, "create", actor_id=ctx.principal.user_id, meta=ctx.principal.meta, table="hojde_orders",
                    row_id=row["id"], after={"number": number, "service": service["key"], "location_id": location_id,
                                             "frequency": body.frequency}, member_id=m.id)
        await webhooks.emit(conn, "hojde.order.created", {"order_id": row["id"], "organization_id": m.org_id})
        out = await _order_out(conn, m, row["id"])
    await events.emit("hojde.order.created", ref=str(row["id"]))
    return out


async def _change_order(ctx: HojdeContext, m: Membership, order_id: int, action: str, extra_sql: str = "",
                        extra: tuple = (), webhook: str | None = None) -> dict:
    """Moves an order through the status flow (409 when not allowed), audits it and emits the webhook."""
    async with db.connection() as conn:
        order = await _order_for_update(conn, m, order_id)
        to = ops.transition(order["status"], action)
        await conn.execute(f"update hojde_orders set status = %s{extra_sql} where id = %s", (to, *extra, order_id))
        await audit(conn, "update", actor_id=ctx.principal.user_id, meta=ctx.principal.meta, table="hojde_orders",
                    row_id=order_id, before={"status": order["status"]}, after={"status": to}, step=action,
                    member_id=m.id)
        if webhook:
            await webhooks.emit(conn, webhook, {"order_id": order_id, "organization_id": m.org_id})
        return await _order_out(conn, m, order_id)


@router.post("/orders/{order_id}/approve")
async def approve_quote(order_id: int, ctx: HojdeContext = Depends(require_customer)):
    m = _ordering(ctx, "Din bruger må ikke godkende tilbud")
    return await _change_order(ctx, m, order_id, "approve_quote", ", quote_approved_at = now(), quote_approved_by = %s",
                               (m.id,), webhook="hojde.quote.approved")


@router.post("/orders/{order_id}/cancel")
async def cancel_order(order_id: int, ctx: HojdeContext = Depends(require_customer)):
    m = _ordering(ctx, "Din bruger må ikke aflyse bestillinger")
    async with db.connection() as conn:
        order = await _order_for_update(conn, m, order_id)
        if not rules.customer_can_cancel(order["status"], order["scheduled_at"], _now()):
            raise HTTPException(409, "Bestillingen kan kun aflyses frem til 24 timer før planlagt flyvning")
        to = ops.transition(order["status"], "cancel")
        removed = await db.fetch_all(conn, """delete from hojde_tasks where order_id = %s
                                              and status in ('forberedelse', 'klar', 'vejrforbehold')
                                              returning id, number""", (order_id,))
        for t in removed:
            await audit(conn, "delete", actor_id=ctx.principal.user_id, meta=ctx.principal.meta, table="hojde_tasks",
                        row_id=t["id"], before={"number": t["number"]}, reason="order_cancelled")
        await conn.execute("update hojde_orders set status = %s, cancelled_at = now() where id = %s", (to, order_id))
        await audit(conn, "update", actor_id=ctx.principal.user_id, meta=ctx.principal.meta, table="hojde_orders",
                    row_id=order_id, before={"status": order["status"]}, after={"status": to}, step="cancel",
                    member_id=m.id)
        await webhooks.emit(conn, "hojde.order.cancelled", {"order_id": order_id, "organization_id": m.org_id})
        return await _order_out(conn, m, order_id)


@router.post("/orders/{order_id}/confirm-access")
async def confirm_access(order_id: int, ctx: HojdeContext = Depends(require_customer)):
    m = customer_of(ctx)
    async with db.connection() as conn:
        order = await _order_for_update(conn, m, order_id)
        if order["status"] in ("leveret", "aflyst"):
            raise HTTPException(409, "Bestillingen er afsluttet")
        if order["access_confirmed_at"] is None:
            await conn.execute("update hojde_orders set access_confirmed_at = now() where id = %s", (order_id,))
            await conn.execute("""update hojde_checklist_items c set done_at = now(), done_by = %s
                                  from hojde_tasks t where t.id = c.task_id and t.order_id = %s
                                  and c.key = 'access' and c.done_at is null""", (m.id, order_id))
            await audit(conn, "update", actor_id=ctx.principal.user_id, meta=ctx.principal.meta, table="hojde_orders",
                        row_id=order_id, before={"access_confirmed_at": None}, after={"access_confirmed_at": "now"},
                        step="confirm_access", member_id=m.id)
        return await _order_out(conn, m, order_id)


# ── Organisation (customer admins) ──────────────────────────────────────────────────────────────────────────────────

async def _organization(conn, ctx: HojdeContext, m: Membership) -> dict:
    org = await db.fetch_one(conn, "select id, name, cvr, billing_address, ean, require_2fa from hojde_organizations "
                                   "where id = %s", (m.org_id,))
    members = await db.fetch_all(conn, """
        select h.id, h.name, h.email, h.roles, h.location_scope, h.location_ids, h.may_order, h.status,
               h.invitation_sent_at, h.user_id,
               case when h.user_id is null then null else
                   exists (select 1 from passkeys k where k.user_id = h.user_id)
                   or exists (select 1 from totp_factors t where t.user_id = h.user_id and t.confirmed_at is not null)
               end as two_factor
        from hojde_members h where h.org_id = %s and h.kind = 'customer' and h.anonymised_at is null
        order by h.created_at, h.id""", (m.org_id,))
    locs = await db.fetch_all(conn, "select id, name from hojde_locations where org_id = %s order by name", (m.org_id,))
    names = {l["id"]: l["name"] for l in locs}
    out = []
    for r in members:
        admin = rules.is_customer_admin(r["roles"])
        out.append({
            "id": r["id"], "name": r["name"], "email": r["email"], "roles": r["roles"],
            "role_labels": [rules.ROLE_LABEL[x] for x in r["roles"]],
            "location_scope": "alle" if admin else r["location_scope"],
            "location_names": [names[i] for i in r["location_ids"] if i in names],
            "may_order": rules.can_order(r["roles"], r["may_order"]),
            "two_factor": r["two_factor"], "status": r["status"],
            "invitation_expires_at": _iso(rules.invitation_expires_at(r["invitation_sent_at"]))
            if r["status"] == "inviteret" and r["invitation_sent_at"] else None,
            "is_me": r["id"] == m.id,
        })
    return {"organization": org, "members": out, "locations": locs}


@router.get("/organization")
async def organization(ctx: HojdeContext = Depends(require_customer)):
    m = customer_admin_of(ctx)
    async with db.connection() as conn:
        return await _organization(conn, ctx, m)


class OrganizationIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    cvr: str | None = Field(None, pattern=r"^([0-9]{8})?$")
    billing_address: str | None = Field(None, max_length=300)
    ean: str | None = Field(None, pattern=r"^([0-9]{13})?$")
    require_2fa: bool | None = None


@router.patch("/organization")
async def update_organization(body: OrganizationIn, ctx: HojdeContext = Depends(require_customer)):
    m = customer_admin_of(ctx)
    fields = {k: (v or None) if k != "require_2fa" else v for k, v in body.model_dump().items()
              if k in body.model_fields_set and not (k == "require_2fa" and v is None)}
    if fields.get("require_2fa") and not (ctx.has_factor and ctx.mfa_proven):
        raise HTTPException(409, "Tilføj og brug en passkey, sikkerhedsnøgle eller godkendelsesapp, før du kræver "
                                 "tofaktor for alle")
    async with db.connection() as conn:
        before = await db.fetch_one(conn, "select cvr, billing_address, ean, require_2fa from hojde_organizations "
                                          "where id = %s for update", (m.org_id,))
        if fields:
            sets = ", ".join(f"{k} = %({k})s" for k in fields)
            await conn.execute(f"update hojde_organizations set {sets}, updated_at = now() where id = %(id)s",
                               {**fields, "id": m.org_id})
            b, a = changed(before, {**before, **fields})
            if a:
                await audit(conn, "update", actor_id=ctx.principal.user_id, meta=ctx.principal.meta,
                            table="hojde_organizations", row_id=m.org_id, before=b, after=a, member_id=m.id)
        return await _organization(conn, ctx, m)


class InviteIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    email: str = Field(max_length=320)
    name: str = Field("", max_length=200)
    role: Literal["kundeadministrator", "kundebruger"]
    location_scope: Literal["alle", "udvalgte"] = "alle"
    location_ids: list[int] = Field(default_factory=list, max_length=500)
    may_order: bool = False

    @model_validator(mode="after")
    def check(self):
        self.email = self.email.lower()
        if not EMAIL_RE.fullmatch(self.email):
            raise ValueError("Ugyldig e-mailadresse")
        if self.role == "kundeadministrator":
            self.location_scope, self.location_ids, self.may_order = "alle", [], True
        elif self.location_scope == "udvalgte" and not self.location_ids:
            raise ValueError("Vælg mindst én lokation")
        if self.location_scope == "alle":
            self.location_ids = []
        return self


@router.post("/organization/invitations", status_code=201)
async def invite(body: InviteIn, ctx: HojdeContext = Depends(require_customer)):
    m = customer_admin_of(ctx)
    async with db.connection() as conn:
        if body.location_ids:
            owned = await db.fetch_one(conn, "select count(*) as n from hojde_locations where org_id = %s and id = any(%s)",
                                       (m.org_id, body.location_ids))
            if owned["n"] != len(set(body.location_ids)):
                raise HTTPException(422, "Ukendt lokation")
        existing = await db.fetch_one(conn, """select id, status, roles from hojde_members
                                               where org_id = %s and kind = 'customer' and email = %s for update""",
                                      (m.org_id, body.email))
        if existing and existing["status"] != "deaktiveret":
            raise HTTPException(409, "Personen er allerede bruger eller inviteret")
        values = (body.name or body.email.split("@")[0], [body.role], body.location_scope, sorted(set(body.location_ids)),
                  body.may_order, m.id)
        if existing:
            row = await db.fetch_one(conn, """
                update hojde_members set name = %s, roles = %s, location_scope = %s, location_ids = %s, may_order = %s,
                       invited_by = %s, status = 'inviteret', invitation_sent_at = now(), user_id = null
                where id = %s returning id""", (*values, existing["id"]))
            await audit(conn, "update", actor_id=ctx.principal.user_id, meta=ctx.principal.meta, table="hojde_members",
                        row_id=row["id"], before={"status": existing["status"], "roles": existing["roles"]},
                        after={"status": "inviteret", "roles": [body.role]}, step="invite", member_id=m.id)
        else:
            row = await db.fetch_one(conn, """
                insert into hojde_members (name, roles, location_scope, location_ids, may_order, invited_by, email, kind,
                                           org_id, status, invitation_sent_at)
                values (%s, %s, %s, %s, %s, %s, %s, 'customer', %s, 'inviteret', now()) returning id""",
                (*values, body.email, m.org_id))
            await audit(conn, "create", actor_id=ctx.principal.user_id, meta=ctx.principal.meta, table="hojde_members",
                        row_id=row["id"], after={"kind": "customer", "roles": [body.role], "status": "inviteret"},
                        step="invite", member_id=m.id)
        await invitations.enqueue(conn, row["id"])
        return await _organization(conn, ctx, m)


@router.post("/organization/members/{member_id}/{action}")
async def member_action(member_id: int, action: Literal["resend", "deactivate", "reactivate"],
                        ctx: HojdeContext = Depends(require_customer)):
    m = customer_admin_of(ctx)
    async with db.connection() as conn:
        target = await db.fetch_one(conn, """select id, status, user_id from hojde_members where id = %s and org_id = %s
                                             and kind = 'customer' and anonymised_at is null for update""",
                                    (member_id, m.org_id))
        if target is None:
            raise HTTPException(404, "Brugeren findes ikke")
        mail = False
        if action == "resend":
            if target["status"] != "inviteret":
                raise HTTPException(409, "Kun invitationer kan sendes igen")
            to, mail = "inviteret", True
            await conn.execute("update hojde_members set invitation_sent_at = now() where id = %s", (member_id,))
        elif action == "deactivate":
            if target["id"] == m.id:
                raise HTTPException(409, "Du kan ikke deaktivere dig selv")
            if target["status"] == "deaktiveret":
                raise HTTPException(409, "Brugeren er allerede deaktiveret")
            to = "deaktiveret"
            await conn.execute("update hojde_members set status = 'deaktiveret' where id = %s", (member_id,))
        else:
            if target["status"] != "deaktiveret":
                raise HTTPException(409, "Brugeren er ikke deaktiveret")
            to = "aktiv" if target["user_id"] else "inviteret"
            mail = to == "inviteret"
            await conn.execute("""update hojde_members set status = %s,
                                  invitation_sent_at = case when %s = 'inviteret' then now() else invitation_sent_at end
                                  where id = %s""", (to, to, member_id))
        await audit(conn, "update", actor_id=ctx.principal.user_id, meta=ctx.principal.meta, table="hojde_members",
                    row_id=member_id, before={"status": target["status"]}, after={"status": to}, step=action,
                    member_id=m.id)
        if mail:
            await invitations.enqueue(conn, member_id)
        return await _organization(conn, ctx, m)
