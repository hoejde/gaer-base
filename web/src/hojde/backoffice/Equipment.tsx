// Backoffice · Udstyr (BO-Udstyr): drones, batteries and other kit with usage, service and status. Equipment that is not
// "Klar" cannot be picked for a flight. Registering and changing status needs the pilot role.
import { useState, type FormEvent } from "react";
import { backoffice, EQUIPMENT_KIND_LABEL, EQUIPMENT_STATUS, EQUIPMENT_STATUSES, type EquipmentKind, type EquipmentStatus } from "../api";
import { Button, Card, Input, LoadState, PageHead, SelectField, StatusBadge, Table, useAction, useAsync } from "../ui";

const KINDS: EquipmentKind[] = ["drone", "batteri", "andet"];

function RegisterForm({ onDone, onCancel }: { onDone: () => void; onCancel: () => void }) {
  const act = useAction();
  const [form, setForm] = useState({ name: "", kind: "drone" as EquipmentKind, model: "", serial: "", c_class: "", next_service: "" });
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const submit = (e: FormEvent) => {
    e.preventDefault();
    void act.run("create", () => backoffice.createEquipment({ ...form, c_class: form.c_class || null }), onDone);
  };
  return (
    <Card>
      <form onSubmit={submit} className="hj-stack">
        <h2 className="hj-h2">Registrér udstyr</h2>
        <div className="hj-grid" style={{ "--min": "200px" } as React.CSSProperties}>
          <Input label="Enhed" required maxLength={100} value={form.name} onChange={set("name")} placeholder="Drone 3" />
          <SelectField label="Type" value={form.kind} onChange={set("kind")}>
            {KINDS.map((k) => <option key={k} value={k}>{EQUIPMENT_KIND_LABEL[k]}</option>)}
          </SelectField>
          <Input label="Model" required maxLength={100} value={form.model} onChange={set("model")} />
          <Input label="Serienummer" maxLength={100} value={form.serial} onChange={set("serial")} />
          <SelectField label="C-klasse" value={form.c_class} onChange={set("c_class")}>
            <option value="">Ingen</option>
            {["C0", "C1", "C2", "C3", "C4"].map((c) => <option key={c} value={c}>{c}</option>)}
          </SelectField>
          <Input label="Næste service" maxLength={100} value={form.next_service} onChange={set("next_service")} placeholder="ved 50 t" />
        </div>
        {act.error && <p className="hj-error" role="alert">{act.error}</p>}
        <div className="hj-row">
          <Button onClick={onCancel}>Annullér</Button>
          <Button type="submit" variant="primary" disabled={!!act.busy}>Registrér</Button>
        </div>
      </form>
    </Card>
  );
}

export default function BackofficeEquipment() {
  const { data, error, loading, reload } = useAsync(() => backoffice.equipment(), []);
  const act = useAction();
  const [adding, setAdding] = useState(false);
  return (
    <>
      <PageHead title="Udstyr" actions={!adding ? <Button variant="primary" onClick={() => setAdding(true)}>Registrér udstyr</Button> : undefined} />
      {adding && <RegisterForm onCancel={() => setAdding(false)} onDone={() => { setAdding(false); reload(); }} />}
      <LoadState error={error ?? act.error} loading={loading && !data} />
      {data && (
        <Table head={["Enhed", "Model", "Serienummer", "C-klasse", "Brug", "Næste service", "Status"]}>
          {data.map((e) => (
            <tr key={e.id}>
              <td>{e.name}</td>
              <td>{e.model}</td>
              <td className="num">{e.serial || "—"}</td>
              <td className="num">{e.c_class ?? "—"}</td>
              <td className="num">{e.usage}</td>
              <td className="num">{e.next_service || "—"}</td>
              <td>
                <div className="hj-row" style={{ gap: 8, flexWrap: "nowrap" }}>
                  <StatusBadge meta={EQUIPMENT_STATUS[e.status]} />
                  <label className="sr-only" htmlFor={`st-${e.id}`}>Skift status for {e.name}</label>
                  <select id={`st-${e.id}`} className="hj-control hj-control--sm" value={e.status} disabled={!!act.busy}
                          onChange={(ev) => void act.run(String(e.id), () => backoffice.setEquipmentStatus(e.id, ev.target.value as EquipmentStatus), reload)}>
                    {EQUIPMENT_STATUSES.map((s) => <option key={s} value={s}>{EQUIPMENT_STATUS[s].label}</option>)}
                  </select>
                </div>
              </td>
            </tr>
          ))}
        </Table>
      )}
      <p className="hj-small hj-muted">Udstyr med status Til kontrol eller Til service kan ikke vælges til en flyvning.</p>
    </>
  );
}
