import { describe, expect, it, vi } from "vitest";

import { LiveStore } from "./store";
import type { FrameMessage, Kpis, SnapshotMessage } from "./types";

const KPIS = { employees_inside: 3, floors: [], total_desks: 800 } as unknown as Kpis;
const STATUS = {
  run_id: "r1",
  status: "RUNNING" as const,
  speed: 60,
  allowed_speeds: [1, 60],
  sim_time: "2026-09-28T09:00:00+05:30",
  events_generated: 10,
};

function snapshot(extra: Partial<SnapshotMessage> = {}): SnapshotMessage {
  return {
    type: "snapshot",
    ...STATUS,
    version: 5,
    desks: { D1: [1, 1] },
    rooms: { R1: 2 },
    zones: {},
    kpis: KPIS,
    events_total: 10,
    automation: [],
    people: {},
    activity: [],
    series: [{ m: "09:00", inside: 3, desks: 1, held: 0, rooms: 2 }],
    ...extra,
  };
}

function frame(extra: Partial<FrameMessage> = {}): FrameMessage {
  return {
    type: "frame",
    ...STATUS,
    version: 6,
    desks: {},
    rooms: {},
    zones: {},
    kpis: KPIS,
    events_total: 11,
    automation: [],
    feed: [],
    point: null,
    people: {},
    activity: [],
    ...extra,
  };
}

describe("LiveStore", () => {
  it("merges deltas into the snapshot state", () => {
    const store = new LiveStore(() => 0);
    store.apply(snapshot());
    store.apply(frame({ desks: { D2: [0, 1] }, rooms: { R1: 3 } }));
    expect(store.desks).toEqual({ D1: [1, 1], D2: [0, 1] });
    expect(store.rooms.R1).toBe(3);
    expect(store.eventsTotal).toBe(11);
  });

  it("appends one series point per minute and resets on a new day", () => {
    const store = new LiveStore(() => 0);
    store.apply(snapshot());
    store.apply(frame({ point: { m: "09:00", inside: 4, desks: 1, held: 0, rooms: 2 } }));
    store.apply(frame({ point: { m: "09:01", inside: 5, desks: 1, held: 0, rooms: 2 } }));
    expect(store.series.map((p) => p.m)).toEqual(["09:00", "09:01"]);
    store.apply(frame({ point: { m: "06:00", inside: 0, desks: 0, held: 0, rooms: 0 } }));
    expect(store.series.map((p) => p.m)).toEqual(["06:00"]);
  });

  it("keeps the newest feed lines first and tweens truth dots", () => {
    let now = 0;
    const store = new LiveStore(() => now);
    store.apply(snapshot({ truth: { version: 1, positions: { E1: [1, 1, "F1", "Eng", "AT_DESK"] }, people: {}, activity: [], summary: {} } }));
    store.apply(
      frame({
        feed: [
          { t: "09:00:01", type: "ACCESS_IN", entity: "E2", floor: "F1", detail: "", identity: "IDENTIFIED" },
          { t: "09:00:02", type: "ACCESS_IN", entity: "E3", floor: "F1", detail: "", identity: "IDENTIFIED" },
        ],
        truth: {
          version: 2,
          positions: { E1: [5, 5, "F1", "Eng", "MEETING"], E9: null },
          people: {},
          activity: [],
          summary: { inside: 1 },
        },
      }),
    );
    expect(store.feed.map((f) => f.entity)).toEqual(["E3", "E2"]);
    const dot = store.dots.get("E1")!;
    expect([dot.fromX, dot.toX, dot.state]).toEqual([1, 5, "MEETING"]);
    now = 1000;
    expect(store.truthSummary?.inside).toBe(1);
  });

  it("merges people activity and status, newest first", () => {
    const store = new LiveStore(() => 0);
    store.apply(snapshot());
    const who = { code: "E283", name: "Priya Nair", dept: "Engineering" };
    store.apply(
      frame({
        people: { EMP000283: { ...who, t: "09:00:05", text: "In building · Floor 1", inside: true } },
        activity: [
          { t: "09:00:05", person: "EMP000283", ...who, text: "entered the building", kind: "in" },
          { t: "09:01:10", person: "EMP000283", ...who, text: "logged in at Desk F1-012", kind: "desk" },
        ],
      }),
    );
    expect(store.activity.map((a) => a.text)).toEqual(["logged in at Desk F1-012", "entered the building"]);
    expect(store.people.EMP000283?.text).toBe("In building · Floor 1");
    store.apply(frame({ people: { EMP000283: null } }));
    expect(store.people.EMP000283).toBeUndefined();
  });

  it("throttles panel notifications", () => {
    vi.useFakeTimers();
    let now = 0;
    const store = new LiveStore(() => now);
    const listener = vi.fn();
    store.subscribe(listener);
    store.apply(snapshot());
    now = 10;
    store.apply(frame());
    store.apply(frame());
    expect(listener).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(500);
    expect(listener).toHaveBeenCalledTimes(2);
    vi.useRealTimers();
  });
});
