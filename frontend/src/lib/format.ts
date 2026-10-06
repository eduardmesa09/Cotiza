// Formato de cifras y fechas para Colombia. La API envía fracciones y texto decimal.

const money = new Intl.NumberFormat("es-CO", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const dateTime = new Intl.DateTimeFormat("es-CO", {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});
const dateOnly = new Intl.DateTimeFormat("es-CO", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });

const DASH = "—";

/** "14592.5" -> "USD 14.592,50" */
export function formatMoney(value: string | number | null | undefined, withCurrency = true): string {
  if (value === null || value === undefined || value === "") return DASH;
  const text = money.format(Number(value));
  return withCurrency ? `USD ${text}` : text;
}

/** Fracción a porcentaje: "0.1502" -> "15,02 %". Sin decimales sobrantes: "0.04" -> "4 %". */
export function formatPercent(fraction: string | number | null | undefined, decimals = 2): string {
  if (fraction === null || fraction === undefined || fraction === "") return DASH;
  const percent = Number(fraction) * 100;
  const text = percent.toFixed(decimals).replace(/\.?0+$/, "").replace(".", ",");
  return `${text} %`;
}

/** Fracción ("0.09") al número que se escribe en un campo de porcentaje ("9"). */
export function fractionToPercentInput(fraction: string | number): string {
  return String(Number((Number(fraction) * 100).toFixed(2)));
}

/** Texto de un campo de porcentaje ("9", "2,5") a la fracción que espera la API ("0.09"). */
export function percentInputToFraction(input: string): string {
  const percent = Number(input.replace(",", ".").trim() || "0");
  if (!Number.isFinite(percent)) return "0";
  return (percent / 100).toFixed(4);
}

export function formatDateTime(iso: string | null | undefined): string {
  return iso ? dateTime.format(new Date(iso)) : DASH;
}

/** Fecha sin hora ("2026-11-04"), sin corrimientos por zona horaria. */
export function formatDate(isoDate: string | null | undefined): string {
  return isoDate ? dateOnly.format(new Date(`${isoDate}T00:00:00Z`)) : DASH;
}

/** Segundos a una duración corta: 3600 -> "1 h", 2700 -> "45 min", 59 -> "59 s". */
export function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s} s`;
  const minutes = Math.floor(s / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `${hours} h ${rest} min` : `${hours} h`;
}

/** Valor de un indicador con su unidad: (7.67, "min") -> "7,7 min". */
export function formatKpi(value: number | null, unit: string): string {
  if (value === null) return DASH;
  const text = (Math.round(value * 10) / 10).toString().replace(".", ",");
  return `${text} ${unit}`;
}

/** Fecha y hora local para un campo datetime-local ("2026-10-05T10:00"). */
export function toLocalInput(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}
