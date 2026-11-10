"""The rules Højde's screens imply (specs/hojde-platform/PLAN.md § Rules). Pure functions, no database.

The server is the only place they are decided: the API returns the result (a task's readiness, whether an order can
be cancelled), so the pages only show it. Ported from surdej-v2 modules/member-hojde/shared/src/rules.ts with the same
tests (server/tests/test_hojde_rules.py). Times are timezone-aware; "the day" is a Danish day (TIME_ZONE).
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TIME_ZONE = ZoneInfo("Europe/Copenhagen")

# ── Vocabulary (keys are stored in the database; labels are the Danish copy from the screens) ──────────────────────

CUSTOMER_ROLES = ("kundeadministrator", "kundebruger")
STAFF_ROLES = ("administrator", "analytiker", "pilot", "kundeansvarlig")
ROLE_LABEL = {
    "kundeadministrator": "Kundeadministrator", "kundebruger": "Kundebruger", "administrator": "Administrator",
    "analytiker": "Analytiker", "pilot": "Pilot", "kundeansvarlig": "Kundeansvarlig",
}
MEMBER_STATUSES = ("aktiv", "inviteret", "deaktiveret")
LOCATION_TYPES = ("bygning", "byggeplads", "omraade")
ORDER_STATUSES = ("afventer_godkendelse", "tilbud_sendt", "godkendt", "planlagt", "vejrforbehold", "leveret", "aflyst")
TASK_STATUSES = ("forberedelse", "klar", "vejrforbehold", "floejet", "leveret")
EQUIPMENT_STATUSES = ("klar", "til_kontrol", "til_service")
QC_STATES = ("afventer", "godkendt", "rettet", "afvist")

# ── Orders ──────────────────────────────────────────────────────────────────────────────────────────────────────────

# afventer_godkendelse → tilbud_sendt → godkendt → planlagt ⇄ vejrforbehold → leveret. An order for a service with a
# list price skips the quote (afventer_godkendelse → planlagt). Any open order can be aflyst.
TRANSITIONS: dict[str, tuple[tuple[str, ...], str]] = {
    "send_quote": (("afventer_godkendelse",), "tilbud_sendt"),
    "approve_quote": (("tilbud_sendt",), "godkendt"),
    "schedule": (("afventer_godkendelse", "godkendt", "planlagt", "vejrforbehold"), "planlagt"),
    "weather_hold": (("planlagt",), "vejrforbehold"),
    "weather_clear": (("vejrforbehold",), "planlagt"),
    "deliver": (("planlagt",), "leveret"),
    "cancel": (("afventer_godkendelse", "tilbud_sendt", "godkendt", "planlagt", "vejrforbehold"), "aflyst"),
}


def next_order_status(current: str, action: str) -> str | None:
    """The status an action leads to, or None when the action is not allowed from `current`."""
    allowed_from, to = TRANSITIONS[action]
    return to if current in allowed_from else None


CANCEL_CUTOFF_HOURS = 24


def customer_can_cancel(status: str, scheduled_at: datetime | None, now: datetime) -> bool:
    """Customers can cancel (or ask for a new date) until 24 hours before the planned flight."""
    if next_order_status(status, "cancel") is None:
        return False
    return scheduled_at is None or scheduled_at - now >= timedelta(hours=CANCEL_CUTOFF_HOURS)


def is_upcoming(status: str) -> bool:
    """Orders still in play (shown under "Kommende")."""
    return status not in ("leveret", "aflyst")


# ── Access ──────────────────────────────────────────────────────────────────────────────────────────────────────────

def is_customer_admin(roles) -> bool:
    return "kundeadministrator" in roles


def can_order(roles, may_order: bool) -> bool:
    """Customer admins always may order; customer users when their membership says so."""
    return is_customer_admin(roles) or may_order


def can_see_location(roles, location_scope: str, location_ids, location_id: int) -> bool:
    """Customer users can be limited to selected locations; admins see all."""
    return is_customer_admin(roles) or location_scope == "alle" or location_id in location_ids


can_manage_organization = is_customer_admin  # only customer admins see invoices and manage the organisation

INVITATION_DAYS = 7


def invitation_expires_at(sent_at: datetime) -> datetime:
    return sent_at + timedelta(days=INVITATION_DAYS)


# ── Weather ─────────────────────────────────────────────────────────────────────────────────────────────────────────

MAX_WIND_MS = 10  # wind over 10 m/s, or any precipitation, means vejrforbehold


@dataclass(frozen=True)
class ForecastHour:
    at: datetime            # start of the hour
    wind_ms: float
    gust_ms: float
    precipitation_mm: float
    visibility_km: float


@dataclass(frozen=True)
class WeatherVerdict:
    ok: bool
    reasons: list[str] = field(default_factory=list)   # Danish, empty when ok


def _num(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else str(v)


def weather_verdict(hours, starts_at: datetime, duration_minutes: int = 60) -> WeatherVerdict:
    """Judges the forecast hours that overlap the flight window [starts_at, starts_at + duration)."""
    end = starts_at + timedelta(minutes=duration_minutes)
    in_window = [h for h in hours if h.at < end and h.at + timedelta(hours=1) > starts_at]
    reasons = []
    max_wind = max([0, *(h.wind_ms for h in in_window)])
    if max_wind > MAX_WIND_MS:
        reasons.append(f"Vind {_num(max_wind)} m/s (over {MAX_WIND_MS} m/s)")
    if any(h.precipitation_mm > 0 for h in in_window):
        reasons.append("Nedbør i tidsrummet")
    return WeatherVerdict(ok=not reasons, reasons=reasons)


def weather_notice_deadline(scheduled_at: datetime) -> datetime:
    """The customer is told about a weather hold by the day before at the latest."""
    return scheduled_at - timedelta(days=1)


# ── Task preparation ────────────────────────────────────────────────────────────────────────────────────────────────

ZONE_PERMIT_KEY = "zone_permit"  # the checklist item that only exists in a restricted zone


@dataclass(frozen=True)
class ChecklistEntry:
    key: str
    short: str   # short noun for "n punkter mangler: …", e.g. "tilladelse"
    done: bool


@dataclass(frozen=True)
class Readiness:
    ready: bool
    missing: list[str]
    message: str  # "2 punkter mangler: tilladelse og afspærring." — empty when ready


def equipment_pickable(status: str) -> bool:
    """Equipment with status til_kontrol or til_service cannot be picked for a flight."""
    return status == "klar"


def readiness(checklist, *, restricted_zone: bool, permit_registered: bool, drone_status: str | None) -> Readiness:
    """A task can't be marked ready until every checklist item is done — the zone permit registered when the location
    is in a restricted zone, even if its item is ticked — and the drone picked is ready for use."""
    missing = [c.short for c in checklist if not c.done]
    permit_item_open = any(c.key == ZONE_PERMIT_KEY and not c.done for c in checklist)
    if restricted_zone and not permit_registered and not permit_item_open:
        missing.insert(0, "tilladelse")
    if drone_status is None:
        missing.append("drone")
    elif not equipment_pickable(drone_status):
        missing.append("drone er ikke klar")
    if not missing:
        return Readiness(True, [], "")
    noun = "punkt mangler" if len(missing) == 1 else "punkter mangler"
    return Readiness(False, missing, f"{len(missing)} {noun}: {join_danish(missing)}.")


# ── Compliance and findings ─────────────────────────────────────────────────────────────────────────────────────────

COMPLIANCE_WARN_DAYS = 30


def compliance_state(expires_at: datetime | None, now: datetime) -> dict:
    """{"state": "gyldig"} | {"state": "udloeber", "days": n} | {"state": "udloebet"}."""
    if expires_at is None:
        return {"state": "gyldig"}
    days = math.ceil((expires_at - now) / timedelta(days=1))
    if days <= 0:
        return {"state": "udloebet"}
    if days <= COMPLIANCE_WARN_DAYS:
        return {"state": "udloeber", "days": days}
    return {"state": "gyldig"}


def visible_to_customer(qc_state: str) -> bool:
    """A finding reaches the customer only after an analyst approved (or corrected) it."""
    return qc_state in ("godkendt", "rettet")


# ── Helpers ─────────────────────────────────────────────────────────────────────────────────────────────────────────

def join_danish(parts) -> str:
    """"a", "a og b", "a, b og c"."""
    parts = list(parts)
    if len(parts) <= 1:
        return "".join(parts)
    return f"{', '.join(parts[:-1])} og {parts[-1]}"


def next_number(prefix: str, existing, first: int = 1, width: int = 4) -> str:
    """Next human number in a series: next_number("B-", ["B-1042", "B-1047"]) → "B-1048"."""
    highest = first - 1
    for n in existing:
        if n.startswith(prefix) and n[len(prefix):].isdigit():
            highest = max(highest, int(n[len(prefix):]))
    return f"{prefix}{highest + 1:0{width}d}"


def local_day(at: datetime) -> str:
    """YYYY-MM-DD of `at` in Danish time."""
    return at.astimezone(TIME_ZONE).date().isoformat()


def local_time(day: str, hour: int, minute: int = 0) -> datetime:
    """The instant of a Danish wall-clock time on `day` (YYYY-MM-DD)."""
    y, m, d = (int(x) for x in day.split("-"))
    return datetime(y, m, d, hour, minute, tzinfo=TIME_ZONE)
