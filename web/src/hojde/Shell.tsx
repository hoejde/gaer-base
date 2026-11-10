// The two Højde shells: the customer portal (light) and the backoffice for Højde's staff (dark). Top bar, side nav, and
// the explanation when the signed-in person does not belong in the shell. Loads /api/hojde/me once; the pages read it
// with useHojdeMe().
import { createContext, useContext, type ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";
import { useAuth } from "../auth";
import { hojde, type Me, type Membership } from "./api";
import { initials } from "./format";
import { Badge, Button, ButtonLink, useAsync } from "./ui";
import "./hojde.css";

type HojdeMe = { me: Me; member: Membership };
const MeContext = createContext<HojdeMe | null>(null);

/** The signed-in Højde member (inside a shell): the customer membership in the portal, the staff one in the backoffice. */
export function useHojdeMe(): HojdeMe {
  const me = useContext(MeContext);
  if (!me) throw new Error("useHojdeMe outside a Højde shell");
  return me;
}

type Theme = "light" | "dark";

function Blocked({ theme, children, action }: { theme: Theme; children: ReactNode; action?: ReactNode }) {
  const { logout } = useAuth();
  return (
    <div className="hj hj-blocked" data-theme={theme}>
      <div>
        <span className="hj-logo">Højde</span>
        <p role="alert">{children}</p>
        <div className="hj-row">
          {action}
          <Button onClick={async () => { await logout(); window.location.href = "/"; }}>Log ud</Button>
        </div>
      </div>
    </div>
  );
}

type NavItem = { to: string; label: string; end?: boolean };

function Frame({ theme, top, nav, label, children }: { theme: Theme; top: ReactNode; nav: NavItem[]; label: string; children: ReactNode }) {
  return (
    <div className="hj" data-theme={theme}>
      <header className="hj-top">{top}</header>
      <div className="hj-body">
        <nav aria-label={label} className="hj-nav">
          {nav.map((i) => <NavLink key={i.to} to={i.to} end={i.end}>{i.label}</NavLink>)}
          <div className="hj-nav-foot">
            <Link to="/konto">Konto og sikkerhed</Link>
            <Link to="/">Forsiden</Link>
          </div>
        </nav>
        <main className="hj-main">{children}</main>
      </div>
    </div>
  );
}

/** /me, and why this person cannot use the shell (null when they can). */
function useShellMember(kind: "customer" | "staff", theme: Theme): { value: HojdeMe | null; blocked: ReactNode } {
  const { data: me, error } = useAsync(() => hojde.me(), []);
  if (error) return { value: null, blocked: <Blocked theme={theme}>{error}</Blocked> };
  if (!me) return { value: null, blocked: <div className="hj" data-theme={theme} /> };
  const member = kind === "customer" ? me.customer : me.staff;
  if (!member) {
    const other = kind === "customer" ? me.staff : me.customer;
    const text = kind === "customer"
      ? (other ? "Du er logget ind som medarbejder hos Højde. Kundeportalen viser en kundes data; brug backoffice." :
        "Din bruger er ikke tilknyttet en kunde hos Højde. Bed din kundeadministrator om en invitation.")
      : "Backoffice er kun for Højdes medarbejdere.";
    const to = kind === "customer" && other ? "/backoffice" : kind === "staff" && other ? "/portal" : "/";
    return { value: null, blocked: <Blocked theme={theme} action={<ButtonLink to={to}>{to === "/" ? "Til forsiden" : to === "/portal" ? "Til kundeportalen" : "Til backoffice"}</ButtonLink>}>{text}</Blocked> };
  }
  if (me.mfa.required && !me.mfa.has_factor) {
    const who = kind === "staff" ? "Backoffice" : member.org_name;
    return {
      value: null,
      blocked: (
        <Blocked theme={theme} action={<ButtonLink to="/konto" variant="primary">Gå til Konto</ButtonLink>}>
          {who} kræver tofaktor. Tilføj en passkey, sikkerhedsnøgle eller godkendelsesapp under Konto, og kom tilbage hertil.
        </Blocked>
      ),
    };
  }
  return { value: { me, member }, blocked: null };
}

export function PortalShell({ children }: { children: ReactNode }) {
  const { value, blocked } = useShellMember("customer", "light");
  if (!value) return <>{blocked}</>;
  const { me, member } = value;
  const admin = !!member.can_manage_organization;
  const nav: NavItem[] = [
    { to: "/portal", label: "Overblik", end: true },
    { to: "/portal/lokationer", label: "Lokationer" },
    { to: "/portal/bestillinger", label: "Bestillinger" },
    ...(admin ? [{ to: "/portal/organisation", label: "Organisation" }] : []),
  ];
  return (
    <MeContext.Provider value={value}>
      <Frame theme="light" label="Kundeportal" nav={nav} top={<>
        <Link to="/portal" className="hj-logo">Højde</Link>
        <span className="hj-org">{member.org_name}</span>
        {me.customers.length > 1 && <span className="hj-small hj-muted hj-hide-phone">+{me.customers.length - 1} organisation(er)</span>}
        <span className="hj-spacer" />
        <Link to={admin ? "/portal/organisation" : "/konto"} className="hj-avatar" aria-label={`Min profil: ${member.name}`}>{initials(member.name)}</Link>
      </>}>
        {children}
      </Frame>
    </MeContext.Provider>
  );
}

export function BackofficeShell({ children }: { children: ReactNode }) {
  const { value, blocked } = useShellMember("staff", "dark");
  if (!value) return <>{blocked}</>;
  const { member } = value;
  const nav: NavItem[] = [
    { to: "/backoffice", label: "Overblik", end: true },
    { to: "/backoffice/opgaver", label: "Opgaver" },
    { to: "/backoffice/compliance", label: "Flyvelog og compliance" },
    { to: "/backoffice/udstyr", label: "Udstyr" },
  ];
  return (
    <MeContext.Provider value={value}>
      <Frame theme="dark" label="Backoffice" nav={nav} top={<>
        <Link to="/backoffice" className="hj-logo">Højde</Link>
        <Badge tone="signal">Backoffice</Badge>
        <span className="hj-spacer" />
        <span className="hj-small hj-muted hj-hide-phone">{member.name} · {member.role_labels.join(", ")}</span>
        <Link to="/konto" className="hj-avatar" aria-label={`Min profil: ${member.name}`}>{initials(member.name)}</Link>
      </>}>
        {children}
      </Frame>
    </MeContext.Provider>
  );
}
