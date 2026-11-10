// Højde's API (/api/hojde) and vocabulary. The server decides every rule (server/app/hojde/rules.py); these types
// mirror its JSON. The X-Hojde-Org header picks the organisation for people who belong to several.
import { api } from "../api";

export type Tone = "neutral" | "signal" | "kote" | "warning" | "danger";
export type Meta = { label: string; tone: Tone; dot?: boolean };

export type OrderStatus = "afventer_godkendelse" | "tilbud_sendt" | "godkendt" | "planlagt" | "vejrforbehold" | "leveret" | "aflyst";
export type Severity = "kritisk" | "moderat" | "lav";
export type FindingStatus = "ny" | "planlagt" | "udbedret" | "afvist";
export type LocationType = "bygning" | "byggeplads" | "omraade";
export type ServiceLine = "drone" | "data" | "ai";
export type MemberStatus = "aktiv" | "inviteret" | "deaktiveret";
export type CustomerRole = "kundeadministrator" | "kundebruger";

export const ORDER_STATUS: Record<OrderStatus, Meta> = {
  afventer_godkendelse: { label: "Afventer godkendelse", tone: "neutral", dot: true },
  tilbud_sendt: { label: "Tilbud sendt", tone: "signal", dot: true },
  godkendt: { label: "Tilbud godkendt", tone: "signal" },
  planlagt: { label: "Planlagt", tone: "signal", dot: true },
  vejrforbehold: { label: "Vejrforbehold", tone: "warning", dot: true },
  leveret: { label: "Leveret", tone: "kote", dot: true },
  aflyst: { label: "Aflyst", tone: "neutral" },
};
export const SEVERITY: Record<Severity, Meta> = {
  kritisk: { label: "Kritisk", tone: "danger", dot: true },
  moderat: { label: "Moderat", tone: "warning", dot: true },
  lav: { label: "Lav", tone: "neutral", dot: true },
};
export const FINDING_STATUS: Record<FindingStatus, Meta> = {
  ny: { label: "Ny", tone: "neutral" },
  planlagt: { label: "Planlagt", tone: "signal" },
  udbedret: { label: "Udbedret", tone: "kote" },
  afvist: { label: "Afvist", tone: "neutral" },
};
export const MEMBER_STATUS: Record<MemberStatus, Meta> = {
  aktiv: { label: "Aktiv", tone: "kote", dot: true },
  inviteret: { label: "Inviteret", tone: "warning", dot: true },
  deaktiveret: { label: "Deaktiveret", tone: "neutral" },
};
export const SERVICE_LINE: Record<ServiceLine, Meta> = {
  drone: { label: "Droneydelse", tone: "signal" },
  data: { label: "Dataanalyse", tone: "kote" },
  ai: { label: "AI-ydelse", tone: "kote" },
};
export const LOCATION_TYPES: LocationType[] = ["bygning", "byggeplads", "omraade"];
export const LOCATION_TYPE_LABEL: Record<LocationType, string> = { bygning: "Bygning", byggeplads: "Byggeplads", omraade: "Område" };
export const MAX_WIND_MS = 10;

export type Membership = {
  id: number; kind: "customer" | "staff"; name: string; email: string; roles: string[]; role_labels: string[];
  org_id?: number; org_name?: string; require_2fa?: boolean; location_scope?: "alle" | "udvalgte";
  location_ids?: number[]; may_order?: boolean; can_order?: boolean; can_manage_organization?: boolean;
};
export type Me = {
  staff: Membership | null;
  customer: Membership | null;
  customers: { org_id: number; org_name: string }[];
  landing: "/portal" | "/backoffice" | null;
  mfa: { required: boolean; has_factor: boolean; proven: boolean };
};

export type OpenFindings = Record<Severity, number>;
export type OrderItem = {
  id: number; number: string; location: { id: number; name: string };
  service: { id: number; title: string; line: ServiceLine; short_label: string };
  status: OrderStatus; frequency: "enkelt" | "abonnement"; visits: number | null; scheduled_at: string | null;
  pilot: string | null; quote_ore: number | null; access_confirmed_at: string | null; created_at: string;
  can_cancel: boolean;
};
export type Overview = {
  first_name: string; can_order: boolean;
  stats: {
    locations: number; locations_this_year: number; critical_findings: number; critical_since_last_week: number;
    resolved_findings: number; resolved_last_quarter: number; next_flight: { at: string; location: string } | null;
  };
  actions: { kind: "approve_quote" | "confirm_access"; order_id: number; text: string }[];
  deliveries: { order_id: number; label: string; title: string; date: string }[];
  open_findings: OpenFindings;
  upcoming: OrderItem[];
};
export type Location = {
  id: number; name: string; type: LocationType; address: string; lat: number | null; lng: number | null;
  contact_name: string; contact_phone: string; access_notes: string; restricted_zone: boolean;
};
export type LocationListItem = Location & { last_visit: string | null; next_visit: string | null; open_findings: OpenFindings };
export type Finding = {
  id: number; number: number; title: string; note: string; severity: Severity; status: FindingStatus;
  confidence: number | null; owner: string | null; change: "ny" | "uaendret" | "forvaerret" | null;
  visit_date: string; order_number: string | null;
};
export type LocationDetail = {
  location: Location;
  visits: { date: string; service: string; order_number: string | null; findings: number }[];
  first_visit: string | null; findings: Finding[]; orders: OrderItem[];
};
export type Service = {
  id: number; key: string; line: ServiceLine; title: string; short_label: string; description: string; specs: string[];
  price_from_ore: number | null; price_unit: string; needs_quote: boolean;
};
export type NewLocation = { name: string; type: LocationType; address: string; contact_name?: string; contact_phone?: string; access_notes?: string };
export type OrderInput = {
  service_id: number; location_id?: number; new_location?: NewLocation; contact_name: string; contact_phone: string;
  access_notes: string; frequency: "enkelt" | "abonnement"; visits?: number; preferred_from: string; preferred_to: string;
  time_of_day: "hele_dagen" | "formiddag" | "eftermiddag"; subject: string; notes: string; report_recipient: string;
};
export type OrgMember = {
  id: number; name: string; email: string; roles: CustomerRole[]; role_labels: string[]; location_scope: "alle" | "udvalgte";
  location_names: string[]; may_order: boolean; two_factor: boolean | null; status: MemberStatus;
  invitation_expires_at: string | null; is_me: boolean;
};
export type OrganizationData = {
  organization: { id: number; name: string; cvr: string | null; billing_address: string | null; ean: string | null; require_2fa: boolean };
  members: OrgMember[];
  locations: { id: number; name: string }[];
};
export type InviteInput = { email: string; role: CustomerRole; location_scope: "alle" | "udvalgte"; location_ids: number[]; may_order: boolean };

const P = "/api/hojde/portal";

export const hojde = {
  me: () => api.get<Me>("/api/hojde/me"),
  overview: () => api.get<Overview>(`${P}/overview`),
  locations: (q = "", type = "") =>
    api.get<{ total: number; items: LocationListItem[] }>(`${P}/locations?q=${encodeURIComponent(q)}&type=${encodeURIComponent(type)}`),
  location: (id: number) => api.get<LocationDetail>(`${P}/locations/${id}`),
  createLocation: (body: NewLocation) => api.post<Location>(`${P}/locations`, body),
  services: () => api.get<Service[]>(`${P}/services`),
  orders: () => api.get<{ upcoming: OrderItem[]; past: OrderItem[]; subscriptions: number }>(`${P}/orders`),
  createOrder: (body: OrderInput) => api.post<OrderItem>(`${P}/orders`, body),
  approveQuote: (id: number) => api.post<OrderItem>(`${P}/orders/${id}/approve`),
  cancelOrder: (id: number) => api.post<OrderItem>(`${P}/orders/${id}/cancel`),
  confirmAccess: (id: number) => api.post<OrderItem>(`${P}/orders/${id}/confirm-access`),
  organization: () => api.get<OrganizationData>(`${P}/organization`),
  updateOrganization: (body: Partial<{ cvr: string; billing_address: string; ean: string; require_2fa: boolean }>) =>
    api.patch<OrganizationData>(`${P}/organization`, body),
  invite: (body: InviteInput) => api.post<OrganizationData>(`${P}/organization/invitations`, body),
  memberAction: (id: number, action: "resend" | "deactivate" | "reactivate") =>
    api.post<OrganizationData>(`${P}/organization/members/${id}/${action}`),
};

// ── Backoffice ─────────────────────────────────────────────────────────────────────────────────────────────

export type TaskStatus = "forberedelse" | "klar" | "vejrforbehold" | "floejet" | "leveret";
export type TaskPhase = "forberedelse" | "flyvning" | "data" | "leverance";
export type EquipmentStatus = "klar" | "til_kontrol" | "til_service";
export type EquipmentKind = "drone" | "batteri" | "andet";

export const TASK_STATUS: Record<TaskStatus, Meta> = {
  forberedelse: { label: "Forberedelse", tone: "signal", dot: true },
  klar: { label: "Klar", tone: "kote", dot: true },
  vejrforbehold: { label: "Vejrforbehold", tone: "warning", dot: true },
  floejet: { label: "Fløjet", tone: "kote", dot: true },
  leveret: { label: "Leveret", tone: "kote", dot: true },
};
export const ZONE_STATUS: Record<"fri" | "tilladelse", Meta> = {
  fri: { label: "Fri", tone: "kote" },
  tilladelse: { label: "Tilladelse", tone: "warning" },
};
export const EQUIPMENT_STATUS: Record<EquipmentStatus, Meta> = {
  klar: { label: "Klar", tone: "kote", dot: true },
  til_kontrol: { label: "Til kontrol", tone: "warning", dot: true },
  til_service: { label: "Til service", tone: "danger", dot: true },
};
export const EQUIPMENT_STATUSES: EquipmentStatus[] = ["klar", "til_kontrol", "til_service"];
export const EQUIPMENT_KIND_LABEL: Record<EquipmentKind, string> = { drone: "Drone", batteri: "Batteri", andet: "Andet" };
export const ZONE_PERMIT_KEY = "zone_permit";

export type Staff = { id: number; name: string; roles: string[]; certificates: string };
export type TaskListItem = {
  id: number; number: string; scheduled_at: string; location: { id: number; name: string }; customer: string;
  service: string; pilot: string | null; status: TaskStatus; zone: "fri" | "tilladelse";
  weather: { wind_ms: number; dry: boolean; ok: boolean } | null;
};
export type UnplannedOrder = {
  order_id: number; number: string; status: OrderStatus; frequency: "enkelt" | "abonnement"; location: string;
  service: string; customer: string; visit_number: number | null; visits: number | null; preferred_to: string | null;
};
export type Equipment = {
  id: number; name: string; kind: EquipmentKind; model: string; serial: string; c_class: string | null; usage: string;
  next_service: string; status: EquipmentStatus;
};
export type Flight = {
  id: number; number: string; started_at: string; location: string; pilot: string; drone: string; sorties: number;
  minutes_per_sortie: number; wind_ms: number; incident: string | null;
};
export type TaskDetail = {
  id: number; number: string; order_id: number; order_number: string; status: TaskStatus; phase: TaskPhase;
  scheduled_at: string; service: { title: string; line: ServiceLine }; location: Location; customer: string;
  visit_number: number | null; visits: number | null; subscription: string | null; report_recipient: string; contact: string;
  pilot: Staff | null; drone: Equipment | null;
  zone: { status: "fri" | "tilladelse"; permit_registered: boolean; coordinates: string; max_altitude_m: number; notam: string };
  weather: { hours: { at: string; wind_ms: number; gust_ms: number; precipitation_mm: number; visibility_km: number }[]; ok: boolean; reasons: string[] };
  checklist: { key: string; label: string; short: string; done: boolean; done_by: string | null }[];
  readiness: { ready: boolean; missing: string[]; message: string };
  flights: Flight[];
};
export type ComplianceState = { state: "gyldig" } | { state: "udloeber"; days: number } | { state: "udloebet" };
export type BackofficeOverview = {
  today: string;
  stats: { flights_today: number; flights_on_weather_hold: number; findings_to_review: number; findings_to_review_visits: number;
           quotes_to_send: number; orders_to_plan: number };
  flights: TaskListItem[];
  awaiting_analysis: { location: string; findings: number }[];
  compliance: { title: string; state: "gyldig" | "udloeber" | "udloebet"; days: number | null }[];
};

const BO = "/api/hojde/backoffice";

export const backoffice = {
  overview: () => api.get<BackofficeOverview>(`${BO}/overview`),
  staff: () => api.get<Staff[]>(`${BO}/staff`),
  week: (week = "") => api.get<{ week_start: string; week: number; tasks: TaskListItem[]; unplanned: UnplannedOrder[]; quotes_to_send: UnplannedOrder[] }>(
    `${BO}/tasks?week=${encodeURIComponent(week)}`),
  sendQuote: (orderId: number, amount_ore: number) => api.post<{ ok: boolean }>(`${BO}/orders/${orderId}/quote`, { amount_ore }),
  planOrder: (orderId: number, body: { scheduled_at: string; pilot_id: number | null }) => api.post<TaskDetail>(`${BO}/orders/${orderId}/plan`, body),
  checkWeather: () => api.post<{ changes: unknown[] }>(`${BO}/weather/check`),
  task: (id: number) => api.get<TaskDetail>(`${BO}/tasks/${id}`),
  updateTask: (id: number, body: { pilot_id?: number | null; drone_id?: number | null }) => api.patch<TaskDetail>(`${BO}/tasks/${id}`, body),
  toggleChecklist: (id: number, key: string, done: boolean) => api.post<TaskDetail>(`${BO}/tasks/${id}/checklist/${key}`, { done }),
  registerPermit: (id: number) => api.post<TaskDetail>(`${BO}/tasks/${id}/permit`),
  markReady: (id: number) => api.post<TaskDetail>(`${BO}/tasks/${id}/ready`),
  reschedule: (id: number, body: { scheduled_at: string; reason: "vejr" | "andet"; note: string }) => api.post<TaskDetail>(`${BO}/tasks/${id}/reschedule`, body),
  logFlight: (id: number, body: { started_at: string; sorties: number; minutes_per_sortie: number; wind_ms: number; battery_ids: number[]; incident: string | null }) =>
    api.post<Flight>(`${BO}/tasks/${id}/flights`, body),
  deliver: (id: number) => api.post<TaskDetail>(`${BO}/tasks/${id}/deliver`),
  equipment: () => api.get<Equipment[]>(`${BO}/equipment`),
  createEquipment: (body: { name: string; kind: EquipmentKind; model: string; serial: string; c_class: string | null; next_service: string }) =>
    api.post<Equipment>(`${BO}/equipment`, body),
  setEquipmentStatus: (id: number, status: EquipmentStatus) => api.patch<Equipment>(`${BO}/equipment/${id}`, { status }),
  compliance: () => api.get<{ flights: Flight[]; documents: { id: number; kind: string; title: string; reference: string; expires_at: string | null; state: ComplianceState }[]; incidents: number }>(
    `${BO}/compliance`),
};
