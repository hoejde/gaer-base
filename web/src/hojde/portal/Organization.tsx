// Kundeportal · Organisation (KP-Brugere): users and invitations, the organisation's settings and its 2FA policy.
// Customer admins only. Invitations go out by e-mail and expire after 7 days.
import { useState, type FormEvent } from "react";
import { hojde, MEMBER_STATUS, type CustomerRole, type OrganizationData, type OrgMember } from "../api";
import { formatDate } from "../format";
import { useHojdeMe } from "../Shell";
import { Button, Card, Input, LoadState, SelectField, StatusBadge, Table, Tabs, useAction, useAsync } from "../ui";

type Tab = "brugere" | "indstillinger" | "links";

function access(m: OrgMember): string {
  if (m.location_scope === "alle") return "Alle lokationer";
  return m.location_names.length === 1 ? m.location_names[0] : `${m.location_names.length} lokationer`;
}

function InviteForm({ data, onDone }: { data: OrganizationData; onDone: (d: OrganizationData) => void }) {
  const act = useAction();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<CustomerRole>("kundebruger");
  const [scope, setScope] = useState<"alle" | "udvalgte">("alle");
  const [ids, setIds] = useState<number[]>([]);
  const [mayOrder, setMayOrder] = useState(true);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    void act.run("invite", () => hojde.invite({ email, role, location_scope: scope, location_ids: ids, may_order: mayOrder }), (d) => {
      setEmail("");
      setIds([]);
      onDone(d);
    });
  };
  return (
    <form onSubmit={submit} className="hj-card">
      <h2 className="hj-h2">Invitér bruger</h2>
      <Input label="E-mail" type="email" required placeholder="navn@firma.dk" value={email} onChange={(e) => setEmail(e.target.value)} />
      <SelectField label="Rolle" value={role} onChange={(e) => setRole(e.target.value as CustomerRole)}>
        <option value="kundebruger">Kundebruger</option>
        <option value="kundeadministrator">Kundeadministrator</option>
      </SelectField>
      {role === "kundebruger" && (
        <>
          <SelectField label="Adgang" value={scope} onChange={(e) => setScope(e.target.value as "alle" | "udvalgte")}>
            <option value="alle">Alle lokationer</option>
            <option value="udvalgte">Udvalgte lokationer</option>
          </SelectField>
          {scope === "udvalgte" && (
            <fieldset>
              <legend>Lokationer</legend>
              {data.locations.map((l) => (
                <label key={l.id} className="hj-check">
                  <input type="checkbox" checked={ids.includes(l.id)} onChange={(e) => setIds((s) => (e.target.checked ? [...s, l.id] : s.filter((x) => x !== l.id)))} />
                  {l.name}
                </label>
              ))}
            </fieldset>
          )}
          <label className="hj-check"><input type="checkbox" checked={mayOrder} onChange={(e) => setMayOrder(e.target.checked)} /> Må bestille opgaver</label>
        </>
      )}
      {act.error && <p className="hj-error" role="alert">{act.error}</p>}
      <div>
        <Button type="submit" variant="primary" disabled={!!act.busy || (role === "kundebruger" && scope === "udvalgte" && ids.length === 0)}>Send invitation</Button>
      </div>
      <p className="hj-small hj-muted">
        Invitationen sendes på e-mail og udløber efter 7 dage.
        {data.organization.require_2fa && " Din organisation kræver tofaktor for alle brugere."}
      </p>
    </form>
  );
}

function Settings({ data, onDone }: { data: OrganizationData; onDone: (d: OrganizationData) => void }) {
  const act = useAction();
  const o = data.organization;
  const [form, setForm] = useState({ cvr: o.cvr ?? "", ean: o.ean ?? "", billing_address: o.billing_address ?? "", require_2fa: o.require_2fa });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    void act.run("save", () => hojde.updateOrganization(form), onDone);
  };
  return (
    <Card>
      <form onSubmit={submit} className="hj-stack">
        <h2 className="hj-h2">{o.name}</h2>
        <div className="hj-grid" style={{ "--min": "220px" } as React.CSSProperties}>
          <Input label="CVR" inputMode="numeric" pattern="[0-9]{8}" placeholder="[CVR]" value={form.cvr} onChange={(e) => setForm((f) => ({ ...f, cvr: e.target.value }))} hint="8 cifre" />
          <Input label="EAN" inputMode="numeric" pattern="[0-9]{13}" value={form.ean} onChange={(e) => setForm((f) => ({ ...f, ean: e.target.value }))} hint="13 cifre" />
          <Input label="Faktureringsadresse" maxLength={300} value={form.billing_address} onChange={(e) => setForm((f) => ({ ...f, billing_address: e.target.value }))} />
        </div>
        <label className="hj-check">
          <input type="checkbox" checked={form.require_2fa} onChange={(e) => setForm((f) => ({ ...f, require_2fa: e.target.checked }))} /> Kræv tofaktor for alle brugere
        </label>
        <p className="hj-small hj-muted">Med tofaktor skal alle bekræfte med en passkey, sikkerhedsnøgle eller godkendelsesapp for at bruge portalen.</p>
        {act.error && <p className="hj-error" role="alert">{act.error}</p>}
        <div><Button type="submit" variant="primary" disabled={!!act.busy}>Gem</Button></div>
      </form>
    </Card>
  );
}

export default function PortalOrganization() {
  const { member } = useHojdeMe();
  const { data, error, loading, setData } = useAsync(() => hojde.organization(), []);
  const act = useAction();
  const [tab, setTab] = useState<Tab>("brugere");

  if (!member.can_manage_organization) return <LoadState error="Kun kundeadministratorer kan administrere organisationen." loading={false} />;

  const action = (m: OrgMember) => {
    if (m.status === "inviteret") return { label: "Send igen", run: () => hojde.memberAction(m.id, "resend") };
    if (m.status === "deaktiveret") return { label: "Genaktivér", run: () => hojde.memberAction(m.id, "reactivate") };
    if (m.is_me) return null;
    return {
      label: "Deaktivér",
      run: () => hojde.memberAction(m.id, "deactivate"),
      confirm: `Deaktivér ${m.name}? Personen mister adgangen til portalen med det samme.`,
    };
  };

  return (
    <>
      <h1 className="hj-h1">Organisation</h1>
      {data && (
        <Tabs<Tab> label="Organisation" value={tab} onChange={setTab} tabs={[
          { key: "brugere", label: `Brugere (${data.members.length})` },
          { key: "indstillinger", label: "Indstillinger" },
          { key: "links", label: "Delte links" },
        ]} />
      )}
      <LoadState error={error ?? act.error} loading={loading && !data} />
      {data && tab === "brugere" && (
        <div className="hj-cols" style={{ "--basis": "300px" } as React.CSSProperties}>
          <section className="hj-wide">
            <Table head={["Navn", "Rolle", "Adgang", "Tofaktor", "Status", <span key="a" className="sr-only">Handlinger</span>]} minWidth={640}>
              {data.members.map((m) => {
                const a = action(m);
                return (
                  <tr key={m.id}>
                    <td><strong>{m.name}</strong><br /><span className="hj-small hj-muted">{m.email}</span></td>
                    <td>{m.role_labels.join(", ")}</td>
                    <td>{access(m)}{!m.may_order && <span className="hj-muted"> · må ikke bestille</span>}</td>
                    <td>{m.two_factor === null ? "—" : m.two_factor ? "Til" : "Fra"}</td>
                    <td>
                      <StatusBadge meta={MEMBER_STATUS[m.status]} />
                      {m.invitation_expires_at && <span className="hj-mono hj-muted" style={{ display: "block", fontSize: 12 }}>udløber {formatDate(m.invitation_expires_at)}</span>}
                    </td>
                    <td className="end">
                      {a && (
                        <Button variant="quiet" size="sm" disabled={!!act.busy}
                                onClick={() => { if (!a.confirm || window.confirm(a.confirm)) void act.run(String(m.id), a.run, setData); }}>
                          {a.label}
                        </Button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </Table>
          </section>
          <InviteForm data={data} onDone={setData} />
        </div>
      )}
      {data && tab === "indstillinger" && <Settings key={JSON.stringify(data.organization)} data={data} onDone={setData} />}
      {data && tab === "links" && <Card><p className="hj-muted">Delte links til rapporter og lokationer kommer med rapportmodulet.</p></Card>}
    </>
  );
}
