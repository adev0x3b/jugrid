const number = new Intl.NumberFormat("en", { maximumFractionDigits: 1 });
const whole = new Intl.NumberFormat("en", { maximumFractionDigits: 0 });

export function formatValue(value: number | null | undefined, unit: string): string {
  if (value === null || value === undefined) return "No data";
  return `${number.format(value)} ${unit}`;
}

export function formatKm(km: number): string {
  return `${km >= 100 ? whole.format(km) : number.format(km)} km`;
}

export function formatKv(kv: number | null): string | null {
  return kv === null ? null : `${whole.format(kv)} kV`;
}

/** A score change as signed points out of 100: +12, −3. */
export function formatChange(change: number | null): string {
  if (change === null) return "";
  const points = Math.round(change * 100);
  if (points === 0) return "±0";
  return points > 0 ? `+${points}` : `−${Math.abs(points)}`;
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
}
