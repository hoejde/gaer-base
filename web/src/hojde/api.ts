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
