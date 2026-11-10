// The Højde design system's five components (Button, Badge, Input, Stat, ServiceCard) with the props they have in the
// design, plus the shells' repeated pieces (card, table, tabs, page head). Styles: hojde.css (scoped to .hj).
import { useCallback, useEffect, useId, useRef, useState, type ButtonHTMLAttributes, type InputHTMLAttributes,
  type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { Link } from "react-router-dom";
import { errorText } from "../api";
import { SERVICE_LINE, type Meta, type ServiceLine, type Severity, type Tone } from "./api";

const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

// ── Button ─────────────────────────────────────────────────────────────────────────────────────────────────

type ButtonVariant = "primary" | "secondary" | "quiet";

export function Button({ variant = "secondary", size = "md", className, type = "button", ...props }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant; size?: "md" | "sm" }) {
  return <button type={type} {...props} className={cx("hj-btn", variant !== "secondary" && `hj-btn--${variant}`, size === "sm" && "hj-btn--sm", className)} />;
}

/** A link styled as a button (navigation, not an action). */
export function ButtonLink({ to, variant = "secondary", size = "md", children }: { to: string; variant?: ButtonVariant; size?: "md" | "sm"; children: ReactNode }) {
  return <Link to={to} className={cx("hj-btn", variant !== "secondary" && `hj-btn--${variant}`, size === "sm" && "hj-btn--sm")}>{children}</Link>;
}

// ── Badge ──────────────────────────────────────────────────────────────────────────────────────────────────

export function Badge({ tone = "neutral", dot, children }: { tone?: Tone; dot?: boolean; children: ReactNode }) {
  return (
    <span className={cx("hj-badge", tone !== "neutral" && `hj-badge--${tone}`)}>
      {dot && <span className="hj-dot" aria-hidden="true" />}
      {children}
    </span>
  );
}

export function StatusBadge({ meta, children }: { meta: Meta; children?: ReactNode }) {
  return <Badge tone={meta.tone} dot={meta.dot}>{children ?? meta.label}</Badge>;
}

// ── Fields ─────────────────────────────────────────────────────────────────────────────────────────────────

export function Input({ label, hint, error, wide, id, ...props }: InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string; error?: string; wide?: boolean }) {
  const auto = useId();
  const inputId = id ?? auto;
  const hintId = `${inputId}-hint`;
  return (
    <div className={cx("hj-field", wide && "hj-field--wide")}>
      <label htmlFor={inputId} className="hj-label">{label}</label>
      <input id={inputId} {...props} className="hj-control" aria-invalid={error ? true : undefined}
             aria-describedby={hint || error ? hintId : undefined} />
      {error ? <span id={hintId} className="hj-error">{error}</span> : hint ? <span id={hintId} className="hj-hint">{hint}</span> : null}
    </div>
  );
}

export function SelectField({ label, children, ...props }: SelectHTMLAttributes<HTMLSelectElement> & { label: string }) {
  const id = useId();
  return (
    <div className="hj-field">
      <label htmlFor={id} className="hj-label">{label}</label>
      <select id={id} {...props} className="hj-control">{children}</select>
    </div>
  );
}

export function TextareaField({ label, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement> & { label: string }) {
  const id = useId();
  return (
    <div className="hj-field hj-field--wide">
      <label htmlFor={id} className="hj-label">{label}</label>
      <textarea id={id} {...props} className="hj-control" />
    </div>
  );
}

// ── Stat ───────────────────────────────────────────────────────────────────────────────────────────────────

export function Stat({ label, value, unit, delta, trend = "flat" }: { label: string; value: ReactNode; unit?: string; delta?: string; trend?: "up" | "down" | "flat" }) {
  return (
    <div className="hj-stat">
      <span className="hj-stat-label">{label}</span>
      <span className="hj-stat-value">{value}{unit && <small>{unit}</small>}</span>
      {delta && (
        <span className={cx("hj-stat-delta", trend === "up" && "up", trend === "down" && "down")}>
          {trend === "up" ? "▲ " : trend === "down" ? "▼ " : "– "}{delta}
        </span>
      )}
    </div>
  );
}

// ── ServiceCard ────────────────────────────────────────────────────────────────────────────────────────────

export function ServiceCard({ line, title, description, specs, price, priceNote, cta, featured, selected, onCta }: {
  line: ServiceLine; title: string; description?: string; specs?: string[]; price?: string; priceNote?: string;
  cta?: string; featured?: boolean; selected?: boolean; onCta?: () => void;
}) {
  const l = SERVICE_LINE[line];
  return (
    <article className={cx("hj-service", selected && "selected")}>
      <div><Badge tone={l.tone}>{l.label}</Badge></div>
      <h3>{title}</h3>
      {description && <p>{description}</p>}
      {specs && specs.length > 0 && <ul>{specs.map((s) => <li key={s}>{s}</li>)}</ul>}
      {(price || cta) && (
        <div className="hj-service-foot">
          <span>{price}{priceNote && <small> {priceNote}</small>}</span>
          {cta && <Button size="sm" variant={featured ? "primary" : "secondary"} onClick={onCta} aria-pressed={selected}>{cta}</Button>}
        </div>
      )}
    </article>
  );
}

// ── Layout ─────────────────────────────────────────────────────────────────────────────────────────────────

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <section className={cx("hj-card", className)}>{children}</section>;
}

export function SectionHead({ title, link }: { title: string; link?: ReactNode }) {
  return <div className="hj-section-head"><h2 className="hj-h2">{title}</h2>{link}</div>;
}

export function PageHead({ crumb, eyebrow, title, meta, actions }: { crumb?: ReactNode; eyebrow?: string; title: string; meta?: ReactNode; actions?: ReactNode }) {
  return (
    <>
      {crumb && <p className="hj-small hj-muted">{crumb}</p>}
      <div className="hj-head">
        <div>
          {eyebrow && <p className="hj-small hj-muted">{eyebrow}</p>}
          <h1 className="hj-h1">{title}</h1>
          {meta && <div className="hj-row">{meta}</div>}
        </div>
        {actions && <div className="hj-row">{actions}</div>}
      </div>
    </>
  );
}

export function Table({ head, children, minWidth = 680, bare }: { head: ReactNode[]; children: ReactNode; minWidth?: number; bare?: boolean }) {
  return (
    <div className={cx("hj-table-wrap", bare && "hj-table-wrap--bare")}>
      <table className="hj-table" style={{ minWidth }}>
        <thead><tr>{head.map((h, i) => <th key={i} scope="col">{h}</th>)}</tr></thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

export function Tabs<K extends string>({ label, tabs, value, onChange }: { label: string; tabs: { key: K; label: string }[]; value: K; onChange: (k: K) => void }) {
  return (
    <div role="tablist" aria-label={label} className="hj-tabs">
      {tabs.map((t) => (
        <button key={t.key} type="button" role="tab" aria-selected={t.key === value} className="hj-tab" onClick={() => onChange(t.key)}>
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function Notice({ tone = "warning", children }: { tone?: "warning" | "danger" | "kote"; children: ReactNode }) {
  return <section className={cx("hj-notice", tone !== "warning" && `hj-notice--${tone}`)}>{children}</section>;
}

export function LoadState({ error, loading }: { error: string | null; loading: boolean }) {
  if (error) return <Notice tone="danger"><span role="alert">{error}</span></Notice>;
  if (loading) return <p className="hj-small hj-muted">Henter …</p>;
  return null;
}

/** Map and 3D are out of scope for now: points placed relative to each other, as a real map gets them later. */
export type MapPoint = { id: number; lat: number; lng: number; label: string; severity?: Severity };

export function MapPlaceholder({ points, caption, height = 420, onSelect }: { points: MapPoint[]; caption: string; height?: number; onSelect?: (id: number) => void }) {
  const lats = points.map((p) => p.lat);
  const lngs = points.map((p) => p.lng);
  const [minLat, maxLat, minLng, maxLng] = [Math.min(...lats), Math.max(...lats), Math.min(...lngs), Math.max(...lngs)];
  return (
    <div className="hj-map" style={{ height }} role="img" aria-label={caption}>
      <div className="hj-map-caption">[{caption}]</div>
      {points.map((p, i) => (
        <button key={p.id} type="button" title={p.label} aria-label={p.label}
                className={cx("hj-pin", p.severity && `sev-${p.severity}`, onSelect && "clickable")}
                onClick={onSelect ? () => onSelect(p.id) : undefined}
                style={{
                  left: `${maxLng === minLng ? 50 : 10 + ((p.lng - minLng) / (maxLng - minLng)) * 80}%`,
                  top: `${maxLat === minLat ? 50 : 10 + ((maxLat - p.lat) / (maxLat - minLat)) * 80}%`,
                }}>
          {i + 1}
        </button>
      ))}
    </div>
  );
}

// ── Data ───────────────────────────────────────────────────────────────────────────────────────────────────

/** Loads data for a screen; refetches when `deps` change and on reload(). Previous data stays while loading. */
export function useAsync<T>(load: () => Promise<T>, deps: unknown[]) {
  const [state, setState] = useState<{ data: T | null; error: string | null; loading: boolean }>({ data: null, error: null, loading: true });
  const seq = useRef(0);
  const run = useCallback(load, deps); // eslint-disable-line react-hooks/exhaustive-deps
  const reload = useCallback(() => {
    const n = ++seq.current;
    setState((s) => ({ ...s, loading: true }));
    run().then(
      (data) => n === seq.current && setState({ data, error: null, loading: false }),
      (e: unknown) => n === seq.current && setState((s) => ({ ...s, error: errorText(e), loading: false })),
    );
  }, [run]);
  useEffect(() => { reload(); }, [reload]);
  const setData = useCallback((data: T) => setState((s) => ({ ...s, data })), []);
  return { ...state, reload, setData };
}

/** Runs a change: tracks which one is busy and the server's message, and hands the result on. */
export function useAction() {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const run = useCallback(async <R,>(key: string, fn: () => Promise<R>, onDone?: (r: R) => void) => {
    setBusy(key);
    setError(null);
    try {
      const r = await fn();
      onDone?.(r);
      return r;
    } catch (e) {
      setError(errorText(e));
      return undefined;
    } finally {
      setBusy(null);
    }
  }, []);
  return { busy, error, run };
}
