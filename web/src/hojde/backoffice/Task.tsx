// Backoffice · Opgave (BO-Opgave): preparation — zone check, weather and the pre-flight checklist that gates "Markér
// klar til flyvning" — then the flight log and delivery. The server decides readiness; the page shows its message.
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { backoffice, EQUIPMENT_STATUS, SERVICE_LINE, TASK_STATUS, ZONE_PERMIT_KEY, type Equipment, type TaskDetail, type TaskPhase } from "../api";
import { danishInstant, formatDateTime, formatNumber, formatPlanned, formatTime, localParts } from "../format";
import { Badge, Button, Card, Input, LoadState, PageHead, SelectField, StatusBadge, Table, Tabs, TextareaField, useAction, useAsync } from "../ui";

const pickable = (e: Equipment | null) => !!e && e.status === "klar";

function CheckRow({ label, done, disabled, hint, onChange }: { label: string; done: boolean; disabled: boolean; hint?: string; onChange: (v: boolean) => void }) {
  return (
    <label className="hj-check" style={{ fontSize: 15 }}>
      <input type="checkbox" checked={done} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <span>{label}{hint && <span className="hj-small hj-muted"> · {hint}</span>}</span>
    </label>
  );
}

function MoveForm({ t, busy, onMove, onCancel }: { t: TaskDetail; busy: boolean; onMove: (iso: string, reason: "vejr" | "andet", note: string) => void; onCancel: () => void }) {
  const start = localParts(t.scheduled_at);
  const [day, setDay] = useState(start.day);
  const [time, setTime] = useState(start.time);
  const [reason, setReason] = useState<"vejr" | "andet">(t.weather.ok ? "andet" : "vejr");
  const [note, setNote] = useState("");
  return (
    <div className="hj-stack" style={{ gap: 12, borderTop: "1px solid var(--line)", paddingTop: 16 }}>
      <Input label="Ny dato" type="date" value={day} onChange={(e) => setDay(e.target.value)} />
      <Input label="Klokkeslæt" type="time" step={900} value={time} onChange={(e) => setTime(e.target.value)} />
      <SelectField label="Årsag" value={reason} onChange={(e) => setReason(e.target.value as "vejr" | "andet")}>
        <option value="vejr">Vejr</option>
        <option value="andet">Andet</option>
      </SelectField>
      <TextareaField label="Note" rows={2} maxLength={1000} value={note} onChange={(e) => setNote(e.target.value)} />
      <div className="hj-row">
        <Button variant="primary" disabled={busy} onClick={() => onMove(danishInstant(day, time), reason, note)}>Flyt dato</Button>
        <Button onClick={onCancel}>Annullér</Button>
      </div>
      <p className="hj-small hj-muted">Kunden ser den nye dato i portalen og skal bekræfte adgang igen.</p>
    </div>
  );
}

function FlightTab({ t, batteries, onLogged }: { t: TaskDetail; batteries: Equipment[]; onLogged: () => void }) {
  const act = useAction();
  const start = localParts(t.scheduled_at);
  const [time, setTime] = useState(start.time);
  const [sorties, setSorties] = useState(3);
  const [minutes, setMinutes] = useState(19);
  const [wind, setWind] = useState(t.weather.hours[1]?.wind_ms ?? t.weather.hours[0]?.wind_ms ?? 5);
  const [used, setUsed] = useState<number[]>([]);
  const [incident, setIncident] = useState("");
  const canLog = t.status === "klar" || t.status === "floejet";
  return (
    <>
      {t.flights.length > 0 && (
        <Table head={["Flyvning", "Dato og tid", "Pilot", "Drone", "Varighed", "Vejr", "Hændelser"]}>
          {t.flights.map((f) => (
            <tr key={f.id}>
              <td className="num">{f.number}</td>
              <td className="num">{formatDateTime(f.started_at)}</td>
              <td>{f.pilot}</td>
              <td className="num">{f.drone}</td>
              <td className="num">{f.sorties} × {f.minutes_per_sortie} min</td>
              <td className="num">{formatNumber(f.wind_ms)} m/s</td>
              <td>{f.incident ? <Badge tone="warning" dot>{f.incident}</Badge> : <span className="hj-muted">Ingen</span>}</td>
            </tr>
          ))}
        </Table>
      )}
      <Card>
        <h2 className="hj-h2">Log flyvning</h2>
        {!canLog ? <p className="hj-muted">Opgaven skal være markeret klar, før en flyvning kan logges.</p> : (
          <>
            <div className="hj-grid" style={{ "--min": "160px" } as React.CSSProperties}>
              <Input label="Starttid" type="time" value={time} onChange={(e) => setTime(e.target.value)} />
              <Input label="Antal flyvninger" type="number" min={1} max={50} value={sorties} onChange={(e) => setSorties(Number(e.target.value))} />
              <Input label="Minutter pr. flyvning" type="number" min={1} max={120} value={minutes} onChange={(e) => setMinutes(Number(e.target.value))} />
              <Input label="Vind (m/s)" type="number" min={0} max={40} step={0.5} value={wind} onChange={(e) => setWind(Number(e.target.value))} />
            </div>
            {batteries.length > 0 && (
              <fieldset>
                <legend>Batterier brugt</legend>
                <div className="hj-row">
                  {batteries.map((b) => (
                    <label key={b.id} className="hj-check">
                      <input type="checkbox" checked={used.includes(b.id)} onChange={(e) => setUsed((s) => (e.target.checked ? [...s, b.id] : s.filter((x) => x !== b.id)))} />
                      {b.name}
                    </label>
                  ))}
                </div>
              </fieldset>
            )}
            <Input label="Hændelse" hint="Tom, hvis der ikke var nogen hændelser." placeholder="Fx GPS-tab" maxLength={500} value={incident} onChange={(e) => setIncident(e.target.value)} />
            {act.error && <p className="hj-error" role="alert">{act.error}</p>}
            <div>
              <Button variant="primary" disabled={!!act.busy}
                onClick={() => void act.run("log", () => backoffice.logFlight(t.id, {
                  started_at: danishInstant(start.day, time), sorties, minutes_per_sortie: minutes, wind_ms: wind, battery_ids: used,
                  incident: incident.trim() || null,
                }), onLogged)}>
                Gem i logbogen
              </Button>
            </div>
          </>
        )}
      </Card>
    </>
  );
}

export default function BackofficeTask() {
  const id = Number(useParams().id);
  const { data: t, error, loading, setData, reload } = useAsync(() => backoffice.task(id), [id]);
  const staff = useAsync(() => backoffice.staff(), []);
  const equipment = useAsync(() => backoffice.equipment(), []);
  const act = useAction();
  const [tab, setTab] = useState<TaskPhase | null>(null);
  const [moving, setMoving] = useState(false);

  if (!t) return <LoadState error={error} loading={loading} />;
  const current: TaskPhase = tab ?? t.phase;
  const editable = t.status !== "floejet" && t.status !== "leveret";
  const run = (key: string, fn: () => Promise<TaskDetail>) => void act.run(key, fn, setData);
  const pilots = (staff.data ?? []).filter((s) => s.roles.includes("pilot"));
  const drones = (equipment.data ?? []).filter((e) => e.kind === "drone");
  const batteries = (equipment.data ?? []).filter((e) => e.kind === "batteri" && e.status === "klar");
  const done = t.checklist.filter((c) => c.done).length + (pickable(t.drone) ? 1 : 0);
  const total = t.checklist.length + 1;

  return (
    <>
      <PageHead
        crumb={<><Link to="/backoffice/opgaver">Opgaver</Link> › <span className="hj-mono">{t.number}</span></>}
        title={t.location.name}
        meta={<>
          <Badge tone={SERVICE_LINE[t.service.line].tone}>{t.service.title}</Badge>
          <span className="hj-mono hj-muted">
            {formatPlanned(t.scheduled_at)} · {t.customer}{t.visit_number !== null && ` · besøg ${t.visit_number} af ${t.visits}`}
          </span>
        </>}
        actions={<StatusBadge meta={TASK_STATUS[t.status]} />}
      />
      <Tabs<TaskPhase> label="Opgave" value={current} onChange={setTab} tabs={[
        { key: "forberedelse", label: "Forberedelse" }, { key: "flyvning", label: "Flyvning" },
        { key: "data", label: "Data" }, { key: "leverance", label: "Leverance" },
      ]} />
      {act.error && <p className="hj-error" role="alert">{act.error}</p>}

      <div className="hj-cols" style={{ "--basis": "300px" } as React.CSSProperties}>
        <div className="hj-wide hj-stack" style={{ gap: 24 }}>
          {current === "forberedelse" && (
            <>
              <Card>
                <div className="hj-section-head">
                  <h2 className="hj-h2">Zonetjek</h2>
                  {t.zone.status === "fri" ? <Badge tone="kote" dot>Fri zone</Badge>
                    : t.zone.permit_registered ? <Badge tone="kote" dot>Tilladelse registreret</Badge>
                    : <Badge tone="warning" dot>Tilladelse kræves</Badge>}
                </div>
                {t.zone.status === "tilladelse" && <p className="hj-small">Lokationen ligger i en restriktionszone. Tilladelsen skal være registreret, før opgaven kan markeres klar.</p>}
                <div className="hj-mono">{t.zone.coordinates} · maks. {t.zone.max_altitude_m} m · {t.zone.notam}</div>
                {t.zone.status === "tilladelse" && !t.zone.permit_registered && editable && (
                  <div><Button size="sm" disabled={!!act.busy} onClick={() => run("permit", () => backoffice.registerPermit(t.id))}>Registrér tilladelse</Button></div>
                )}
              </Card>

              <Card>
                <div className="hj-section-head">
                  <h2 className="hj-h2">Vejr</h2>
                  {t.weather.ok ? <Badge tone="kote" dot>Inden for grænser</Badge> : <Badge tone="warning" dot>Vejrforbehold</Badge>}
                </div>
                {!t.weather.ok && <p className="hj-small">{t.weather.reasons.join(" · ")}. Kunden ser vejrforbeholdet i portalen.</p>}
                <Table head={["Tid", "Vind", "Vindstød", "Nedbør", "Sigt"]} minWidth={420} bare>
                  {t.weather.hours.map((h) => (
                    <tr key={h.at}>
                      <td className="num">{formatTime(h.at)}</td>
                      <td className="num">{formatNumber(h.wind_ms)} m/s</td>
                      <td className="num">{formatNumber(h.gust_ms)} m/s</td>
                      <td className="num">{formatNumber(h.precipitation_mm)} mm</td>
                      <td className="num">{h.visibility_km >= 10 ? "> 10 km" : `${formatNumber(h.visibility_km)} km`}</td>
                    </tr>
                  ))}
                </Table>
              </Card>

              <Card>
                <div className="hj-section-head">
                  <h2 className="hj-h2">Tjekliste før flyvning</h2>
                  <span className="hj-mono hj-muted">{done} af {total}</span>
                </div>
                <div className="hj-stack" style={{ gap: 12 }}>
                  {t.checklist.slice(0, 1).map((c) => (
                    <CheckRow key={c.key} label={c.label} done={c.done} disabled={!editable || !!act.busy} hint={c.done && c.done_by ? `afkrydset af ${c.done_by}` : undefined}
                              onChange={(v) => run(c.key, () => backoffice.toggleChecklist(t.id, c.key, v))} />
                  ))}
                  <div className="hj-row" style={{ gap: 8, fontSize: 15 }}>
                    <input type="checkbox" checked={pickable(t.drone)} readOnly aria-label="Drone valgt" />
                    <label htmlFor="drone">Drone valgt:</label>
                    <select id="drone" className="hj-control hj-control--sm" value={t.drone?.id ?? ""} disabled={!editable || !!act.busy}
                            onChange={(e) => run("drone", () => backoffice.updateTask(t.id, { drone_id: e.target.value ? Number(e.target.value) : null }))}>
                      <option value="">Vælg drone</option>
                      {drones.map((d) => (
                        <option key={d.id} value={d.id} disabled={d.status !== "klar"}>
                          {d.name} · {d.model}{d.c_class ? ` · ${d.c_class}` : ""}{d.status !== "klar" ? ` (${EQUIPMENT_STATUS[d.status].label.toLowerCase()})` : ""}
                        </option>
                      ))}
                    </select>
                    {t.drone && <span className="hj-mono">SN {t.drone.serial || "—"}</span>}
                  </div>
                  {t.checklist.slice(1).map((c) => (
                    <CheckRow key={c.key} label={c.label} done={c.done} disabled={!editable || !!act.busy || c.key === ZONE_PERMIT_KEY}
                      hint={c.key === ZONE_PERMIT_KEY && !c.done ? "registreres under Zonetjek" : c.done && c.done_by ? `${c.key === "access" ? "bekræftet" : "afkrydset"} af ${c.done_by}` : undefined}
                      onChange={(v) => run(c.key, () => backoffice.toggleChecklist(t.id, c.key, v))} />
                  ))}
                </div>
              </Card>
            </>
          )}

          {current === "flyvning" && <FlightTab t={t} batteries={batteries} onLogged={() => { reload(); equipment.reload(); }} />}

          {current === "data" && (
            <Card>
              <h2 className="hj-h2">Data</h2>
              <p className="hj-muted">Upload fra piloten, automatiske tjek og behandling (sløring, fotogrammetri, AI-analyse) kommer med datapipelinen (P3).</p>
            </Card>
          )}

          {current === "leverance" && (
            <Card>
              <h2 className="hj-h2">Leverance</h2>
              <p className="hj-muted">Rapporter med skabeloner, udgivelse og delte links kommer i P4. Indtil da markeres besøget leveret her, så kunden kan se det i portalen.</p>
              <div>
                <Button variant="primary" disabled={t.status !== "floejet" || !!act.busy} onClick={() => run("deliver", () => backoffice.deliver(t.id))}>Markér leveret</Button>
              </div>
            </Card>
          )}
        </div>

        <aside className="hj-summary">
          <h2 className="hj-h2">Opgave</h2>
          <dl>
            <dt>Kunde</dt><dd>{t.customer}</dd>
            <dt>Kontakt</dt><dd>{t.contact || "—"}</dd>
            {t.subscription && <><dt>Abonnement</dt><dd>{t.subscription}</dd></>}
            <dt>Rapportmodtager</dt><dd>{t.report_recipient || "Kunden"}</dd>
            <dt>Bestilling</dt><dd className="hj-mono">{t.order_number}</dd>
          </dl>
          <SelectField label="Pilot" value={t.pilot?.id ?? ""} disabled={!editable || !!act.busy}
                       onChange={(e) => run("pilot", () => backoffice.updateTask(t.id, { pilot_id: e.target.value ? Number(e.target.value) : null }))}>
            <option value="">Vælg pilot</option>
            {pilots.map((p) => <option key={p.id} value={p.id}>{p.name}{p.certificates ? ` · ${p.certificates}` : ""}</option>)}
          </SelectField>
          {t.status === "forberedelse" && (
            <>
              <Button variant="primary" disabled={!t.readiness.ready || !t.pilot || !!act.busy} onClick={() => run("ready", () => backoffice.markReady(t.id))}>
                Markér klar til flyvning
              </Button>
              {!t.readiness.ready && <p className="hj-small hj-muted">{t.readiness.message}</p>}
              {t.readiness.ready && !t.pilot && <p className="hj-small hj-muted">Vælg en pilot.</p>}
            </>
          )}
          {t.status === "vejrforbehold" && <p className="hj-small">Opgaven har vejrforbehold. Flyt datoen, eller vent på at vejret klarer op.</p>}
          {t.status === "klar" && <p className="hj-small">Klar til flyvning. Log flyvningen under Flyvning.</p>}
          {editable && !moving && <Button onClick={() => setMoving(true)}>Flyt dato</Button>}
          {editable && moving && (
            <MoveForm t={t} busy={!!act.busy} onCancel={() => setMoving(false)}
              onMove={(scheduled_at, reason, note) => void act.run("move", () => backoffice.reschedule(t.id, { scheduled_at, reason, note }), (d) => { setData(d); setMoving(false); })} />
          )}
        </aside>
      </div>
    </>
  );
}
