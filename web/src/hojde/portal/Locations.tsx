// Kundeportal · Lokationer (KP-Lokationer): search, type filter, list or map, and "Opret lokation".
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { hojde, LOCATION_TYPE_LABEL, LOCATION_TYPES, type LocationListItem, type LocationType } from "../api";
import { formatDate } from "../format";
import { useHojdeMe } from "../Shell";
import { Badge, Button, Card, Input, LoadState, MapPlaceholder, PageHead, SelectField, Table, TextareaField, useAction, useAsync } from "../ui";

function OpenFindingsCell({ f }: { f: LocationListItem["open_findings"] }) {
  const rest = (n: number) => (n > 0 ? <span className="hj-muted"> · {n} øvrige</span> : null);
  if (f.kritisk) return <><Badge tone="danger" dot>{f.kritisk} kritisk</Badge>{rest(f.moderat + f.lav)}</>;
  if (f.moderat) return <><Badge tone="warning" dot>{f.moderat} {f.moderat === 1 ? "moderat" : "moderate"}</Badge>{rest(f.lav)}</>;
  if (f.lav) return <Badge dot>{f.lav} {f.lav === 1 ? "lav" : "lave"}</Badge>;
  return <span className="hj-muted">Ingen</span>;
}

function CreateLocation({ onDone, onCancel }: { onDone: (id: number) => void; onCancel: () => void }) {
  const act = useAction();
  const [form, setForm] = useState({ name: "", type: "bygning" as LocationType, address: "", contact_name: "", contact_phone: "", access_notes: "" });
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const submit = (e: FormEvent) => {
    e.preventDefault();
    void act.run("create", () => hojde.createLocation(form), (l) => onDone(l.id));
  };
  return (
    <Card>
      <form onSubmit={submit} className="hj-stack">
        <h2 className="hj-h2">Opret lokation</h2>
        <div className="hj-grid">
          <Input label="Navn" required maxLength={200} value={form.name} onChange={set("name")} placeholder="Kystparken blok D" />
          <SelectField label="Type" value={form.type} onChange={set("type")}>
            {LOCATION_TYPES.map((t) => <option key={t} value={t}>{LOCATION_TYPE_LABEL[t]}</option>)}
          </SelectField>
          <Input label="Adresse" required maxLength={300} value={form.address} onChange={set("address")} placeholder="Vej 1, 2900 Hellerup" />
          <Input label="Kontaktperson på stedet" maxLength={200} value={form.contact_name} onChange={set("contact_name")} />
          <Input label="Telefon" type="tel" maxLength={40} value={form.contact_phone} onChange={set("contact_phone")} />
        </div>
        <TextareaField label="Adgangsforhold" rows={3} maxLength={2000} value={form.access_notes} onChange={set("access_notes")} />
        {act.error && <p className="hj-error" role="alert">{act.error}</p>}
        <div className="hj-row">
          <Button onClick={onCancel}>Annullér</Button>
          <Button type="submit" variant="primary" disabled={!!act.busy}>Opret lokation</Button>
        </div>
      </form>
    </Card>
  );
}

export default function PortalLocations() {
  const { member } = useHojdeMe();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [type, setType] = useState<LocationType | "">("");
  const [view, setView] = useState<"liste" | "kort">("liste");
  const [creating, setCreating] = useState(false);
  const { data, error, loading } = useAsync(() => hojde.locations(q, type), [q, type]);
  const items = data?.items ?? [];
  const open = (id: number) => navigate(`/portal/lokationer/${id}`);

  return (
    <>
      <PageHead title="Lokationer" actions={member.can_order && !creating ? <Button variant="primary" onClick={() => setCreating(true)}>Opret lokation</Button> : undefined} />
      {creating && <CreateLocation onCancel={() => setCreating(false)} onDone={open} />}
      <div className="hj-row">
        <label className="hj-small hj-muted">Søg{" "}
          <input type="search" className="hj-control hj-control--sm" placeholder="Navn eller adresse" value={q} onChange={(e) => setQ(e.target.value)} />
        </label>
        <label className="hj-small hj-muted">Type{" "}
          <select className="hj-control hj-control--sm" value={type} onChange={(e) => setType(e.target.value as LocationType | "")}>
            <option value="">Alle typer</option>
            {LOCATION_TYPES.map((t) => <option key={t} value={t}>{LOCATION_TYPE_LABEL[t]}</option>)}
          </select>
        </label>
        <span className="hj-spacer" />
        <Button size="sm" variant={view === "liste" ? "secondary" : "quiet"} aria-pressed={view === "liste"} onClick={() => setView("liste")}>Liste</Button>
        <Button size="sm" variant={view === "kort" ? "secondary" : "quiet"} aria-pressed={view === "kort"} onClick={() => setView("kort")}>Kort</Button>
      </div>
      <LoadState error={error} loading={loading && !data} />
      {view === "kort" ? (
        <MapPlaceholder caption="Kort over lokationer" onSelect={open}
          points={items.filter((l) => l.lat !== null && l.lng !== null).map((l) => ({
            id: l.id, lat: l.lat!, lng: l.lng!, label: l.name,
            severity: l.open_findings.kritisk ? "kritisk" : l.open_findings.moderat ? "moderat" : undefined,
          }))} />
      ) : (
        <Table head={["Lokation", "Type", "Seneste besøg", "Næste besøg", "Åbne fund"]}>
          {items.map((l) => (
            <tr key={l.id}>
              <td><Link to={`/portal/lokationer/${l.id}`}><strong>{l.name}</strong></Link><br /><span className="hj-muted">{l.address}</span></td>
              <td>{LOCATION_TYPE_LABEL[l.type]}</td>
              <td className="num">{l.last_visit ? formatDate(l.last_visit) : "—"}</td>
              <td className="num">{l.next_visit ? formatDate(l.next_visit) : "—"}</td>
              <td><OpenFindingsCell f={l.open_findings} /></td>
            </tr>
          ))}
          {data && items.length === 0 && <tr><td colSpan={5} className="hj-muted">Ingen lokationer matcher.</td></tr>}
        </Table>
      )}
      {data && <p className="hj-small hj-muted">Viser {items.length} af {data.total} lokationer.</p>}
    </>
  );
}
