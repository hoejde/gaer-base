// Kundeportal · Bestillinger (KP-Bestillinger): upcoming, past and subscriptions; quotes to approve; cancelling until
// 24 hours before the flight (the server decides, per order: can_cancel).
import { useState } from "react";
import { Link } from "react-router-dom";
import { hojde, ORDER_STATUS, type OrderItem } from "../api";
import { formatPlanned, formatPrice } from "../format";
import { useHojdeMe } from "../Shell";
import { Button, ButtonLink, Card, LoadState, PageHead, StatusBadge, Table, Tabs, useAction, useAsync } from "../ui";

type Tab = "kommende" | "tidligere" | "abonnementer";

function planned(o: OrderItem): string {
  if (o.scheduled_at) return formatPlanned(o.scheduled_at);
  if (o.status === "tilbud_sendt" || o.status === "afventer_godkendelse") return "Afventer godkendelse";
  if (o.status === "godkendt") return "Planlægges";
  return "—";
}

export default function PortalOrders() {
  const { member } = useHojdeMe();
  const { data, error, loading, reload } = useAsync(() => hojde.orders(), []);
  const act = useAction();
  const [tab, setTab] = useState<Tab>("kommende");
  const quotes = (data?.upcoming ?? []).filter((o) => o.status === "tilbud_sendt");
  const rows = !data ? [] : tab === "kommende" ? data.upcoming : tab === "tidligere" ? data.past : data.upcoming.filter((o) => o.frequency === "abonnement");

  const cancel = (o: OrderItem) => {
    if (!window.confirm(`Aflys ${o.number} (${o.service.title}, ${o.location.name})? Planlagte flyvninger fjernes.`)) return;
    void act.run(String(o.id), () => hojde.cancelOrder(o.id), reload);
  };

  return (
    <>
      <PageHead title="Bestillinger" actions={member.can_order ? <ButtonLink to="/portal/bestillinger/ny" variant="primary">Ny bestilling</ButtonLink> : undefined} />
      {data && (
        <Tabs<Tab> label="Bestillinger" value={tab} onChange={setTab} tabs={[
          { key: "kommende", label: `Kommende (${data.upcoming.length})` },
          { key: "tidligere", label: `Tidligere (${data.past.length})` },
          { key: "abonnementer", label: `Abonnementer (${data.subscriptions})` },
        ]} />
      )}
      <LoadState error={error ?? act.error} loading={loading && !data} />
      {tab === "kommende" && quotes.map((o) => (
        <Card key={o.id} className="hj-row">
          <StatusBadge meta={ORDER_STATUS.tilbud_sendt} />
          <span style={{ flex: "1 1 320px" }}>
            Tilbud på {o.service.title} af {o.location.name} venter på din godkendelse.
            <span className="hj-mono hj-muted"> {o.number} · {formatPrice(o.quote_ore)} ekskl. moms</span>
          </span>
          {member.can_order && (
            <Button size="sm" variant="primary" disabled={!!act.busy} onClick={() => void act.run(String(o.id), () => hojde.approveQuote(o.id), reload)}>
              Godkend tilbud
            </Button>
          )}
        </Card>
      ))}
      {data && (
        <Table head={["Nr.", "Lokation", "Ydelse", "Planlagt", "Pilot", "Status", <span key="a" className="sr-only">Handlinger</span>]}>
          {rows.map((o) => (
            <tr key={o.id}>
              <td className="num">{o.number}</td>
              <td><Link to={`/portal/lokationer/${o.location.id}`}>{o.location.name}</Link></td>
              <td>{o.service.title}{o.frequency === "abonnement" && <span className="hj-muted"> · {o.visits} besøg</span>}</td>
              <td className="num">{planned(o)}</td>
              <td>{o.pilot ?? "—"}</td>
              <td><StatusBadge meta={ORDER_STATUS[o.status]} /></td>
              <td className="end">
                {o.can_cancel && member.can_order && (
                  <Button size="sm" variant="quiet" disabled={!!act.busy} onClick={() => cancel(o)}>Aflys</Button>
                )}
              </td>
            </tr>
          ))}
          {rows.length === 0 && <tr><td colSpan={7} className="hj-muted">Ingen bestillinger.</td></tr>}
        </Table>
      )}
      <p className="hj-small hj-muted">Du kan aflyse eller ønske ny dato frem til 24 timer før planlagt flyvning.</p>
    </>
  );
}
