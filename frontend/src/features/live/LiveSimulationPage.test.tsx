import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { routes } from "@/app/routes";

import type { LiveLayout, SnapshotMessage } from "./types";

const LAYOUT: LiveLayout = {
  building: { building_id: "BLD01", name: "Building A", max_occupancy: 1000 },
  floors: [{ floor_id: "BLD01_F01", floor_number: 1, name: "Floor 1", desk_policy: "HOT_DESK", width: 120, height: 60, desks: 1 }],
  zones: [],
  workspaces: [{ workspace_id: "D1", floor_id: "BLD01_F01", zone_id: "Z", workspace_type: "DESK", x: 5, y: 5, has_sensor: true }],
  rooms: [],
  access_points: [],
  departments: ["Engineering"],
};

const SNAPSHOT: SnapshotMessage = {
  type: "snapshot",
  run_id: "r1",
  status: "STOPPED",
  speed: 60,
  allowed_speeds: [1, 60, 300],
  sim_time: "2026-09-28T09:15:00+05:30",
  events_generated: 0,
  version: 1,
  desks: { D1: [1, 0] },
  rooms: {},
  zones: {},
  kpis: {
    employees_inside: 42,
    occupied_desks: 1,
    held_desks: 0,
    available_desks: 0,
    total_desks: 1,
    desk_util_pct: 100,
    rooms_in_use: 0,
    meeting_rooms: 0,
    room_util_pct: 0,
    room_occupants: 0,
    building_util_pct: 4.2,
    peak_today: 42,
    peak_time: "09:10",
    floors: [
      { floor_id: "BLD01_F01", name: "Floor 1", occupied_desks: 1, held_desks: 0, room_occupants: 0, est_headcount: 1, desks: 1, desk_util_pct: 100 },
    ],
    hvac_eco_zones: 0,
  },
  events_total: 0,
  automation: [],
  series: [],
};

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

describe("LiveSimulationPage", () => {
  it("renders the snapshot and sends commands", async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.startsWith("/api/v1/live/layout")) return new Response(JSON.stringify(LAYOUT));
      if (url.startsWith("/api/v1/simulation/commands")) return new Response(JSON.stringify({ ...SNAPSHOT, status: "RUNNING", body: init?.body }));
      return new Response(JSON.stringify({ status: "ok", checked_at: "", components: {} }));
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("WebSocket", FakeSocket);

    const router = createMemoryRouter(routes, { initialEntries: ["/live"] });
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );

    await screen.findByText(/Floor 1 — Hot desk/);
    const socket = FakeSocket.instances.at(-1)!;
    expect(socket.url).toContain("truth=false");
    act(() => {
      socket.onopen?.();
      socket.onmessage?.({ data: JSON.stringify(SNAPSHOT) });
    });
    expect(await screen.findByText("42")).toBeInTheDocument();
    expect(screen.getByText("2026-09-28 09:15:00")).toBeInTheDocument();
    expect(screen.queryByText(/Truth inside/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Start/ }));
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/simulation/commands", expect.objectContaining({ method: "POST" }));

    fireEvent.click(screen.getByRole("button", { name: "Simulation (truth)" }));
    expect(FakeSocket.instances.at(-1)!.url).toContain("truth=true");
  });
});
