// The Højde customer portal's shell (light): top bar with the organisation, side nav, and the explanation when the
// signed-in person does not belong here. Loads /api/hojde/me once; the pages read it with useHojdeMe().
// The backoffice (dark) gets its own shell in phase 3.
import { createContext, useContext, type ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";
import { useAuth } from "../auth";
import { hojde, type Me, type Membership } from "./api";
import { initials } from "./format";
import { Button, ButtonLink, useAsync } from "./ui";
import "./hojde.css";

type HojdeMe = { me: Me; member: Membership };
const MeContext = createContext<HojdeMe | null>(null);

/** The signed-in Højde member (inside the shell). */
export function useHojdeMe(): HojdeMe {
  const me = useContext(MeContext);
  if (!me) throw new Error("useHojdeMe outside the Højde shell");
  return me;
}

function Blocked({ children, action }: { children: ReactNode; action?: ReactNode }) {
  const { logout } = useAuth();
  return (
    <div className="hj hj-blocked" data-theme="light">
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

const PORTAL_NAV = [
  { to: "/portal", label: "Overblik", end: true },
  { to: "/portal/lokationer", label: "Lokationer" },
  { to: "/portal/bestillinger", label: "Bestillinger" },
];

export function PortalShell({ children }: { children: ReactNode }) {
  const { data: me, error } = useAsync(() => hojde.me(), []);
  if (error) return <Blocked>{error}</Blocked>;
  if (!me) return <div className="hj" data-theme="light" />;
  const member = me.customer;
  if (!member) {
    return (
      <Blocked action={<ButtonLink to="/">Til forsiden</ButtonLink>}>
        {me.staff
          ? "Du er logget ind som medarbejder hos Højde. Kundeportalen viser en kundes data."
          : "Din bruger er ikke tilknyttet en kunde hos Højde. Bed din kundeadministrator om en invitation."}
      </Blocked>
    );
  }
  if (me.mfa.required && !me.mfa.has_factor) {
    return (
      <Blocked action={<ButtonLink to="/konto" variant="primary">Gå til Konto</ButtonLink>}>
        {member.org_name} kræver tofaktor. Tilføj en passkey, sikkerhedsnøgle eller godkendelsesapp under Konto, og kom
        tilbage hertil.
      </Blocked>
    );
  }
  const admin = !!member.can_manage_organization;
  return (
    <MeContext.Provider value={{ me, member }}>
      <div className="hj" data-theme="light">
        <header className="hj-top">
          <Link to="/portal" className="hj-logo">Højde</Link>
          <span className="hj-org">{member.org_name}</span>
          {me.customers.length > 1 && <span className="hj-small hj-muted hj-hide-phone">+{me.customers.length - 1} organisation(er)</span>}
          <span className="hj-spacer" />
          <Link to={admin ? "/portal/organisation" : "/konto"} className="hj-avatar" aria-label={`Min profil: ${member.name}`}>
            {initials(member.name)}
          </Link>
        </header>
        <div className="hj-body">
          <nav aria-label="Kundeportal" className="hj-nav">
            {PORTAL_NAV.map((i) => <NavLink key={i.to} to={i.to} end={i.end}>{i.label}</NavLink>)}
            {admin && <NavLink to="/portal/organisation">Organisation</NavLink>}
            <div className="hj-nav-foot">
              <Link to="/konto">Konto og sikkerhed</Link>
              <Link to="/">Forsiden</Link>
            </div>
          </nav>
          <main className="hj-main">{children}</main>
        </div>
      </div>
    </MeContext.Provider>
  );
}
