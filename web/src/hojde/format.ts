// Danish formatting as on Højde's screens: dates DD.MM.YYYY, times HH:MM, numbers with Danish separators
// (12.480 · 3,8). Always in Danish time. Ported from surdej-v2 member-hojde shared/src/format.ts.

export const TIME_ZONE = "Europe/Copenhagen";

type DateInput = Date | string | number;

const partsFmt = new Intl.DateTimeFormat("da-DK", {
  timeZone: TIME_ZONE, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
  hourCycle: "h23",
});

function parts(d: DateInput): Record<string, string> {
  const out: Record<string, string> = {};
  for (const p of partsFmt.formatToParts(new Date(d))) out[p.type] = p.value;
  return out;
}

/** 02.10.2026 */
export function formatDate(d: DateInput): string {
  const p = parts(d);
  return `${p.day}.${p.month}.${p.year}`;
}

/** 14.10 */
export function formatDayMonth(d: DateInput): string {
  const p = parts(d);
  return `${p.day}.${p.month}`;
}

/** 08:00 */
export function formatTime(d: DateInput): string {
  const p = parts(d);
  return `${p.hour}:${p.minute}`;
}

/** 14.10.2026 kl. 08 — minutes only when they aren't :00. */
export function formatPlanned(d: DateInput): string {
  const p = parts(d);
  return `${formatDate(d)} kl. ${p.minute === "00" ? p.hour : `${p.hour}:${p.minute}`}`;
}

/** 12.480 · 3,8 · 0,94 */
export function formatNumber(n: number, decimals?: number): string {
  return new Intl.NumberFormat("da-DK", decimals === undefined
    ? { maximumFractionDigits: 2 }
    : { minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(n);
}

/** Amounts are stored in øre; shown as "12.500 kr." — null shows the screens' placeholder. */
export function formatPrice(ore: number | null | undefined, placeholder = "[PRIS]"): string {
  if (ore === null || ore === undefined) return `${placeholder} kr.`;
  return `${formatNumber(ore / 100, ore % 100 === 0 ? 0 : 2)} kr.`;
}

/** "Godmorgen" / "Goddag" / "Godaften" by Danish local hour. */
export function greeting(now: Date = new Date()): string {
  const h = parseInt(parts(now).hour, 10);
  return h < 10 ? "Godmorgen" : h < 18 ? "Goddag" : "Godaften";
}

/** "MH" for "Mette Holm". */
export function initials(name: string): string {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]!.toUpperCase()).join("");
}

/** YYYY-MM-DD in Danish time, `offsetDays` from today. */
export function isoDay(offsetDays = 0): string {
  const d = new Date(Date.now() + offsetDays * 86_400_000);
  const p = parts(d);
  return `${p.year}-${p.month}-${p.day}`;
}

/** 09.10.2026 09:12 */
export function formatDateTime(d: DateInput): string {
  return `${formatDate(d)} ${formatTime(d)}`;
}

const WEEKDAYS = ["Søn", "Man", "Tir", "Ons", "Tor", "Fre", "Lør"];
const WEEKDAYS_LONG = ["Søndag", "Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag", "Lørdag"];

function weekday(d: DateInput): number {
  const p = parts(d);
  return new Date(Date.UTC(Number(p.year), Number(p.month) - 1, Number(p.day))).getUTCDay();
}

/** Man 12.10 */
export function formatWeekdayShort(d: DateInput): string {
  return `${WEEKDAYS[weekday(d)]} ${formatDayMonth(d)}`;
}

/** Tirsdag 13.10.2026 */
export function formatLongDate(d: DateInput): string {
  return `${WEEKDAYS_LONG[weekday(d)]} ${formatDate(d)}`;
}

/** The Danish day (YYYY-MM-DD) and time (HH:MM) of an instant. */
export function localParts(d: DateInput): { day: string; time: string } {
  const p = parts(d);
  return { day: `${p.year}-${p.month}-${p.day}`, time: `${p.hour}:${p.minute}` };
}

/** The instant (ISO) of a Danish wall-clock time — independent of the browser's own time zone. */
export function danishInstant(day: string, time: string): string {
  const [y, m, dd] = day.split("-").map(Number);
  const [hh, mm] = time.split(":").map(Number);
  const wall = Date.UTC(y, m - 1, dd, hh, mm);
  const offset = (t: number) => {
    const p = parts(t);
    return Date.UTC(Number(p.year), Number(p.month) - 1, Number(p.day), Number(p.hour), Number(p.minute)) - Math.floor(t / 60000) * 60000;
  };
  let t = wall - offset(wall);
  t = wall - offset(t); // across a change to or from summer time
  return new Date(t).toISOString();
}

/** YYYY-MM-DD plus n days. */
export function addDays(day: string, n: number): string {
  const d = new Date(`${day}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}
