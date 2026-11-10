// Kundeportal · Overblik (KP-Overblik): key numbers, what waits on the customer, latest deliveries, open findings
// by severity and the coming flights.
import { Link } from "react-router-dom";
import { hojde, ORDER_STATUS, SEVERITY, type Severity } from "../api";
import { formatDate, formatDayMonth, formatTime, greeting } from "../format";
import { useHojdeMe } from "../Shell";
import { Badge, Button, ButtonLink, Card, LoadState, Notice, PageHead, SectionHead, Stat, StatusBadge, Table, useAction, useAsync } from "../ui";

const SEVERITIES: Severity[] = ["kritisk", "moderat", "lav"];

export default function PortalOverview() {
  const { member } = useHojdeMe();
  const { data, error, loading, reload } = useAsync(() => hojde.overview(), []);
  const act = useAction();
  const max = data ? Math.max(1, ...Object.values(data.open_findings)) : 1;
  const s = data?.stats;

  return (
    <>
      <PageHead eyebrow={`${greeting()}, ${data?.first_name ?? member.name.split(" ")[0]}`} title="Overblik"
                actions={member.can_order ? <ButtonLink to="/portal/bestillinger/ny" variant="primary">Ny bestilling</ButtonLink> : undefined} />
      <LoadState error={error ?? act.error} loading={loading && !data} />
      {data && s && (
        <>
          <div className="hj-grid" style={{ "--min": "200px" } as React.CSSProperties}>
            <Stat label="Lokationer" value={s.locations} delta={`${s.locations_this_year} ${s.locations_this_year === 1 ? "ny" : "nye"} i år`} />
            <Stat label="Alvorlige fund" value={s.critical_findings} delta={`${s.critical_since_last_week} siden sidste uge`}
                  trend={s.critical_since_last_week > 0 ? "down" : "flat"} />
            <Stat label="Udbedrede fund" value={s.resolved_findings} delta={`${s.resolved_last_quarter} siden sidste kvartal`}
                  trend={s.resolved_last_quarter > 0 ? "up" : "flat"} />
            {s.next_flight
              ? <Stat label="Næste flyvning" value={formatDayMonth(s.next_flight.at)} unit={`kl. ${formatTime(s.next_flight.at).replace(/:00$/, "")}`} delta={s.next_flight.location} />
              : <Stat label="Næste flyvning" value="—" />}
          </div>

          {data.actions.map((a) => (
            <Notice key={`${a.kind}:${a.order_id}`}>
              <Badge tone="warning" dot>Venter på dig</Badge>
              <span className="hj-grow">{a.text}</span>
              {a.kind === "confirm_access"
                ? <Button size="sm" disabled={!!act.busy} onClick={() => void act.run(String(a.order_id), () => hojde.confirmAccess(a.order_id), reload)}>Bekræft adgang</Button>
                : <ButtonLink size="sm" to="/portal/bestillinger">Se tilbud</ButtonLink>}
            </Notice>
          ))}

          <div className="hj-cols" style={{ "--basis": "420px" } as React.CSSProperties}>
            <Card>
              <SectionHead title="Seneste leverancer" link={<Link to="/portal/bestillinger">Alle bestillinger</Link>} />
              {data.deliveries.length === 0 ? <p className="hj-small hj-muted">Ingen leverancer endnu.</p> : (
                <ul className="hj-list">
                  {data.deliveries.map((d) => (
                    <li key={d.order_id}>
                      <Badge tone="kote">{d.label}</Badge>
                      <span className="hj-grow">{d.title}</span>
                      <span className="hj-mono hj-muted">{formatDate(d.date)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            <Card>
              <SectionHead title="Åbne fund efter alvor" link={<Link to="/portal/lokationer">Alle lokationer</Link>} />
              <div className="hj-bars">
                {SEVERITIES.map((k) => (
                  <div key={k}>
                    <span>{SEVERITY[k].label}</span>
                    <span className={`hj-bar sev-${k}`} style={{ width: `${(data.open_findings[k] / max) * 100}%` }} />
                    <span className="hj-mono" style={{ textAlign: "right" }}>{data.open_findings[k]}</span>
                  </div>
                ))}
              </div>
              <p className="hj-small hj-muted">Alle fund er godkendt af en analytiker før visning.</p>
            </Card>
          </div>

          <Card>
            <SectionHead title="Kommende flyvninger" link={<Link to="/portal/bestillinger">Alle bestillinger</Link>} />
            {data.upcoming.length === 0 ? <p className="hj-small hj-muted">Ingen planlagte flyvninger.</p> : (
              <Table head={["Dato", "Lokation", "Ydelse", "Status"]} minWidth={560} bare>
                {data.upcoming.map((o) => (
                  <tr key={o.id}>
                    <td className="num">{o.scheduled_at ? formatDate(o.scheduled_at) : "—"}</td>
                    <td><Link to={`/portal/lokationer/${o.location.id}`}>{o.location.name}</Link></td>
                    <td>{o.service.title}</td>
                    <td><StatusBadge meta={ORDER_STATUS[o.status]} /></td>
                  </tr>
                ))}
              </Table>
            )}
          </Card>
        </>
      )}
    </>
  );
}
