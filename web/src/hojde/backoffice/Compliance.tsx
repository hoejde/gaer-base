// Backoffice · Flyvelog og compliance (BO-Compliance): the logbook and the documents that must not expire (operator
// registration, insurance, pilot certificates). Documents warn 30 days ahead.
import { useState } from "react";
import { backoffice, type ComplianceState } from "../api";
import { formatDate, formatDateTime, formatNumber } from "../format";
import { Badge, Card, LoadState, PageHead, Table, Tabs, useAsync } from "../ui";

type Tab = "logbog" | "dokumenter" | "haendelser";

function DocState({ s }: { s: ComplianceState }) {
  if (s.state === "udloebet") return <Badge tone="danger" dot>Udløbet</Badge>;
  if (s.state === "udloeber") return <Badge tone="warning" dot>Udløber om {s.days} {s.days === 1 ? "dag" : "dage"}</Badge>;
  return <Badge tone="kote" dot>Gyldig</Badge>;
}

export default function BackofficeCompliance() {
  const { data, error, loading } = useAsync(() => backoffice.compliance(), []);
  const [tab, setTab] = useState<Tab>("logbog");
  const flights = (data?.flights ?? []).filter((f) => tab !== "haendelser" || f.incident);

  return (
    <>
      <PageHead title="Flyvelog og compliance" />
      {data && (
        <Tabs<Tab> label="Flyvelog og compliance" value={tab} onChange={setTab} tabs={[
          { key: "logbog", label: "Logbog" },
          { key: "dokumenter", label: "Dokumenter og udløb" },
          { key: "haendelser", label: `Hændelser (${data.incidents})` },
        ]} />
      )}
      <LoadState error={error} loading={loading && !data} />
      {data && tab !== "dokumenter" && (
        <Table head={["Flyvning", "Dato og tid", "Lokation", "Pilot", "Drone", "Varighed", "Vejr", "Hændelser"]}>
          {flights.map((f) => (
            <tr key={f.id}>
              <td className="num">{f.number}</td>
              <td className="num">{formatDateTime(f.started_at)}</td>
              <td>{f.location}</td>
              <td>{f.pilot}</td>
              <td className="num">{f.drone}</td>
              <td className="num">{f.sorties} × {f.minutes_per_sortie} min</td>
              <td className="num">{formatNumber(f.wind_ms)} m/s</td>
              <td>{f.incident ? <Badge tone="warning" dot>{f.incident}</Badge> : <span className="hj-muted">Ingen</span>}</td>
            </tr>
          ))}
          {flights.length === 0 && <tr><td colSpan={8} className="hj-muted">Ingen flyvninger.</td></tr>}
        </Table>
      )}
      {data && tab !== "haendelser" && (
        <Card>
          <h2 className="hj-h2">Dokumenter og udløb</h2>
          <ul className="hj-list">
            {data.documents.map((d) => (
              <li key={d.id}>
                <DocState s={d.state} />
                <span className="hj-grow">{d.title}</span>
                <span className="hj-mono">{d.reference || (d.expires_at ? `udløber ${formatDate(d.expires_at)}` : "")}</span>
              </li>
            ))}
          </ul>
          <p className="hj-small hj-muted">Dokumenter advarer 30 dage før udløb og vises på overblikket.</p>
        </Card>
      )}
    </>
  );
}
