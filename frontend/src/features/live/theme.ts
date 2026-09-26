// Canvas colours for the Live Simulation screen. Mirrors the --color-twin-* tokens in index.css
// (docs/visualization-spec.md §2); canvases cannot use Tailwind classes, so they read these.

export const TWIN = {
  bg: "#0e1117",
  panel: "#161b24",
  line: "#262e3b",
  text: "#e6e9ef",
  muted: "#8a94a6",
  label: "#6b7689",
  accent: "#4f8cff",
  occupied: "#22c55e",
  held: "#f59e0b",
  vacant: "#334155",
  roomEmpty: "#1a2230",
  roomBorder: "#334155",
  over: "#ef4444",
  zoneWork: "#131a24",
  zoneHall: "#10151d",
  zoneOther: "#121822",
  zoneBorder: "#2a3444",
  restricted: "#ef4444",
  readerEntrance: "#e2e8f0",
  readerDoor: "#38bdf8",
  readerSecure: "#ef4444",
  anonymous: "#a78bfa",
  isoText: "#e2e8f0",
  isoEdge: "#475569",
  selected: "#ffffff",
} as const;

export const DEPARTMENT_PALETTE = ["#60a5fa", "#f472b6", "#34d399", "#fbbf24", "#a78bfa", "#f87171", "#2dd4bf", "#fb923c"];

export const HVAC_FILL: Record<string, string> = {
  ECO: "rgba(34,197,94,.25)",
  NORMAL: "rgba(148,163,184,.12)",
  HIGH: "rgba(249,115,22,.3)",
};

export const HVAC_LEGEND: [string, string][] = [
  ["#22c55e", "ECO"],
  ["#94a3b8", "NORMAL"],
  ["#f97316", "HIGH"],
];

export const TEMP_LEGEND: [string, string][] = [
  ["#3b82f6", "≤21 °C"],
  ["#a855f7", "24 °C"],
  ["#ef4444", "≥27 °C"],
];

export const OCCUPANCY_LEGEND: [string, string][] = [
  [TWIN.occupied, "Occupied (sensor)"],
  [TWIN.held, "Logged in, vacant"],
  [TWIN.vacant, "Vacant"],
  [TWIN.accent, "Room occupied (count)"],
];

/** Temperature ramp 21 °C blue -> 24 °C purple -> 27 °C red (overlay fill). */
export function temperatureFill(t: number | null | undefined): string {
  if (t == null) return "#1e293b";
  const k = Math.max(0, Math.min(1, (t - 21) / 6));
  return `rgba(${Math.round(60 + 195 * k)},${Math.round(130 - 60 * k)},${Math.round(255 - 200 * k)},0.35)`;
}

/** Utilisation colour scale green -> red for the isometric floors. */
export function utilisationFill(pct: number): string {
  const u = Math.min(1, Math.max(0, pct / 100));
  return `hsla(${140 - 140 * u}, 70%, ${22 + 30 * u}%, .95)`;
}

/** Room fill scaled by count/capacity (rendering scale only). */
export function roomFill(count: number, capacity: number): string {
  if (!count) return TWIN.roomEmpty;
  const u = Math.min(1, count / Math.max(1, capacity));
  return `rgba(79,140,255,${0.15 + 0.55 * u})`;
}

/** Desk square size and click radius in layout units (metres). */
export const DESK_SIZE = 1.6;
export const DESK_HIT_RADIUS = 2.0;
/** Dot tween duration (ms), docs/live-streaming.md §5. */
export const DOT_TWEEN_MS = 900;
