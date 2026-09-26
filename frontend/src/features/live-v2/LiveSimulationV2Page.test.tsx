import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { routes } from "@/app/routes";

import { LiveStoreV2 } from "./store";
import type { ActionItem, FrameV2, SnapshotV2, V2Layout } from "./types";

const LAYOUT: V2Layout = {
  building: { building_id: "BLD01", name: "Building A" },
  departments: ["Engineering"],
  floors: [
    {
      floor_id: "BLD01_F02",
      floor_number: 2,
      name: "Floor 2",
      desk_policy: "HOT_DESK",
      width: 60,
      height: 30,
      glazing: ["N"],
      cores: [],
      zones: [
        { zone_id: "Z1", code: "A", name: "North open", zone_type: "OPEN_WORK", x: 0, y: 0, w: 30, h: 15, facade: "N", is_restricted: false, capacity: 20 },
      ],
      desks: [{ workspace_id: "BLD01_F02_D001", zone_id: "Z1", x: 2, y: 2, w: 1.6, h: 0.8, facing: "N" }],
      rooms: [],
      readers: [],
    },
  ],
};

const ACTION: ActionItem = {
  t: "10:40",
  area: "Z1",
  area_name: "North open",
  floor: "BLD01_F02",
  rule: "PRECOOL",
  action: "PRECOOL",
  tag: "HVAC",
  reason: "Pre-cool: 25.9 °C and rising",
};

const SNAPSHOT = {
  type: "snapshot",
  run_id: "r1",
  status: "STOPPED",
  speed: 60,
  allowed_speeds: [1, 60, 300],
  sim_time: "2026-09-28T10:42:00+05:30",
  events_generated: 0,
  version: 1,
  desks: { BLD01_F02_D001: [1, 0] },
  rooms: {},
  zones: {},
  kpis: null,
  events_total: 0,
  automation: [],
  people: {},
  activity: [],
  series: [],
  areas: { Z1: [25.9, 0.6, 820, "PRECOOL", 100, 23.5, false] },
  esg: { kwh: 400, baseline_kwh: 448, saved_kwh: 48, saved_pct: 10.7, co2e_kg: 34, cost_inr: 384, comfort_pct: 96.1 },
  esg_floors: {},
  floor_kpis: {
    BLD01_F02: { desk_util_pct: 64, occupied_desks: 87, held_desks: 9, rooms_in_use: 3, rooms: 12, est_people: 131, warm_spots: 2 },
  },
  chips: {},
  booked: {},
  warm_areas: ["Z1"],
  actions: [ACTION],
} as unknown as SnapshotV2;

class FakeSocket {
  static instances: FakeSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  constructor(public url: string) {
    FakeSocket.instances.push(this);
  }
  close() {}
}

afterEach(() => {
  vi.unstubAllGlobals();
  FakeSocket.instances = [];
});

describe("LiveStoreV2", () => {
  it("merges v2 extras and keeps actions newest first", () => {
    const store = new LiveStoreV2();
    store.apply(SNAPSHOT);
    expect(store.floorKpis.BLD01_F02?.est_people).toBe(131);
    expect(store.warmAreas.has("Z1")).toBe(true);
    const later = { ...ACTION, t: "10:45", reason: "Eco: area empty" };
    store.apply({ ...SNAPSHOT, type: "frame", feed: [], areas: { Z1: [24.1, -1.8, 600, "ECO", 30, 26, false] }, warm_areas: [], actions: [later] } as unknown as FrameV2);
    expect(store.areas.Z1?.[3]).toBe("ECO");
    expect(store.warmAreas.size).toBe(0);
    expect(store.actions.map((a) => a.t)).toEqual(["10:45", "10:40"]);
  });
});

describe("LiveSimulationV2Page", () => {
  it("renders KPIs, sustainability and automation from the v2 socket", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url.startsWith("/api/v2/layout")) return new Response(JSON.stringify(LAYOUT));
      if (url.startsWith("/api/v2/simulation/commands")) return new Response(JSON.stringify({ status: "RUNNING" }));
      return new Response(JSON.stringify({ status: "ok", checked_at: "", components: {} }));
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("WebSocket", FakeSocket);

    const router = createMemoryRouter(routes, { initialEntries: ["/live-v2"] });
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );

    await screen.findByRole("heading", { name: "Floor 2" });
    const socket = FakeSocket.instances.at(-1)!;
    expect(socket.url).toContain("/ws/live-v2");
    expect(socket.url).toContain("truth=false");
    act(() => {
      socket.onopen?.();
      socket.onmessage?.({ data: JSON.stringify(SNAPSHOT) });
    });
    expect(await screen.findByText("Mon 28 Sep · 10:42")).toBeInTheDocument();
    expect(screen.getByText("131")).toBeInTheDocument();
    expect(screen.getByText("10.7%")).toBeInTheDocument();
    expect(screen.getByText("Pre-cool: 25.9 °C and rising")).toBeInTheDocument();
    expect(screen.queryByText("True headcount*")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Start" }));
    expect(fetchMock).toHaveBeenCalledWith("/api/v2/simulation/commands", expect.objectContaining({ method: "POST" }));

    fireEvent.click(screen.getByRole("button", { name: "Simulation" }));
    expect(FakeSocket.instances.at(-1)!.url).toContain("truth=true");
    expect(screen.getByText("True headcount*")).toBeInTheDocument();
  });
});
