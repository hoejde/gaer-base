"""Højde's rules (app/hojde/rules.py) — the same cases as surdej-v2's hojde.test.ts, so the port behaves the same."""

from datetime import datetime, timedelta, timezone

from app.hojde import rules
from app.hojde.providers import StubWeather
from app.hojde.rules import ChecklistEntry, ForecastHour

UTC = timezone.utc
H = timedelta(hours=1)


def utc(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


# ── Orders ──────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_order_status_flow():
    n = rules.next_order_status
    assert n("afventer_godkendelse", "send_quote") == "tilbud_sendt"
    assert n("tilbud_sendt", "approve_quote") == "godkendt"
    assert n("godkendt", "schedule") == "planlagt"
    assert n("afventer_godkendelse", "schedule") == "planlagt"   # a listed price skips the quote
    assert n("planlagt", "weather_hold") == "vejrforbehold"
    assert n("vejrforbehold", "weather_clear") == "planlagt"
    assert n("planlagt", "deliver") == "leveret"
    assert n("leveret", "cancel") is None
    assert n("tilbud_sendt", "deliver") is None


def test_customers_cancel_until_24_hours_before():
    now = utc("2026-10-13T08:00:00Z")
    assert rules.customer_can_cancel("planlagt", now + 25 * H, now) is True
    assert rules.customer_can_cancel("planlagt", now + 24 * H, now) is True
    assert rules.customer_can_cancel("planlagt", now + 23 * H, now) is False
    assert rules.customer_can_cancel("tilbud_sendt", None, now) is True
    assert rules.customer_can_cancel("leveret", None, now) is False
    assert rules.is_upcoming("planlagt") and not rules.is_upcoming("aflyst")


def test_numbers_orders_tasks_and_flights():
    assert rules.next_number("B-", ["B-1042", "B-1047"], 1001) == "B-1048"
    assert rules.next_number("B-", [], 1001) == "B-1001"
    assert rules.next_number("OP-2026-", ["OP-2026-0418", "OP-2025-0999"]) == "OP-2026-0419"
    assert rules.next_number("FL-", ["FL-0931", "FL-x"]) == "FL-0932"


# ── Access ──────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_customer_users_are_limited_to_their_locations_and_ordering_right():
    roles = ["kundebruger"]
    assert rules.can_see_location(roles, "udvalgte", [3], 3) is True
    assert rules.can_see_location(roles, "udvalgte", [3], 1) is False
    assert rules.can_see_location(roles, "alle", [], 1) is True
    assert rules.can_order(roles, False) is False
    assert rules.can_order(roles, True) is True


def test_customer_admins_get_everything():
    roles = ["kundeadministrator"]
    assert rules.can_see_location(roles, "udvalgte", [3], 1) is True
    assert rules.can_order(roles, False) is True
    assert rules.can_manage_organization(roles) and not rules.can_manage_organization(["kundebruger"])


def test_invitations_expire_after_7_days():
    assert rules.invitation_expires_at(utc("2026-10-12T11:10:00Z")) == utc("2026-10-19T11:10:00Z")


# ── Weather ─────────────────────────────────────────────────────────────────────────────────────────────────────────

def hour(at: str, wind: float, rain: float = 0) -> ForecastHour:
    return ForecastHour(at=utc(at), wind_ms=wind, gust_ms=wind + 3, precipitation_mm=rain, visibility_km=10)


FORECAST = [hour("2026-10-13T08:00:00Z", 7), hour("2026-10-13T09:00:00Z", 8),
            hour("2026-10-13T10:00:00Z", 9, 0.2), hour("2026-10-13T11:00:00Z", 11)]


def test_weather_judges_only_the_hours_that_overlap_the_flight():
    # 10:30–11:30 Danish time = 08:30–09:30 UTC: 7 and 8 m/s, dry
    v = rules.weather_verdict(FORECAST, utc("2026-10-13T08:30:00Z"), 60)
    assert v.ok is True and v.reasons == []


def test_weather_holds_for_precipitation_or_wind_over_10():
    assert rules.weather_verdict(FORECAST, utc("2026-10-13T10:00:00Z"), 60).reasons == ["Nedbør i tidsrummet"]
    assert rules.weather_verdict(FORECAST, utc("2026-10-13T11:00:00Z"), 60).reasons == ["Vind 11 m/s (over 10 m/s)"]
    assert rules.weather_verdict([hour("2026-10-13T08:00:00Z", 10)], utc("2026-10-13T08:00:00Z")).ok is True
    assert rules.weather_notice_deadline(utc("2026-10-14T08:00:00Z")) == utc("2026-10-13T08:00:00Z")


def test_stub_weather_is_deterministic_and_in_danish_hours():
    day = utc("2026-10-13T12:00:00Z")
    a = StubWeather().forecast(location_id=1, lat=55.7301, lng=12.5795, day=day)
    b = StubWeather().forecast(location_id=99, lat=55.7301, lng=12.5795, day=day)
    assert a == b and len(a) == 15
    assert a[0].at == utc("2026-10-13T04:00:00Z")                    # 06:00 in Danish summer time
    winter = StubWeather().forecast(location_id=1, lat=None, lng=None, day=utc("2026-12-01T12:00:00Z"))
    assert winter[0].at == utc("2026-12-01T05:00:00Z")               # 06:00 in Danish winter time
    assert all(3 <= h.wind_ms <= 20 for h in a + winter)


# ── Task readiness (the checklist gate) ─────────────────────────────────────────────────────────────────────────────

ITEMS = [ChecklistEntry("risk", "risikovurdering", True), ChecklistEntry("zone_permit", "tilladelse", False),
         ChecklistEntry("cordon", "afspærring", False)]
DONE = [ChecklistEntry(i.key, i.short, True) for i in ITEMS]


def test_readiness_lists_what_is_missing_as_on_the_screen():
    r = rules.readiness(ITEMS, restricted_zone=True, permit_registered=False, drone_status="klar")
    assert r.ready is False
    assert r.message == "2 punkter mangler: tilladelse og afspærring."


def test_readiness_requires_the_zone_permit_even_if_the_item_is_ticked():
    r = rules.readiness(DONE, restricted_zone=True, permit_registered=False, drone_status="klar")
    assert r.missing == ["tilladelse"]


def test_readiness_blocks_a_drone_that_is_not_ready_and_a_missing_drone():
    assert rules.readiness(DONE, restricted_zone=True, permit_registered=True,
                           drone_status="til_kontrol").missing == ["drone er ikke klar"]
    assert rules.readiness(DONE, restricted_zone=True, permit_registered=True,
                           drone_status=None).message == "1 punkt mangler: drone."
    assert rules.readiness(DONE, restricted_zone=True, permit_registered=True, drone_status="klar").ready is True


def test_only_ready_equipment_can_be_picked():
    assert rules.equipment_pickable("klar") is True
    assert rules.equipment_pickable("til_kontrol") is False
    assert rules.equipment_pickable("til_service") is False


# ── Compliance and findings ─────────────────────────────────────────────────────────────────────────────────────────

def test_compliance_warns_ahead_of_expiry():
    now = utc("2026-10-13T08:00:00Z")
    assert rules.compliance_state(None, now) == {"state": "gyldig"}
    assert rules.compliance_state(utc("2026-11-08T08:00:00Z"), now) == {"state": "udloeber", "days": 26}
    assert rules.compliance_state(utc("2027-06-01T00:00:00Z"), now) == {"state": "gyldig"}
    assert rules.compliance_state(utc("2026-10-01T00:00:00Z"), now) == {"state": "udloebet"}


def test_customers_see_approved_findings_only():
    assert rules.visible_to_customer("godkendt") is True
    assert rules.visible_to_customer("rettet") is True
    assert rules.visible_to_customer("afventer") is False
    assert rules.visible_to_customer("afvist") is False


def test_joins_lists_the_danish_way():
    assert rules.join_danish(["a"]) == "a"
    assert rules.join_danish(["a", "b"]) == "a og b"
    assert rules.join_danish(["a", "b", "c"]) == "a, b og c"
