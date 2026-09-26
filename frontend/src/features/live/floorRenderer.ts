// Canvas drawing for the 2D floor twin (port of reference/refsim/viewer drawFloor).
// Static layer (zones, labels, readers) is cached per floor and size; the dynamic layer
// (overlay, rooms, desks, truth dots) is drawn only when the store is dirty or dots are moving.

import type { Dot, LiveStore } from "./store";
import {
  DESK_GLOW,
  DESK_GLOW_SCALE,
  DESK_HIT_RADIUS,
  DESK_PULSE_MS,
  DESK_PULSE_SCALE,
  DESK_SIZE,
  DOT_TWEEN_MS,
  HVAC_FILL,
  TWIN,
  roomFill,
  temperatureFill,
} from "./theme";
import type { LiveLayout } from "./types";

export type Overlay = "occupancy" | "temperature" | "hvac";
export type View = "operational" | "simulation";

type Zone = LiveLayout["zones"][number];
type Room = LiveLayout["rooms"][number];
type Workspace = LiveLayout["workspaces"][number];
type Reader = LiveLayout["access_points"][number];

export interface FloorScene {
  floorId: string;
  width: number;
  height: number;
  zones: Zone[];
  rooms: Room[];
  workspaces: Workspace[];
  readers: Reader[];
}

export interface Geometry {
  scale: number;
  ox: number;
  oy: number;
  dpr: number;
}

const WORK_ZONES = new Set(["OPEN_WORKSPACE", "TEAM_NEIGHBORHOOD"]);
const HALL_ZONES = new Set(["ENTRANCE", "CIRCULATION"]);

export function buildScene(layout: LiveLayout, floorId: string): FloorScene {
  const floor = layout.floors.find((f) => f.floor_id === floorId) ?? layout.floors[0];
  const id = floor?.floor_id ?? floorId;
  return {
    floorId: id,
    width: floor?.width ?? 1,
    height: floor?.height ?? 1,
    zones: layout.zones.filter((z) => z.floor_id === id),
    rooms: layout.rooms.filter((r) => r.floor_id === id),
    workspaces: layout.workspaces.filter((w) => w.floor_id === id),
    readers: layout.access_points.filter((a) => a.floor_id === id),
  };
}

export function geometry(canvas: HTMLCanvasElement, scene: FloorScene): Geometry {
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const w = Math.max(1, Math.round(rect.width * dpr));
  const h = Math.max(1, Math.round(rect.height * dpr));
  if (canvas.width !== w || canvas.height !== h) {
    canvas.width = w;
    canvas.height = h;
  }
  const scale = Math.min(w / scene.width, h / scene.height) * 0.98;
  return { scale, ox: (w - scene.width * scale) / 2, oy: (h - scene.height * scale) / 2, dpr };
}

const staticCache = new Map<string, HTMLCanvasElement>();

function staticLayer(scene: FloorScene, g: Geometry, w: number, h: number): HTMLCanvasElement | null {
  const key = `${scene.floorId}|${w}x${h}`;
  const cached = staticCache.get(key);
  if (cached) return cached;
  const layer = document.createElement("canvas");
  layer.width = w;
  layer.height = h;
  const x = layer.getContext("2d");
  if (!x) return null;
  const X = (v: number) => g.ox + v * g.scale;
  const Y = (v: number) => g.oy + v * g.scale;
  const zonesWithRooms = new Set(scene.rooms.map((r) => r.zone_id));
  for (const z of scene.zones) {
    x.fillStyle = WORK_ZONES.has(z.zone_type) ? TWIN.zoneWork : HALL_ZONES.has(z.zone_type) ? TWIN.zoneHall : TWIN.zoneOther;
    x.fillRect(X(z.x), Y(z.y), z.width * g.scale, z.height * g.scale);
    x.strokeStyle = z.is_restricted ? TWIN.restricted : TWIN.zoneBorder;
    x.setLineDash(z.is_restricted ? [6 * g.dpr, 4 * g.dpr] : []);
    x.lineWidth = g.dpr;
    x.strokeRect(X(z.x), Y(z.y), z.width * g.scale, z.height * g.scale);
    x.setLineDash([]);
    if (!zonesWithRooms.has(z.zone_id)) {
      // Rooms carry their own labels; label only zones without rooms.
      x.fillStyle = z.is_restricted ? TWIN.restricted : TWIN.label;
      x.font = `${11 * g.dpr}px system-ui`;
      x.fillText(z.name + (z.is_restricted ? "  · restricted" : ""), X(z.x) + 4 * g.dpr, Y(z.y) + 13 * g.dpr);
    }
  }
  for (const a of scene.readers) {
    x.fillStyle =
      a.reader_type === "SECURE_ZONE" ? TWIN.readerSecure : a.reader_type === "ROOM_DOOR" ? TWIN.readerDoor : TWIN.readerEntrance;
    const px = X(a.x);
    const py = Y(a.y);
    const s = 5 * g.dpr;
    x.beginPath();
    x.moveTo(px, py - s);
    x.lineTo(px + s, py + s);
    x.lineTo(px - s, py + s);
    x.fill();
  }
  staticCache.clear(); // keep only the current floor/size
  staticCache.set(key, layer);
  return layer;
}

function ease(k: number): number {
  return k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
}

/** Draws one frame. Returns true while dots tween or desk pulses fade (caller keeps redrawing). */
export function drawFloor(
  canvas: HTMLCanvasElement,
  scene: FloorScene,
  store: LiveStore,
  view: View,
  overlay: Overlay,
  deptColor: Record<string, string>,
  now: number,
): boolean {
  const ctx = canvas.getContext("2d");
  if (!ctx) return false;
  const g = geometry(canvas, scene);
  const X = (v: number) => g.ox + v * g.scale;
  const Y = (v: number) => g.oy + v * g.scale;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const base = staticLayer(scene, g, canvas.width, canvas.height);
  if (base) ctx.drawImage(base, 0, 0);

  if (overlay !== "occupancy") {
    for (const z of scene.zones) {
      const zs = store.zones[z.zone_id];
      ctx.fillStyle = overlay === "temperature" ? temperatureFill(zs?.[0]) : (HVAC_FILL[zs?.[2] ?? "NORMAL"] ?? HVAC_FILL.NORMAL!);
      ctx.fillRect(X(z.x), Y(z.y), z.width * g.scale, z.height * g.scale);
      if (zs) {
        ctx.fillStyle = TWIN.isoText;
        ctx.font = `${10 * g.dpr}px system-ui`;
        const label = overlay === "temperature" ? `${zs[0] ?? "–"} °C · ${zs[1] ?? "–"} ppm` : zs[2];
        ctx.fillText(label, X(z.x) + 4 * g.dpr, Y(z.y + z.height) - 5 * g.dpr);
      }
    }
  }

  for (const r of scene.rooms) {
    const n = store.rooms[r.room_id] ?? 0;
    ctx.fillStyle = roomFill(n, r.capacity);
    ctx.fillRect(X(r.x), Y(r.y), r.width * g.scale, r.height * g.scale);
    ctx.strokeStyle = n > r.capacity ? TWIN.over : TWIN.roomBorder;
    ctx.lineWidth = g.dpr;
    ctx.strokeRect(X(r.x), Y(r.y), r.width * g.scale, r.height * g.scale);
    // Short label clipped to the room: "1.04 3/8", "Auditorium 13/80", "CAFETERIA 15/150".
    const name = r.area_subtype ?? r.name.replace(/^Room /, "");
    ctx.save();
    ctx.beginPath();
    ctx.rect(X(r.x), Y(r.y), r.width * g.scale, r.height * g.scale);
    ctx.clip();
    ctx.fillStyle = TWIN.isoText;
    ctx.font = `${10 * g.dpr}px system-ui`;
    ctx.fillText(`${name} ${n}/${r.capacity}`, X(r.x) + 3 * g.dpr, Y(r.y) + 12 * g.dpr);
    ctx.restore();
  }

  const s = DESK_SIZE * g.scale;
  const glow = s * DESK_GLOW_SCALE;
  // Glow halo under occupied desks ("desk lights on").
  ctx.fillStyle = DESK_GLOW;
  for (const w of scene.workspaces) {
    if (store.desks[w.workspace_id]?.[0]) ctx.fillRect(X(w.x) - glow / 2, Y(w.y) - glow / 2, glow, glow);
  }
  let pulsing = false;
  for (const w of scene.workspaces) {
    const d = store.desks[w.workspace_id] ?? [0, 0];
    const colour = d[0] ? TWIN.occupied : d[1] ? TWIN.held : TWIN.vacant;
    ctx.fillStyle = colour;
    ctx.fillRect(X(w.x) - s / 2, Y(w.y) - s / 2, s, s);
    // Expanding, fading ring right after the desk changed state.
    const changed = store.deskPulses.get(w.workspace_id);
    if (changed !== undefined) {
      const k = (now - changed) / DESK_PULSE_MS;
      if (k >= 1 || k < 0) {
        store.deskPulses.delete(w.workspace_id);
      } else if (d[0] || d[1]) {
        pulsing = true;
        const r = (s / 2) * (1 + (DESK_PULSE_SCALE - 1) * k);
        ctx.strokeStyle = colour;
        ctx.globalAlpha = 1 - k;
        ctx.lineWidth = 1.5 * g.dpr;
        ctx.strokeRect(X(w.x) - r, Y(w.y) - r, r * 2, r * 2);
        ctx.globalAlpha = 1;
      }
    }
  }

  let moving = pulsing;
  if (view === "simulation") {
    const radius = Math.max(2 * g.dpr, 0.45 * g.scale);
    for (const p of store.dots.values()) {
      if (p.floor !== scene.floorId) continue;
      moving = tweenDot(p, now) || moving;
      ctx.fillStyle = deptColor[p.dept] ?? TWIN.selected;
      ctx.beginPath();
      ctx.arc(X(p.x), Y(p.y), radius, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  return moving;
}

function tweenDot(p: Dot, now: number): boolean {
  const k = Math.min(1, (now - p.t0) / DOT_TWEEN_MS);
  const e = ease(k);
  p.x = p.fromX + (p.toX - p.fromX) * e;
  p.y = p.fromY + (p.toY - p.fromY) * e;
  return k < 1;
}

export type Pick = { kind: "desk"; id: string } | { kind: "room"; id: string } | null;

/** Hit-test a click (CSS pixels relative to the canvas) against desks, then rooms. */
export function pick(canvas: HTMLCanvasElement, scene: FloorScene, cssX: number, cssY: number): Pick {
  const g = geometry(canvas, scene);
  const lx = (cssX * g.dpr - g.ox) / g.scale;
  const ly = (cssY * g.dpr - g.oy) / g.scale;
  let best: Workspace | null = null;
  let bestDist = DESK_HIT_RADIUS;
  for (const w of scene.workspaces) {
    const d = Math.hypot(w.x - lx, w.y - ly);
    if (d < bestDist) {
      bestDist = d;
      best = w;
    }
  }
  if (best) return { kind: "desk", id: best.workspace_id };
  const room = scene.rooms.find((r) => lx >= r.x && lx <= r.x + r.width && ly >= r.y && ly <= r.y + r.height);
  return room ? { kind: "room", id: room.room_id } : null;
}
