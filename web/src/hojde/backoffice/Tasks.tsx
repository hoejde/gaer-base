// Backoffice · Opgaver (BO-Opgaver): the week calendar or list, orders waiting to be planned and orders waiting for a
// quote. Times are entered in Danish time whatever the browser's own time zone is.
import { useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { backoffice, ORDER_STATUS, TASK_STATUS, type Staff, type TaskListItem, type UnplannedOrder } from "../api";
import { addDays, danishInstant, formatDate, formatPlanned, formatTime, formatWeekdayShort, isoDay, localParts } from "../format";
import { Badge, Button, Card, Input, LoadState, PageHead, SelectField, StatusBadge, Table, Tabs, useAction, useAsync } from "../ui";

type Tab = "kalender" | "liste";

function tileText(t: TaskListItem): string {
  const what = t.status === "forberedelse" || t.status === "vejrforbehold" ? TASK_STATUS[t.status].label : t.service;
  return [what, t.pilot].filter(Boolean).join(" · ");
}

function PlanForm({ order, pilots, onPlanned, onCancel }: { order: UnplannedOrder; pilots: Staff[]; onPlanned: (taskId: number) => void; onCancel: () => void }) {
  const act = useAction();
  const preferred = order.preferred_to ? order.preferred_to.slice(0, 10) : "";
  const [day, setDay] = useState(preferred && preferred > isoDay(0) ? preferred : isoDay(1));
  const [time, setTime] = useState("09:00");
  const [pilotId, setPilotId] = useState(pilots[0] ? String(pilots[0].id) : "");
  return (
    <li style={{ flexDirection: "column", alignItems: "stretch" }}>
      <div className="hj-row" style={{ alignItems: "flex-end", gap: 16 }}>
        <Input label="Dato" type="date" min={isoDay(0)} value={day} onChange={(e) => setDay(e.target.value)} />
        <Input label="Klokkeslæt" type="time" step={900} value={time} onChange={(e) => setTime(e.target.value)} />
        <SelectField label="Pilot" value={pilotId} onChange={(e) => setPilotId(e.target.value)}>
          <option value="">Vælg senere</option>
          {pilots.map((p) => <option key={p.id} value={p.id}>{p.name}{p.certificates ? ` · ${p.certificates}` : ""}</option>)}
        </SelectField>
        <Button variant="primary" disabled={!!act.busy || !day || !time}
                onClick={() => void act.run("plan", () => backoffice.planOrder(order.order_id, { scheduled_at: danishInstant(day, time), pilot_id: pilotId ? Number(pilotId) : null }), (t) => onPlanned(t.id))}>
          Planlæg
        </Button>
        <Button onClick={onCancel}>Annullér</Button>
      </div>
      {act.error && <p className="hj-error" role="alert">{act.error}</p>}
    </li>
  );
}

function QuoteForm({ order, onSent }: { order: UnplannedOrder; onSent: () => void }) {
  const act = useAction();
  const [kr, setKr] = useState("");
  const amount = Math.round(Number(kr.replace(/\./g, "").replace(",", ".")) * 100);
  return (
    <li style={{ flexWrap: "wrap" }}>
      <StatusBadge meta={ORDER_STATUS.afventer_godkendelse} />
      <span className="hj-grow">{order.customer} · {order.location} · {order.service} <span className="hj-mono hj-muted">{order.number}</span></span>
      <label className="hj-small">Pris ekskl. moms{" "}
        <input className="hj-control hj-control--sm" style={{ width: 120 }} inputMode="decimal" placeholder="kr." value={kr} onChange={(e) => setKr(e.target.value)} />
      </label>
      <Button size="sm" variant="primary" disabled={!!act.busy || !(amount > 0)} onClick={() => void act.run("quote", () => backoffice.sendQuote(order.order_id, amount), onSent)}>
        Send tilbud
      </Button>
      {act.error && <span className="hj-error" style={{ width: "100%" }} role="alert">{act.error}</span>}
    </li>
  );
}

export default function BackofficeTasks() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const week = params.get("uge") ?? "";
  const { data, error, loading, reload } = useAsync(() => backoffice.week(week), [week]);
  const staff = useAsync(() => backoffice.staff(), []);
  const pilots = (staff.data ?? []).filter((s) => s.roles.includes("pilot"));
  const [tab, setTab] = useState<Tab>("kalender");
  const [pilot, setPilot] = useState("");
  const [planning, setPlanning] = useState<number | null>(null);

  const tasks = (data?.tasks ?? []).filter((t) => !pilot || t.pilot === pilot);
  const days = useMemo(() => {
    if (!data) return [];
    const used = new Set(data.tasks.map((t) => localParts(t.scheduled_at).day));
    return Array.from({ length: 7 }, (_, i) => addDays(data.week_start, i)).filter((d, i) => i < 5 || used.has(d));
  }, [data]);
  const byDay = (day: string) => tasks.filter((t) => localParts(t.scheduled_at).day === day);
  const goWeek = (n: number) => data && setParams({ uge: addDays(data.week_start, 7 * n) });

  return (
    <>
      <PageHead title="Opgaver" />
      <Tabs<Tab> label="Visning" value={tab} onChange={setTab} tabs={[{ key: "kalender", label: "Kalender" }, { key: "liste", label: "Liste" }]} />
      <div className="hj-row">
        <Button size="sm" onClick={() => goWeek(-1)}>‹ Forrige uge</Button>
        {data && <strong>Uge {data.week} · {formatDate(`${data.week_start}T12:00:00Z`).slice(0, 5)}–{formatDate(`${addDays(data.week_start, days.length - 1)}T12:00:00Z`)}</strong>}
        <Button size="sm" onClick={() => goWeek(1)}>Næste uge ›</Button>
        <span className="hj-spacer" />
        <label className="hj-small hj-muted">Pilot{" "}
          <select className="hj-control hj-control--sm" value={pilot} onChange={(e) => setPilot(e.target.value)}>
            <option value="">Alle piloter</option>
            {pilots.map((p) => <option key={p.id} value={p.name}>{p.name}</option>)}
          </select>
        </label>
      </div>
      <LoadState error={error} loading={loading && !data} />
      {data && tab === "kalender" && (
        <div className="hj-table-wrap">
          <div className="hj-cal" style={{ gridTemplateColumns: `repeat(${days.length}, minmax(0, 1fr))` }}>
            {days.map((d) => (
              <div key={d}>
                <strong className="hj-small">{formatWeekdayShort(`${d}T12:00:00Z`)}</strong>
                {byDay(d).map((t) => (
                  <Link key={t.id} to={`/backoffice/opgaver/${t.id}`} className={`hj-tile hj-tile--${t.status}`}>
                    <span className="hj-mono">{formatTime(t.scheduled_at)}</span><br />
                    {t.location.name}<br />
                    <span className="hj-small hj-muted">{tileText(t)}</span>
                  </Link>
                ))}
                {byDay(d).length === 0 && <span className="hj-small hj-muted">Ingen opgaver</span>}
              </div>
            ))}
          </div>
        </div>
      )}
      {data && tab === "liste" && (
        <Table head={["Opgave", "Tidspunkt", "Lokation", "Kunde", "Ydelse", "Pilot", "Status"]}>
          {tasks.map((t) => (
            <tr key={t.id}>
              <td className="num"><Link to={`/backoffice/opgaver/${t.id}`}>{t.number}</Link></td>
              <td className="num">{formatPlanned(t.scheduled_at)}</td>
              <td>{t.location.name}</td>
              <td>{t.customer}</td>
              <td>{t.service}</td>
              <td>{t.pilot ?? "—"}</td>
              <td><StatusBadge meta={TASK_STATUS[t.status]} /></td>
            </tr>
          ))}
          {tasks.length === 0 && <tr><td colSpan={7} className="hj-muted">Ingen opgaver i ugen.</td></tr>}
        </Table>
      )}

      {data && (
        <Card>
          <h2 className="hj-h2">Ikke planlagt ({data.unplanned.length})</h2>
          {data.unplanned.length === 0 ? <p className="hj-muted">Alle godkendte bestillinger er planlagt.</p> : (
            <ul className="hj-list">
              {data.unplanned.map((o) => planning === o.order_id ? (
                <PlanForm key={o.order_id} order={o} pilots={pilots} onCancel={() => setPlanning(null)} onPlanned={(id) => navigate(`/backoffice/opgaver/${id}`)} />
              ) : (
                <li key={o.order_id}>
                  {o.frequency === "abonnement" ? <Badge>Abonnement</Badge> : <StatusBadge meta={ORDER_STATUS[o.status]} />}
                  <span className="hj-grow">
                    {o.customer} · {o.location} · {o.service}
                    {o.visit_number !== null && ` · besøg ${o.visit_number} af ${o.visits}`}
                    {o.preferred_to && ` · senest ${formatDate(`${o.preferred_to.slice(0, 10)}T12:00:00Z`).slice(0, 5)}`}
                  </span>
                  <Button size="sm" onClick={() => setPlanning(o.order_id)}>Planlæg</Button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}
      {data && data.quotes_to_send.length > 0 && (
        <Card>
          <h2 className="hj-h2">Tilbud til afsendelse ({data.quotes_to_send.length})</h2>
          <ul className="hj-list">{data.quotes_to_send.map((o) => <QuoteForm key={o.order_id} order={o} onSent={reload} />)}</ul>
          <p className="hj-small hj-muted">Kunden ser og godkender tilbuddet i kundeportalen.</p>
        </Card>
      )}
    </>
  );
}
