import type {
  AutomationLine,
  DeskValue,
  FeedLine,
  Kpis,
  LiveMessage,
  SeriesPoint,
  StatusInfo,
  TruthPosition,
  TruthSummary,
  ZoneValue,
} from "./types";

/** A truth dot with its tween state (Simulation View only). */
export interface Dot {
  x: number;
  y: number;
  fromX: number;
  fromY: number;
  toX: number;
  toY: number;
  t0: number;
  floor: string;
  dept: string;
  state: string;
}

const FEED_CAP = 120;
const PANEL_REFRESH_MS = 450;

/**
 * Mutable live state outside React. Canvases read it every animation frame (when `dirty`);
 * panels subscribe and re-render at most every PANEL_REFRESH_MS. Nothing here computes
 * utilisation: values arrive computed from the server and are merged as-is.
 */
export class LiveStore {
  status: StatusInfo | null = null;
  desks: Record<string, DeskValue> = {};
  rooms: Record<string, number> = {};
  zones: Record<string, ZoneValue> = {};
  kpis: Kpis | null = null;
  series: SeriesPoint[] = [];
  feed: FeedLine[] = [];
  automation: AutomationLine[] = [];
  eventsTotal = 0;
  dots = new Map<string, Dot>();
  /** Desk id -> time its state last changed (drives the pulse ring). */
  deskPulses = new Map<string, number>();
  truthSummary: TruthSummary | null = null;
  /** Canvas needs a redraw. */
  dirty = true;

  private listeners = new Set<() => void>();
  private revision = 0;
  private notifyTimer: ReturnType<typeof setTimeout> | null = null;
  private lastNotify = Number.NEGATIVE_INFINITY; // first update renders immediately

  constructor(private readonly now: () => number = () => performance.now()) {}

  apply(msg: LiveMessage): void {
    this.status = {
      run_id: msg.run_id,
      status: msg.status,
      speed: msg.speed,
      allowed_speeds: msg.allowed_speeds,
      sim_time: msg.sim_time,
      events_generated: msg.events_generated,
    };
    this.kpis = msg.kpis;
    this.eventsTotal = msg.events_total;
    this.automation = msg.automation;
    if (msg.type === "snapshot") {
      this.desks = { ...msg.desks };
      this.rooms = { ...msg.rooms };
      this.zones = { ...msg.zones };
      this.series = [...msg.series];
      this.feed = [];
      this.dots.clear();
      this.deskPulses.clear();
      if (msg.truth) {
        for (const [id, p] of Object.entries(msg.truth.positions)) this.setDot(id, p, true);
        this.truthSummary = msg.truth.summary;
      } else {
        this.truthSummary = null;
      }
    } else {
      const t = this.now();
      for (const id of Object.keys(msg.desks)) this.deskPulses.set(id, t);
      Object.assign(this.desks, msg.desks);
      Object.assign(this.rooms, msg.rooms);
      Object.assign(this.zones, msg.zones);
      if (msg.point) this.addPoint(msg.point);
      if (msg.feed.length) this.feed = [...[...msg.feed].reverse(), ...this.feed].slice(0, FEED_CAP);
      if (msg.truth) {
        for (const [id, p] of Object.entries(msg.truth.positions)) this.setDot(id, p, false);
        this.truthSummary = msg.truth.summary;
      }
    }
    this.dirty = true;
    this.notify();
  }

  private addPoint(point: SeriesPoint): void {
    const last = this.series[this.series.length - 1];
    if (last && point.m < last.m) {
      this.series = [point]; // a new simulated day started
    } else if (!last || last.m !== point.m) {
      this.series = [...this.series, point];
    }
  }

  private setDot(id: string, p: TruthPosition | null, instant: boolean): void {
    if (!p) {
      this.dots.delete(id);
      return;
    }
    const [x, y, floor, dept, state] = p;
    const cur = this.dots.get(id);
    if (!cur || instant || cur.floor !== floor) {
      this.dots.set(id, { x, y, fromX: x, fromY: y, toX: x, toY: y, t0: this.now(), floor, dept, state });
      return;
    }
    Object.assign(cur, { fromX: cur.x, fromY: cur.y, toX: x, toY: y, t0: this.now(), state });
  }

  // ------------------------------------------------------------------ subscriptions
  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getRevision = (): number => this.revision;

  /** Throttled: panels refresh at most every PANEL_REFRESH_MS. */
  private notify(): void {
    const elapsed = this.now() - this.lastNotify;
    if (elapsed >= PANEL_REFRESH_MS) {
      this.flush();
    } else if (!this.notifyTimer) {
      this.notifyTimer = setTimeout(() => this.flush(), PANEL_REFRESH_MS - elapsed);
    }
  }

  flush(): void {
    if (this.notifyTimer) clearTimeout(this.notifyTimer);
    this.notifyTimer = null;
    this.lastNotify = this.now();
    this.revision += 1;
    for (const listener of this.listeners) listener();
  }
}
