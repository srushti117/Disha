export const LEVEL_COLOR: Record<string, string> = { P1: "#d62f35", P2: "#e0721a", P3: "#d9a400", P4: "#6b7a90" };
export const LEVEL_NAME: Record<string, string> = { P1: "CRITICAL", P2: "HIGH", P3: "MODERATE", P4: "LOW" };
export const HAZARD_LABEL: Record<string, string> = { flood: "Flood", wildfire: "Wildfire", landslide: "Landslide", cyclone: "Cyclone" };

export const pct = (v: number | null | undefined, d = 0) => (v === null || v === undefined || Number.isNaN(v) ? "-" : `${(v * 100).toFixed(d)}%`);
export const num = (v: number | null | undefined) => (v === null || v === undefined ? "-" : Math.round(v).toLocaleString());
export const fixed = (v: number | null | undefined, d = 1) => (v === null || v === undefined ? "-" : v.toFixed(d));

export function hhmm(iso?: string | null) {
  if (!iso) return "-";
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}
export function dt(iso?: string | null) {
  if (!iso) return "-";
  const d = new Date(iso);
  return d.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}
export function ago(iso?: string | null) {
  if (!iso) return "-";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 90) return "just now";
  if (s < 5400) return `${Math.round(s / 60)} min ago`;
  if (s < 86400 * 2) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} d ago`;
}
export function confColor(label?: string) {
  if (!label) return "#5d6f87";
  if (label.startsWith("HIGH")) return "#1f9d6b";
  if (label.startsWith("MEDIUM")) return "#b58500";
  if (label.startsWith("LOW")) return "#e0721a";
  return "#d62f35";
}
export function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}
