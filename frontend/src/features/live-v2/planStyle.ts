// Presentation helpers for the v2 floor plan (colours come from CSS variables in twin-v2.css).

import type { AreaValue, Chip } from "./types";

/** Temperature ramp: 21 cold blue -> 22.5 cool -> 24.5 comfort -> 26 warm -> 27.5 hot (70% fill). */
const TEMP_STOPS: [number, string][] = [
  [21, "var(--t-cold)"],
  [22.5, "var(--t-cool)"],
  [24.5, "var(--t-comfort)"],
  [26, "var(--t-warm)"],
  [27.5, "var(--t-hot)"],
];

export function temperatureFill(t: number | null): string {
  if (t == null) return "transparent";
  let a = TEMP_STOPS[0]!;
  let b = TEMP_STOPS[TEMP_STOPS.length - 1]!;
  if (t <= a[0]) b = a;
  for (let i = 0; i < TEMP_STOPS.length - 1; i++) {
    const lo = TEMP_STOPS[i]!;
    const hi = TEMP_STOPS[i + 1]!;
    if (t >= lo[0] && t <= hi[0]) {
      a = lo;
      b = hi;
    }
  }
  const k = b[0] === a[0] ? 1 : Math.max(0, Math.min(1, (t - a[0]) / (b[0] - a[0])));
  const mixed = `color-mix(in srgb, ${b[1]} ${Math.round(k * 100)}%, ${a[1]})`;
  return `color-mix(in srgb, ${mixed} 70%, transparent)`;
}

/** Trend label for the 15-minute change delivered by the backend (▲ warm, ▼ cool, → steady). */
export function trendArrow(delta: number | null | undefined): { text: string; colour: string; cls: string } {
  if (delta == null || Math.abs(delta) < 0.2) return { text: "→", colour: "var(--ink-3)", cls: "" };
  return delta > 0
    ? { text: `▲${delta.toFixed(1)}`, colour: "var(--warm)", cls: "up" }
    : { text: `▼${(-delta).toFixed(1)}`, colour: "var(--cool)", cls: "down" };
}

export function lightFill(level: number): string {
  if (level >= 100) return "var(--l-full)";
  if (level >= 70) return "var(--l-day)";
  if (level > 0) return "var(--l-dim)";
  return "var(--l-off)";
}

export const HVAC_LABEL: Record<string, [string, string]> = {
  ECO: ["Eco", "var(--h-eco)"],
  PRECOOL: ["Pre-cool", "var(--h-precool)"],
  HIGH: ["High", "var(--h-high)"],
  BOOST: ["Vent boost", "var(--h-high)"],
};

/** HVAC state to show: ventilation boost wins over the mode; NORMAL shows no tint. */
export function hvacState(v: AreaValue | undefined): [string, string] | null {
  if (!v) return null;
  if (v[6]) return HVAC_LABEL.BOOST!;
  return HVAC_LABEL[v[3]] ?? null;
}

export const HVAC_NAME: Record<string, string> = {
  ECO: "Eco",
  NORMAL: "Normal",
  HIGH: "High",
  PRECOOL: "Pre-cool",
};

export type RoomBadge = Chip | "booked";

export const CHIP_TEXT: Record<RoomBadge, [long: string, short: string]> = {
  released: ["Released", "Released"],
  over: ["Over capacity", "Over"],
  too_big: ["Oversized", "Too big"],
  booked: ["Booked", "Booked"],
};

export const CHIP_COLOURS: Record<RoomBadge, [fg: string, bg: string]> = {
  released: ["var(--released)", "var(--released-bg)"],
  over: ["var(--danger)", "var(--danger-bg)"],
  too_big: ["var(--warn)", "var(--warn-bg)"],
  booked: ["var(--ink-2)", "var(--z-meet)"],
};

export const COMMON_ZONE_TYPES = new Set(["COLLABORATION", "LOUNGE", "CAFETERIA"]);

/** Department dot colours (floor-twin-design-v2.md: palette unchanged; extended to 9 departments). */
export const DEPT_COLOURS = ["#2F6FDE", "#C2417A", "#0F8F6E", "#C07A0A", "#6D3FD1", "#D0452F", "#11879E", "#7A8B1C", "#8A5A00"];
