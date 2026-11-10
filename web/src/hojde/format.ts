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
