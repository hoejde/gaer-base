"""Demo tenant for Højde: Boligforeningen Kystparken, the Højde staff and a week of operations, so every P0–P2 screen
has something to show. Dates are relative to today, so the demo never goes stale.

    python -m app.hojde.seed

Replaces ALL Højde data and refuses to run when GAER_ENV=production. Nobody gets a Gær user from here: the demo
people sign in with their e-mail and a code (MAIL_PROVIDER=console writes it to the server log), and their membership
is linked at that first login. Customer admin: mh@kystparken.example · staff: emil@hojde.example, anders@hojde.example.
"""

import asyncio
import sys
from datetime import date, datetime, timedelta, timezone

from app import config, db
from app.hojde import ops, rules
from app.logs import RequestMeta, audit

STAFF_DOMAIN = "hojde.example"
CUSTOMER_DOMAIN = "kystparken.example"

TABLES = ("hojde_checklist_items", "hojde_flights", "hojde_tasks", "hojde_findings", "hojde_orders",
          "hojde_compliance_documents", "hojde_locations", "hojde_members", "hojde_organizations", "hojde_services",
          "hojde_equipment")


class Days:
    def __init__(self, today: date):
        self.today = today

    def __call__(self, offset: int, hour: int, minute: int = 0) -> datetime:
        """Danish local time `offset` days from today."""
        return rules.local_time((self.today + timedelta(days=offset)).isoformat(), hour, minute)


def coordinates_for(lat: float, lng: float, when: datetime, want_ok: bool) -> dict:
    """The stub forecast is deterministic per coordinates and day: nudge a demo location (by metres) until its flight
    lands on the side of the weather rule the screens show."""
    for k in range(400):
        cand = round(lat + k * 0.0001, 4)
        _, verdict = ops.flight_weather(0, cand, lng, when)
        if verdict.ok == want_ok:
            return {"lat": cand, "lng": lng}
    return {"lat": lat, "lng": lng}


async def seed(conn, today: date | None = None, *, meta: RequestMeta | None = None) -> dict:
    meta = meta or RequestMeta()
    at = Days(today or datetime.now(rules.TIME_ZONE).date())

    async def insert(table: str, **values) -> int:
        cols = ", ".join(values)
        marks = ", ".join(["%s"] * len(values))
        row = await db.fetch_one(conn, f"insert into {table} ({cols}) values ({marks}) returning id",
                                 tuple(values.values()))
        return row["id"]

    # ── Reset ────────────────────────────────────────────────────────────────────────────────────────────────────
    removed = {}
    for table in TABLES:
        cur = await conn.execute(f"delete from {table}")
        removed[table] = cur.rowcount

    # ── Service catalogue ────────────────────────────────────────────────────────────────────────────────────────
    svc = {}
    for sort, (key, line, title, short, needs_quote, desc, specs, industry, permit) in enumerate([
        ("bygningsinspektion", "ai", "Bygningsinspektion", "Inspektion", False,
         "Tag- og facadeinspektion med AI-skadesrapport",
         ["Tag og facader i 50 MP", "Prioriteret skadesliste", "Rapport inden for [X] dage"],
         "Bygninger og ejendomme", "A1"),
        ("3d-model", "data", "3D-model af bygning", "3D-model", True, "3D-model og digital tvilling af bygningen",
         ["Måling af afstand og areal", "Ortofoto og punktsky", "Eksport til CAD"], "Bygninger og ejendomme", "A1"),
        ("byggelaan", "drone", "Byggelånsdokumentation", "Fremdrift", True,
         "Byggelåns- og fremdriftsdokumentation med faste fotopunkter",
         ["Faste fotopunkter", "Sammenligning med sidste besøg", "Deling med bank via link"], "Byggeri og anlæg", "A2"),
        ("termografi", "ai", "Termografi", "Termografi", True, "Varmetab, fugt og utætheder med termisk drone",
         ["Termisk kamera", "Varmetab og fugt", "Rapport inden for [X] dage"], "Bygninger og ejendomme", "A2"),
        ("volumen", "data", "Volumen og lagerstatus", "Volumen", True,
         "Volumen og lagerstatus for jord, grus og materialer",
         ["Terrænmodel", "Volumen pr. depot", "Sammenligning over tid"], "Byggeri og anlæg", "A2"),
    ], start=1):
        svc[key] = await insert("hojde_services", key=key, line=line, title=title, short_label=short, sort=sort,
                                needs_quote=needs_quote, description=desc, specs=specs, industry=industry,
                                equipment="Termisk drone" if key == "termografi" else "DJI Mini 5 Pro · C0",
                                permit_class=permit)

    # ── Staff ────────────────────────────────────────────────────────────────────────────────────────────────────
    staff = {}
    for key, name, roles, certs in [("emil", "Emil", ["administrator", "analytiker", "pilot"], "A1/A3, A2"),
                                    ("anders", "Anders", ["pilot"], "A1/A3, A2"),
                                    ("salg", "Kundeansvarlig", ["kundeansvarlig"], "")]:
        staff[key] = await insert("hojde_members", email=f"{key}@{STAFF_DOMAIN}", name=name, kind="staff",
                                  roles=roles, certificates=certs)

    # ── Equipment and compliance ─────────────────────────────────────────────────────────────────────────────────
    drone = await insert("hojde_equipment", name="Drone 1", kind="drone", model="DJI Mini 5 Pro", serial="[SERIENR]",
                         c_class="C0", usage_minutes=38 * 60 + 12, next_service="ved 50 t", sort=1)
    batteries = [await insert("hojde_equipment", name=f"Batteri {i + 1}", kind="batteri",
                              model="Intelligent Flight Battery", serial="[SERIENR]", cycles=cycles, sort=2 + i)
                 for i, cycles in enumerate([41, 47, 52, 57])]
    await insert("hojde_equipment", name="Batteri 5", kind="batteri", model="Intelligent Flight Battery",
                 serial="[SERIENR]", cycles=212, status="til_kontrol", sort=6)
    await insert("hojde_equipment", name="Drone 2", kind="drone", model="DJI Mini 5 Pro", serial="[SERIENR]",
                 c_class="C0", usage_minutes=49 * 60 + 40, next_service="ved 50 t", status="til_service", sort=7)
    await insert("hojde_equipment", name="GNSS-stang", kind="andet", model="[Model]", serial="[SERIENR]",
                 next_service="kalibrering 01.2027", sort=8)

    await insert("hojde_compliance_documents", kind="operatoerregistrering",
                 title="Operatørregistrering hos Trafikstyrelsen", reference="[OPERATØR-ID]")
    await insert("hojde_compliance_documents", kind="forsikring", title="Ansvarsforsikring, erhverv",
                 reference="[POLICE]", expires_at=at(26, 23, 59))
    await insert("hojde_compliance_documents", kind="pilotcertifikat", title="A1/A3 og A2", holder_id=staff["anders"],
                 expires_at=datetime(2030, 6, 30, tzinfo=timezone.utc))
    await insert("hojde_compliance_documents", kind="pilotcertifikat", title="A1/A3 og A2", holder_id=staff["emil"],
                 expires_at=datetime(2030, 3, 31, tzinfo=timezone.utc))

    # ── Boligforeningen Kystparken ───────────────────────────────────────────────────────────────────────────────
    kyst = await insert("hojde_organizations", name="Boligforeningen Kystparken", require_2fa=True,
                        billing_address="Strandvejen 10, 2900 Hellerup")
    vice = {"contact_name": "Jens Pedersen, vicevært", "contact_phone": "+45 20 00 00 00"}
    loc = {
        "c": await insert("hojde_locations", org_id=kyst, name="Kystparken blok C", type="bygning",
                          address="Strandvejen 14, 2900 Hellerup", lat=55.7305, lng=12.5799, **vice,
                          access_notes="Start og landing fra gårdarealet. Beboerne er varslet via opslag.",
                          created_at=at(-590, 9)),
        "b": await insert("hojde_locations", org_id=kyst, name="Kystparken blok B", type="bygning",
                          address="Strandvejen 12, 2900 Hellerup", **coordinates_for(55.7301, 12.5795, at(1, 8), False),
                          **vice, created_at=at(-590, 9)),
        "a": await insert("hojde_locations", org_id=kyst, name="Kystparken blok A", type="bygning",
                          address="Strandvejen 10, 2900 Hellerup", lat=55.7297, lng=12.5791, **vice,
                          created_at=at(-590, 9)),
        "s8": await insert("hojde_locations", org_id=kyst, name="Strandvejen 8", type="bygning",
                           address="Strandvejen 8, 2900 Hellerup", lat=55.7293, lng=12.5788, created_at=at(-120, 9)),
        "p": await insert("hojde_locations", org_id=kyst, name="Fællesareal og p-plads", type="omraade",
                          address="Strandvejen 10-14", lat=55.7300, lng=12.5785, created_at=at(-60, 9)),
    }

    people = {}
    for name, email, role, scope, ids, may_order, status in [
        ("Mette Holm", f"mh@{CUSTOMER_DOMAIN}", "kundeadministrator", "alle", [], True, "aktiv"),
        ("Jens Pedersen", f"jp@{CUSTOMER_DOMAIN}", "kundebruger", "udvalgte", [loc["a"], loc["b"], loc["c"]], True, "aktiv"),
        ("Lars Krogh", "lk@tagfirma.example", "kundebruger", "udvalgte", [loc["c"]], False, "aktiv"),
        ("Sofie Berg", f"sb@{CUSTOMER_DOMAIN}", "kundebruger", "alle", [], True, "inviteret"),
        ("Peter Lund", f"pl@{CUSTOMER_DOMAIN}", "kundebruger", "alle", [], False, "deaktiveret"),
    ]:
        people[name] = await insert("hojde_members", email=email, name=name, kind="customer", org_id=kyst,
                                    roles=[role], location_scope=scope, location_ids=ids, may_order=may_order,
                                    status=status, invited_by=None,
                                    invitation_sent_at=at(-1, 11, 10) if status == "inviteret" else None)
    mette = people["Mette Holm"]

    async def order(number, org, location, service, status, **extra) -> int:
        return await insert("hojde_orders", number=number, org_id=org, location_id=location, service_id=service,
                            status=status, **extra)

    async def task(order_id, location, when, status, phase, pilot) -> int:
        return await insert("hojde_tasks", number=await ops.next_task_number(conn, when), order_id=order_id,
                            location_id=location, scheduled_at=when, status=status, phase=phase, pilot_id=pilot,
                            drone_id=drone, ready_at=when)

    # Delivered history
    delivered = [("B-1031", loc["b"], "bygningsinspektion", at(-32, 9), "tag", staff["anders"]),
                 ("B-1032", loc["s8"], "bygningsinspektion", at(-32, 13), "tag", staff["anders"]),
                 ("B-1036", loc["a"], "3d-model", at(-19, 13, 30), "", staff["anders"]),
                 ("B-1039", loc["c"], "bygningsinspektion", at(-11, 10, 4), "tag og facade", staff["emil"])]
    for number, location, service, when, subject, pilot in delivered:
        oid = await order(number, kyst, location, svc[service], "leveret", subject=subject, scheduled_at=when,
                          delivered_at=when + timedelta(days=3), access_confirmed_at=when,
                          contact_name="Jens Pedersen", created_by=mette, created_at=when - timedelta(days=20))
        await task(oid, location, when, "leveret", "leverance", pilot)

    # Findings: an earlier visit to blok C and the latest (B-1039), approved by Emil
    async def finding(location, visit, number, title, severity, *, status="ny", qc="godkendt", **extra):
        approved = {"approved_by": staff["emil"], "model_version": "tagskade v1.3"} if qc == "godkendt" \
            else {"model_version": "tagskade v1.3"}
        await insert("hojde_findings", location_id=location, visit_date=visit, number=number, title=title,
                     severity=severity, status=status, qc_state=qc, **approved, **extra)

    c_visit = delivered[3][3]
    await finding(loc["c"], at(-224, 10), 1, "Revne i inddækning ved skorsten", "moderat", status="udbedret",
                  resolved_at=at(-150, 12), confidence=0.88)
    await finding(loc["c"], c_visit, 1, "Løs tagsten ved tagfod, nordside", "kritisk", order_number="B-1039",
                  note="Anbefaling: udbedres inden næste storm.", confidence=0.94, change="ny")
    await finding(loc["c"], c_visit, 2, "Revne i inddækning ved skorsten", "moderat", order_number="B-1039",
                  status="planlagt", owner="Jens (vicevært)", confidence=0.86, change="uaendret")
    await finding(loc["c"], c_visit, 3, "Mos og begroning på sydvendt flade", "lav", order_number="B-1039",
                  note="Anbefaling: rens ved næste vedligehold.", confidence=0.81, change="ny")
    for i, (title, severity) in enumerate([("Afskallet puds ved indgang, øst", "moderat"),
                                           ("Tilstoppet tagrende, vestside", "moderat"),
                                           ("Rust på altanværn, 3. sal", "lav"), ("Manglende fuge ved vindue, 2. sal", "lav"),
                                           ("Misfarvning af facadeplader", "lav"),
                                           ("Løs inddækning ved tagvindue", "moderat")]):
        await finding(loc["c"], c_visit, 4 + i, title, severity, order_number="B-1039",
                      confidence=round(0.7 + (i % 3) * 0.08, 2), change="ny")
    for i, title in enumerate(["Revne i tagpap ved ovenlys", "Utæt samling ved kvist"]):
        await finding(loc["b"], delivered[0][3], i + 1, title, "moderat", order_number="B-1031", confidence=0.83)
    for i, title in enumerate(["Mos på nordflade", "Begroning i tagrende", "Afskalning på skorsten",
                               "Løs tagrendekrog", "Misfarvet tagsten"]):
        await finding(loc["s8"], delivered[1][3], i + 1, title, "lav", order_number="B-1032", confidence=0.77)
    for i in range(6):
        await finding(loc["a"], at(-200, 10), i + 1, f"Udbedret skade {i + 1}", "moderat" if i < 2 else "lav",
                      status="udbedret", resolved_at=at(-30 - i * 5, 12), confidence=0.85)
    # Awaiting analyst review: blok B was flown four days ago (FL-0931)
    for i in range(9):
        await finding(loc["b"], at(-4, 9, 12), i + 1, f"AI-fund {i + 1}",
                      "kritisk" if i == 0 else "moderat" if i < 4 else "lav", qc="afventer",
                      confidence=round(0.6 + i * 0.04, 2))

    # Upcoming orders
    contact = {"contact_name": "Jens Pedersen", "contact_phone": "+45 20 00 00 00"}
    b1042 = await order("B-1042", kyst, loc["b"], svc["bygningsinspektion"], "afventer_godkendelse", subject="tag",
                        created_by=mette, created_at=at(-14, 9), **contact)
    b1043 = await order("B-1043", kyst, loc["a"], svc["bygningsinspektion"], "afventer_godkendelse", subject="tag",
                        access_confirmed_at=at(-2, 10), created_by=mette, created_at=at(-14, 9), **contact)
    await order("B-1047", kyst, loc["a"], svc["3d-model"], "tilbud_sendt", quote_sent_at=at(-2, 14),
                contact_name="Jens Pedersen", created_by=mette, created_at=at(-5, 9))

    # ── Other customers in this week's calendar ──────────────────────────────────────────────────────────────────
    byg = await insert("hojde_organizations", name="Demo Bygherre A/S")
    nordhavn = await insert("hojde_locations", org_id=byg, name="Nordhavn byggefelt 7", type="byggeplads",
                            address="Nordhavn, 2150 Nordhavn", **coordinates_for(55.714, 12.597, at(0, 10, 30), True),
                            restricted_zone=True, contact_name="Byggeleder", contact_phone="+45 30 00 00 00")
    sub = await order("B-1018", byg, nordhavn, svc["byggelaan"], "godkendt", frequency="abonnement", visits=12,
                      quote_approved_at=at(-90, 9), report_recipient="Banken via delt link",
                      contact_name="Byggeleder", contact_phone="+45 30 00 00 00", created_at=at(-100, 9))
    ejd = await insert("hojde_organizations", name="Demo Ejendomme")
    valby = await insert("hojde_locations", org_id=ejd, name="Valby Langgade 40", type="bygning",
                         address="Valby Langgade 40, 2500 Valby", lat=55.6648, lng=12.5047)
    valby_order = await order("B-1044", ejd, valby, svc["3d-model"], "godkendt", quote_approved_at=at(-6, 9),
                              access_confirmed_at=at(-1, 9), contact_name="Driftschef", created_at=at(-12, 9))
    grus = await insert("hojde_organizations", name="Demo Grusgrav")
    depot = await insert("hojde_locations", org_id=grus, name="Grusgrav depot nord", type="omraade",
                         address="Depotvej 1, 4000 Roskilde", lat=55.6415, lng=12.0803)
    depot_order = await order("B-1045", grus, depot, svc["volumen"], "godkendt", quote_approved_at=at(-6, 9),
                              contact_name="Pladsformand", created_at=at(-12, 9))
    await order("B-1048", grus, depot, svc["termografi"], "afventer_godkendelse", contact_name="Pladsformand",
                notes="Termografi af værkstedsbygning", created_at=at(-1, 15))

    # ── Plan the week through the same code path as the planner ──────────────────────────────────────────────────
    async def plan(order_id, when, pilot) -> int:
        return (await ops.plan_order(conn, order_id, when, pilot, actor_id=None, meta=meta))["id"]

    for v in range(1, 4):  # earlier visits of the Nordhavn subscription, delivered
        t = await plan(sub, at(-28 * (4 - v), 10, 30), staff["anders"])
        await conn.execute("update hojde_tasks set status = 'leveret', phase = 'leverance', drone_id = %s "
                           "where id = %s", (drone, t))
    nord = await plan(sub, at(0, 10, 30), staff["anders"])
    await conn.execute("update hojde_tasks set drone_id = %s where id = %s", (drone, nord))
    await conn.execute("""update hojde_checklist_items set done_at = %s, done_by = %s
                          where task_id = %s and key in ('risk', 'batteries', 'access', 'route')""",
                       (at(-1, 15), staff["anders"], nord))
    valby_task = await plan(valby_order, at(0, 13), staff["emil"])
    await conn.execute("update hojde_checklist_items set done_at = %s, done_by = %s where task_id = %s",
                       (at(-1, 16), staff["emil"], valby_task))
    await conn.execute("""update hojde_tasks set drone_id = %s, status = 'klar', phase = 'flyvning', ready_at = %s,
                          ready_by = %s where id = %s""", (drone, at(-1, 16), staff["emil"], valby_task))
    b_task = await plan(b1042, at(1, 8), staff["anders"])
    await conn.execute("update hojde_tasks set drone_id = %s where id = %s", (drone, b_task))
    await plan(b1043, at(8, 9), staff["anders"])
    await plan(depot_order, at(3, 10), staff["emil"])

    # ── Flight log ───────────────────────────────────────────────────────────────────────────────────────────────
    for number, location, pilot, when, sorties, minutes, wind, incident, bats in [
        ("FL-0925", loc["a"], staff["anders"], at(-19, 13, 30), 2, 21, 5, "GPS-tab", []),
        ("FL-0928", loc["c"], staff["emil"], at(-11, 10, 4), 4, 18, 8, None, []),
        ("FL-0931", loc["b"], staff["anders"], at(-4, 9, 12), 3, 19, 6, None, batteries),
    ]:
        await insert("hojde_flights", number=number, location_id=location, pilot_id=pilot, drone_id=drone,
                     battery_ids=bats, started_at=when, sorties=sorties, minutes_per_sortie=minutes, wind_ms=wind,
                     incident=incident)

    # ── The weather rule for the next 48 hours ───────────────────────────────────────────────────────────────────
    now = datetime.now(timezone.utc) if today is None else at(0, 0)
    changes = await ops.apply_weather_rule(conn, now, meta=meta)

    counts = {}
    for table in TABLES:
        counts[table] = (await db.fetch_one(conn, f"select count(*) as n from {table}"))["n"]
    await audit(conn, "create", actor_id=None, meta=meta, table=None, via="hojde.seed", removed=removed,
                counts=counts, weather=[f"{c['task_number']} → {c['to']}" for c in changes])
    return {"counts": counts, "weather": changes}


async def _main() -> int:
    if config.settings.is_production:
        print("Nægter at lægge demo-data i produktion (GAER_ENV=production).")
        return 1
    await db.open_pools()
    try:
        async with db.connection() as conn:
            result = await seed(conn)
    finally:
        await db.close_pools()
    c = result["counts"]
    print(f"Højde-demo klar: {c['hojde_organizations']} organisationer, {c['hojde_members']} medlemmer, "
          f"{c['hojde_locations']} lokationer, {c['hojde_orders']} bestillinger, {c['hojde_tasks']} opgaver, "
          f"{c['hojde_flights']} flyvninger.")
    print("Vejrreglen: " + (", ".join(f"{w['task_number']} → {w['to']}" for w in result["weather"]) or "ingen ændringer"))
    print(f"Log ind som mh@{CUSTOMER_DOMAIN} (kunde) eller emil@{STAFF_DOMAIN} (medarbejder).")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
