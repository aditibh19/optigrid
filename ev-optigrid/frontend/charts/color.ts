/** Interpolates along a list of hex colour stops; t in [0, 1]. */
export function ramp(t: number, stops: string[]): string {
  const clamped = Math.max(0, Math.min(1, Number.isFinite(t) ? t : 0));
  const pos = clamped * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(pos));
  const f = pos - i;
  const a = hexToRgb(stops[i]), b = hexToRgb(stops[i + 1]);
  const mix = (k: 0 | 1 | 2) => Math.round(a[k] + (b[k] - a[k]) * f);
  return `rgb(${mix(0)}, ${mix(1)}, ${mix(2)})`;
}
function hexToRgb(h: string): [number, number, number] {
  const n = parseInt(h.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
/** Power/energy scale: dark (none) -> violet -> cyan (a lot). Matches the app's design tokens. */
export const POWER_STOPS = ["#1B1E29", "#453B7A", "#8B7BFA", "#2DD9E8"];
/** Cost/value scale: cool (low) -> warm (high). */
export const VALUE_STOPS = ["#1D5C66", "#1B1E29", "#6B2E3A", "#FF6E82"];
