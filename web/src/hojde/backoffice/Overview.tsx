// Backoffice · Overblik (BO-Overblik): today's flights, the analysis queue and compliance warnings.
import { Link } from "react-router-dom";
import { backoffice, TASK_STATUS, ZONE_STATUS } from "../api";
import { formatLongDate, formatNumber, formatTime } from "../format";
import { Badge, Button, Card, LoadState, PageHead, SectionHead, Stat, StatusBadge, Table, useAction, useAsync } from "../ui";

export default function BackofficeOverview() {
  const { data, error, loading, reload } = useAsync(() => backoffice.overview(), []);
  const act = useAction();
  const s = data?.stats;
  return (
    <>
      <PageHead eyebrow={data ? formatLongDate(data.today) : undefined} title="Overblik"
                actions={<Button disabled={!!act.busy} onClick={() => void act.run("weather", () => backoffice.checkWeather(), reload)}>Tjek vejret</Button>} />
      <LoadState error={error ?? act.error} loading={loading && !data} />
      {data && s && (
        <>
          <div className="hj-grid" style={{ "--min": "200px" } as React.CSSProperties}>
            <Stat label="Flyvninger i dag" value={s.flights_today} delta={`${s.flights_on_weather_hold} med vejrforbehold`} />
            <Stat label="Fund til kontrol" value={s.findings_to_review}
                  delta={`fra ${s.findings_to_review_visits} besøg`} />
            <Stat label="Tilbud til afsendelse" value={s.quotes_to_send} delta="afventer pris" trend={s.quotes_to_send ? "down" : "flat"} />
            <Stat label="Ikke planlagt" value={s.orders_to_plan} delta="godkendte bestillinger" />
          </div>
          <Card>
            <SectionHead title="Dagens flyvninger" link={<Link to="/backoffice/opgaver">Planlægning</Link>} />
            {data.flights.length === 0 ? <p className="hj-muted">Ingen flyvninger i dag.</p> : (
              <Table head={["Tid", "Lokation", "Pilot", "Vejr", "Zone", "Status"]} minWidth={640} bare>
                {data.flights.map((t) => (
                  <tr key={t.id}>
                    <td className="num">{formatTime(t.scheduled_at)}</td>
                    <td>
                      <Link to={`/backoffice/opgaver/${t.id}`}>{t.location.name}</Link><br />
                      <span className="hj-small hj-muted">{t.customer} · {t.service.toLowerCase()}</span>
                    </td>
                    <td>{t.pilot ?? "—"}</td>
                    <td className="num">{t.weather ? `${formatNumber(t.weather.wind_ms)} m/s · ${t.weather.dry ? "tørt" : "nedbør"}` : "—"}</td>
                    <td><StatusBadge meta={ZONE_STATUS[t.zone]} /></td>
                    <td><StatusBadge meta={TASK_STATUS[t.status]} /></td>
                  </tr>
                ))}
              </Table>
            )}
          </Card>
          <div className="hj-cols">
            <Card>
              <h2 className="hj-h2">Venter på analyse</h2>
              {data.awaiting_analysis.length === 0 ? <p className="hj-small hj-muted">Ingen fund venter på kontrol.</p> : (
                <ul className="hj-list">
                  {data.awaiting_analysis.map((a) => (
                    <li key={a.location}>
                      <span className="hj-grow">{a.location} · {a.findings} fund</span>
                      <span className="hj-small hj-muted">Kvalitetskontrol kommer med datapipelinen</span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            <Card>
              <SectionHead title="Compliance" link={<Link to="/backoffice/compliance">Flyvelog og compliance</Link>} />
              <ul className="hj-list">
                {data.compliance.map((c) => (
                  <li key={c.title}>
                    {c.state === "gyldig" ? <Badge tone="kote" dot>OK</Badge>
                      : c.state === "udloebet" ? <Badge tone="danger" dot>Udløbet</Badge>
                      : <Badge tone="warning" dot>{c.days !== null ? `${c.days} dage` : "Snart"}</Badge>}
                    <span className="hj-grow">{c.title}</span>
                  </li>
                ))}
              </ul>
            </Card>
          </div>
        </>
      )}
    </>
  );
}
