// Kundeportal · Ny bestilling (KP-Bestilling): the four-step wizard — Ydelse, Lokation, Tidspunkt, Bemærkninger — with
// the order summary beside it. The server validates the order again (OrderIn in routes/hojde_portal.py).
import { useState, type ReactNode } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { hojde, LOCATION_TYPE_LABEL, LOCATION_TYPES, MAX_WIND_MS, SERVICE_LINE, type LocationType, type OrderInput } from "../api";
import { formatDate, formatPrice, isoDay } from "../format";
import { useHojdeMe } from "../Shell";
import { Badge, Button, Input, LoadState, SelectField, ServiceCard, TextareaField, useAction, useAsync } from "../ui";

const STEPS = ["Ydelse", "Lokation", "Tidspunkt", "Bemærkninger"];
const NEW = "ny";

function Steps({ step }: { step: number }) {
  return (
    <ol aria-label="Trin" className="hj-steps">
      {STEPS.map((s, i) => (
        <li key={s} aria-current={i === step ? "step" : undefined} className={i < step ? "done" : undefined}>
          <span className="hj-mono">{i + 1}{i < step ? " ✓" : ""}</span> {s}
        </li>
      ))}
    </ol>
  );
}

function Choice({ checked, onChange, title, detail, name }: { checked: boolean; onChange: () => void; title: string; detail: ReactNode; name: string }) {
  return (
    <label className={`hj-choice${checked ? " checked" : ""}`}>
      <input type="radio" name={name} checked={checked} onChange={onChange} />
      <span><strong>{title}</strong><br /><span className="hj-small hj-muted">{detail}</span></span>
    </label>
  );
}

export default function PortalNewOrder() {
  const { member } = useHojdeMe();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const services = useAsync(() => hojde.services(), []);
  const locations = useAsync(() => hojde.locations(), []);
  const act = useAction();

  const [step, setStep] = useState(0);
  const [serviceId, setServiceId] = useState<number | null>(null);
  const [locationId, setLocationId] = useState<string>(params.get("lokation") ?? "");
  const [newLoc, setNewLoc] = useState({ name: "", type: "bygning" as LocationType, address: "" });
  // The site contact, prefilled from the chosen location until edited.
  const [contact, setContact] = useState<{ name?: string; phone?: string; access?: string }>({});
  const [frequency, setFrequency] = useState<"enkelt" | "abonnement">("enkelt");
  const [visits, setVisits] = useState(12);
  const [from, setFrom] = useState(isoDay(7));
  const [to, setTo] = useState(isoDay(21));
  const [timeOfDay, setTimeOfDay] = useState<OrderInput["time_of_day"]>("hele_dagen");
  const [subject, setSubject] = useState("");
  const [notes, setNotes] = useState("");
  const [reportRecipient, setReportRecipient] = useState("");

  if (!member.can_order) {
    return <LoadState error="Din bruger må ikke bestille opgaver. Kontakt din kundeadministrator." loading={false} />;
  }

  const service = services.data?.find((s) => s.id === serviceId) ?? null;
  const locs = locations.data?.items ?? [];
  const chosen = locationId || (locs[0] ? String(locs[0].id) : NEW);
  const location = locs.find((l) => String(l.id) === chosen) ?? null;
  const contactName = contact.name ?? location?.contact_name ?? "";
  const contactPhone = contact.phone ?? location?.contact_phone ?? "";
  const accessNotes = contact.access ?? location?.access_notes ?? "";
  const pickLocation = (id: string) => { setLocationId(id); setContact({}); };

  const valid = [
    !!service,
    chosen === NEW ? !!newLoc.name.trim() && !!newLoc.address.trim() && !!contactName.trim() : !!location && !!contactName.trim(),
    from <= to && from >= isoDay(0) && (frequency === "enkelt" || (visits >= 2 && visits <= 52)),
    true,
  ];

  const submit = () => {
    const input: OrderInput = {
      service_id: serviceId!,
      ...(chosen === NEW
        ? { new_location: { ...newLoc, contact_name: contactName, contact_phone: contactPhone, access_notes: accessNotes } }
        : { location_id: Number(chosen) }),
      contact_name: contactName, contact_phone: contactPhone, access_notes: accessNotes,
      frequency, ...(frequency === "abonnement" ? { visits } : {}),
      preferred_from: from, preferred_to: to, time_of_day: timeOfDay, subject, notes, report_recipient: reportRecipient,
    };
    void act.run("submit", () => hojde.createOrder(input), () => navigate("/portal/bestillinger"));
  };

  const next = ["Fortsæt til lokation", "Fortsæt til tidspunkt", "Fortsæt til bemærkninger", "Send bestilling"][step];

  return (
    <>
      <div className="hj-stack" style={{ gap: 8 }}>
        <p className="hj-small hj-muted"><Link to="/portal/bestillinger">Bestillinger</Link> › Ny bestilling</p>
        <h1 className="hj-h1">Ny bestilling</h1>
      </div>
      <Steps step={step} />
      <LoadState error={services.error ?? locations.error} loading={!services.data} />
      <div className="hj-cols" style={{ "--basis": "300px" } as React.CSSProperties}>
        <section className="hj-wide hj-stack" style={{ gap: 20 }}>
          {step === 0 && (
            <>
              <h2 className="hj-h2">Hvilken ydelse har du brug for?</h2>
              <div className="hj-grid" style={{ "--min": "260px" } as React.CSSProperties}>
                {services.data?.map((s) => (
                  <ServiceCard key={s.id} line={s.line} title={s.title} description={s.description} specs={s.specs}
                    price={s.needs_quote ? "Pris efter tilbud" : `fra ${formatPrice(s.price_from_ore)}`}
                    priceNote={s.needs_quote ? undefined : s.price_unit}
                    cta={s.id === serviceId ? "Valgt" : "Vælg"} featured={s.id === serviceId} selected={s.id === serviceId}
                    onCta={() => setServiceId(s.id)} />
                ))}
              </div>
            </>
          )}

          {step === 1 && (
            <>
              <h2 className="hj-h2">Hvilken lokation skal vi flyve?</h2>
              <fieldset>
                <legend>Dine lokationer</legend>
                {locs.map((l) => (
                  <Choice key={l.id} name="lok" checked={chosen === String(l.id)} onChange={() => pickLocation(String(l.id))} title={l.name}
                          detail={`${l.address}${l.last_visit ? ` · sidste besøg ${formatDate(l.last_visit)}` : ""}`} />
                ))}
                <Choice name="lok" checked={chosen === NEW} onChange={() => pickLocation(NEW)} title="Ny lokation" detail="Angiv navn og adresse på bygningen eller området" />
              </fieldset>
              {chosen === NEW && (
                <div className="hj-grid">
                  <Input label="Navn" required maxLength={200} value={newLoc.name} onChange={(e) => setNewLoc((n) => ({ ...n, name: e.target.value }))} />
                  <SelectField label="Type" value={newLoc.type} onChange={(e) => setNewLoc((n) => ({ ...n, type: e.target.value as LocationType }))}>
                    {LOCATION_TYPES.map((t) => <option key={t} value={t}>{LOCATION_TYPE_LABEL[t]}</option>)}
                  </SelectField>
                  <Input label="Adresse" required maxLength={300} value={newLoc.address} onChange={(e) => setNewLoc((n) => ({ ...n, address: e.target.value }))} />
                </div>
              )}
              <div className="hj-grid">
                <Input label="Kontaktperson på stedet" required maxLength={200} value={contactName} onChange={(e) => setContact((c) => ({ ...c, name: e.target.value }))} />
                <Input label="Telefon" type="tel" maxLength={40} value={contactPhone} onChange={(e) => setContact((c) => ({ ...c, phone: e.target.value }))} />
              </div>
              <TextareaField label="Adgangsforhold" rows={3} maxLength={2000} value={accessNotes} onChange={(e) => setContact((c) => ({ ...c, access: e.target.value }))} />
            </>
          )}

          {step === 2 && (
            <>
              <h2 className="hj-h2">Hvornår skal vi flyve?</h2>
              <fieldset>
                <legend>Frekvens</legend>
                <Choice name="freq" checked={frequency === "enkelt"} onChange={() => setFrequency("enkelt")} title="Enkelt besøg" detail="Vi flyver én gang inden for det ønskede tidsrum." />
                <Choice name="freq" checked={frequency === "abonnement"} onChange={() => setFrequency("abonnement")} title="Abonnement" detail="Faste besøg, fx hver 4. uge, med sammenligning over tid." />
              </fieldset>
              {frequency === "abonnement" && (
                <Input label="Antal besøg" type="number" min={2} max={52} value={visits} onChange={(e) => setVisits(Number(e.target.value))}
                       error={visits < 2 || visits > 52 ? "Mellem 2 og 52 besøg" : undefined} />
              )}
              <div className="hj-grid" style={{ "--min": "200px" } as React.CSSProperties}>
                <Input label="Tidligst" type="date" min={isoDay(0)} value={from} onChange={(e) => setFrom(e.target.value)} />
                <Input label="Senest" type="date" min={from} value={to} onChange={(e) => setTo(e.target.value)}
                       error={to < from ? "Senest skal være efter tidligst" : undefined} />
                <SelectField label="Tidspunkt på dagen" value={timeOfDay} onChange={(e) => setTimeOfDay(e.target.value as OrderInput["time_of_day"])}>
                  <option value="hele_dagen">Hele dagen</option>
                  <option value="formiddag">Formiddag</option>
                  <option value="eftermiddag">Eftermiddag</option>
                </SelectField>
              </div>
              <p className="hj-small hj-muted">Vi bekræfter dato og klokkeslæt, når flyvningen er planlagt.</p>
            </>
          )}

          {step === 3 && (
            <>
              <h2 className="hj-h2">Er der noget, vi skal vide?</h2>
              <Input label="Hvad skal vi se på?" placeholder="Fx tag og facade" maxLength={200} value={subject} onChange={(e) => setSubject(e.target.value)} />
              <TextareaField label="Bemærkninger" rows={4} maxLength={4000} value={notes} onChange={(e) => setNotes(e.target.value)} />
              <Input label="Rapportmodtager" hint="Fx en bank eller rådgiver, der får rapporten via delt link." maxLength={200}
                     value={reportRecipient} onChange={(e) => setReportRecipient(e.target.value)} />
            </>
          )}

          {act.error && <p className="hj-error" role="alert">{act.error}</p>}
          <div className="hj-row">
            <Button onClick={() => (step === 0 ? navigate("/portal/bestillinger") : setStep(step - 1))}>Tilbage</Button>
            <Button variant="primary" disabled={!valid[step] || !!act.busy} onClick={() => (step === 3 ? submit() : setStep(step + 1))}>{next}</Button>
          </div>
        </section>

        <aside className="hj-summary">
          <h2 className="hj-h2">Din bestilling</h2>
          {service ? (
            <>
              <div><Badge tone={SERVICE_LINE[service.line].tone}>{SERVICE_LINE[service.line].label}</Badge></div>
              <strong>{service.title}</strong>
            </>
          ) : <span className="hj-muted">Vælg en ydelse.</span>}
          <dl>
            <dt>Lokation</dt>
            <dd>{chosen === NEW ? newLoc.name || "Ny lokation" : location?.name ?? "—"}</dd>
            <dt>Frekvens</dt>
            <dd>{frequency === "abonnement" ? `Abonnement, ${visits} besøg` : "Enkelt besøg"}</dd>
            <dt>Pris</dt>
            <dd>{!service ? "—" : service.needs_quote ? "Efter tilbud" : `fra ${formatPrice(service.price_from_ore)} ekskl. moms`}</dd>
          </dl>
          <p className="hj-small hj-muted">Flyvningen kan flyttes ved vind over {MAX_WIND_MS} m/s eller nedbør. Du får besked senest dagen før.</p>
        </aside>
      </div>
    </>
  );
}
