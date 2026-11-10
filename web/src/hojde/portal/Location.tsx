// Kundeportal · Lokation (KP-Lokation): timeline, map/3D placeholder with the visit's findings, findings and orders.
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { FINDING_STATUS, hojde, LOCATION_TYPE_LABEL, ORDER_STATUS, SEVERITY, type Finding } from "../api";
import { formatDate, formatDayMonth, formatNumber } from "../format";
import { useHojdeMe } from "../Shell";
import { Badge, Button, ButtonLink, Card, LoadState, MapPlaceholder, PageHead, StatusBadge, Table, Tabs, useAsync } from "../ui";

type Tab = "tidslinje" | "kort" | "fund" | "dokumenter" | "bestillinger";

function changeText(f: Finding, previous: string | null): string | null {
  if (!previous) return null;
  if (f.change === "ny") return `Ny siden ${formatDayMonth(previous)}.`;
  if (f.change === "uaendret") return `Uændret siden ${formatDayMonth(previous)}.`;
  if (f.change === "forvaerret") return `Forværret siden ${formatDayMonth(previous)}.`;
  return null;
}

function FindingCard({ f, previous }: { f: Finding; previous: string | null }) {
  const note = [f.owner ? `Ansvarlig: ${f.owner}.` : null, f.note || null, changeText(f, previous)].filter(Boolean).join(" ");
  return (
    <article className="hj-finding">
      <div className="hj-row" style={{ gap: 8 }}>
        <span className="hj-mono" style={{ fontWeight: 600 }}>{f.number}</span>
        <StatusBadge meta={SEVERITY[f.severity]} />
        <span className="hj-spacer" />
        <StatusBadge meta={FINDING_STATUS[f.status]} />
      </div>
      <strong>{f.title}</strong>
      {note && <span className="hj-small hj-muted">{note}</span>}
      {f.confidence !== null && f.severity === "kritisk" && (
        <span className="hj-mono hj-muted" style={{ fontSize: 12 }}>AI-sikkerhed {formatNumber(f.confidence, 2)} · godkendt af analytiker</span>
      )}
    </article>
  );
}

export default function PortalLocation() {
  const id = Number(useParams().id);
  const { member } = useHojdeMe();
  const { data, error, loading } = useAsync(() => hojde.location(id), [id]);
  const [tab, setTab] = useState<Tab>("kort");
  const visitDates = useMemo(() => [...new Set((data?.findings ?? []).map((f) => f.visit_date))].sort().reverse(), [data]);
  const [visit, setVisit] = useState<string | null>(null);
  const current = visit ?? visitDates[0] ?? null;
  const previous = current ? visitDates[visitDates.indexOf(current) + 1] ?? null : null;
  const [compare, setCompare] = useState("auto");
  const compareWith = compare === "auto" ? previous : compare === "ingen" ? null : compare;

  if (!data) return <LoadState error={error} loading={loading} />;
  const l = data.location;
  const visitFindings = data.findings.filter((f) => f.visit_date === current);
  const open = data.findings.filter((f) => f.status === "ny" || f.status === "planlagt");

  return (
    <>
      <PageHead
        crumb={<><Link to="/portal/lokationer">Lokationer</Link> › {l.name}</>}
        title={l.name}
        meta={<>
          <Badge>{LOCATION_TYPE_LABEL[l.type]}</Badge>
          <span className="hj-mono hj-muted">
            {l.address}
            {data.visits.length > 0 && ` · ${data.visits.length} besøg`}
            {data.first_visit && ` siden ${formatDate(data.first_visit).slice(3)}`}
          </span>
        </>}
        actions={member.can_order ? <ButtonLink to={`/portal/bestillinger/ny?lokation=${l.id}`} variant="primary">Bestil flyvning</ButtonLink> : undefined}
      />
      <Tabs<Tab> label="Lokation" value={tab} onChange={setTab} tabs={[
        { key: "tidslinje", label: "Tidslinje" },
        { key: "kort", label: "Kort og 3D" },
        { key: "fund", label: `Fund (${open.length})` },
        { key: "dokumenter", label: "Dokumenter" },
        { key: "bestillinger", label: "Bestillinger" },
      ]} />

      {tab === "kort" && (
        <div className="hj-cols" style={{ "--basis": "320px" } as React.CSSProperties}>
          <section className="hj-wide hj-stack" style={{ gap: 12 }}>
            <div className="hj-row" style={{ gap: 8 }}>
              <label className="hj-small">Besøg{" "}
                <select className="hj-control hj-control--sm" value={current ?? ""} onChange={(e) => setVisit(e.target.value)}>
                  {visitDates.map((d) => <option key={d} value={d}>{formatDate(d)}</option>)}
                </select>
              </label>
              <label className="hj-small">sammenlign med{" "}
                <select className="hj-control hj-control--sm" value={compare} onChange={(e) => setCompare(e.target.value)}>
                  {previous && <option value="auto">{formatDate(previous)}</option>}
                  {visitDates.filter((d) => d !== current && d !== previous).map((d) => <option key={d} value={d}>{formatDate(d)}</option>)}
                  <option value="ingen">Ingen</option>
                </select>
              </label>
              <span className="hj-spacer" />
              <Button size="sm" disabled title="Kommer med kortvisningen">Mål afstand</Button>
              <Button size="sm" disabled title="Kommer med kortvisningen">Mål areal</Button>
              <Button size="sm" disabled title="Kommer med 3D-visningen">3D-visning</Button>
            </div>
            {current ? (
              <MapPlaceholder height={520}
                caption={`Ortofoto, ${formatDate(current)}${compareWith ? ` | ${formatDate(compareWith)}` : ""}`}
                points={visitFindings.map((f, i) => ({ id: f.id, lat: 1 - ((i * 37) % 10) / 10, lng: ((i * 53) % 10) / 10, label: `${f.number}: ${f.title}`, severity: f.severity }))} />
            ) : <Card><p className="hj-muted">Ingen besøg med fund endnu.</p></Card>}
          </section>
          <aside className="hj-stack" style={{ gap: 12 }}>
            <h2 className="hj-h2">Fund på dette besøg</h2>
            {visitFindings.slice(0, 3).map((f) => <FindingCard key={f.id} f={f} previous={previous} />)}
            {visitFindings.length === 0 && <p className="hj-small hj-muted">Ingen godkendte fund.</p>}
            {visitFindings.length > 3 && <Button variant="quiet" onClick={() => setTab("fund")}>Se alle {visitFindings.length} fund</Button>}
          </aside>
        </div>
      )}

      {tab === "tidslinje" && (
        <Card>
          <h2 className="hj-h2">Tidslinje</h2>
          {data.visits.length === 0 ? <p className="hj-muted">Ingen besøg endnu.</p> : (
            <ul className="hj-list">
              {data.visits.map((v) => (
                <li key={`${v.date}:${v.order_number}`}>
                  <span className="hj-mono hj-muted">{formatDate(v.date)}</span>
                  <span className="hj-grow">{v.service}</span>
                  <span className="hj-muted">{v.findings} fund</span>
                  <span className="hj-mono">{v.order_number}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}

      {tab === "fund" && (
        <Table head={["Nr.", "Fund", "Alvor", "Besøg", "Status", "Ansvarlig"]}>
          {data.findings.map((f) => (
            <tr key={f.id}>
              <td className="num">{f.number}</td>
              <td>{f.title}</td>
              <td><StatusBadge meta={SEVERITY[f.severity]} /></td>
              <td className="num">{formatDate(f.visit_date)}</td>
              <td><StatusBadge meta={FINDING_STATUS[f.status]} /></td>
              <td>{f.owner ?? "—"}</td>
            </tr>
          ))}
          {data.findings.length === 0 && <tr><td colSpan={6} className="hj-muted">Ingen godkendte fund.</td></tr>}
        </Table>
      )}

      {tab === "dokumenter" && <Card><p className="hj-muted">Rapporter og dokumenter for lokationen vises her, når de er udgivet.</p></Card>}

      {tab === "bestillinger" && (
        <Table head={["Nr.", "Ydelse", "Planlagt", "Status"]} minWidth={520}>
          {data.orders.map((o) => (
            <tr key={o.id}>
              <td className="num">{o.number}</td>
              <td>{o.service.title}</td>
              <td className="num">{o.scheduled_at ? formatDate(o.scheduled_at) : "—"}</td>
              <td><StatusBadge meta={ORDER_STATUS[o.status]} /></td>
            </tr>
          ))}
          {data.orders.length === 0 && <tr><td colSpan={4} className="hj-muted">Ingen bestillinger.</td></tr>}
        </Table>
      )}
    </>
  );
}
