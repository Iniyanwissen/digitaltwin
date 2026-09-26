import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Health } from "@/api/types";

import { routes } from "./routes";

const HEALTHY: Health = {
  status: "ok",
  checked_at: "2026-09-25T10:00:00Z",
  components: {
    database: { status: "ok", detail: "sqlite reachable", info: {} },
    simulation_engine: { status: "ok", detail: "running", info: { status: "STOPPED" } },
  },
};

function renderAt(path: string, fetchImpl: typeof fetch) {
  vi.stubGlobal("fetch", fetchImpl);
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

const okFetch = vi.fn(async () => new Response(JSON.stringify(HEALTHY), { status: 200 }));

afterEach(() => vi.unstubAllGlobals());

describe("AppShell", () => {
  it("shows a green health indicator when the API is healthy", async () => {
    renderAt("/", okFetch as unknown as typeof fetch);
    expect(await screen.findByText("Healthy")).toBeInTheDocument();
    expect(screen.getByTestId("health-dot")).toHaveClass("bg-emerald-500");
    expect(screen.getByText(/Simulation: stopped/i)).toBeInTheDocument();
  });

  it("shows API unreachable when the request fails", async () => {
    renderAt("/", vi.fn(async () => Promise.reject(new TypeError("offline"))) as unknown as typeof fetch);
    expect(await screen.findByText("API unreachable")).toBeInTheDocument();
  });

  it("redirects a section to its first tab and shows tabs", async () => {
    renderAt("/analytics", okFetch as unknown as typeof fetch);
    expect(await screen.findByRole("link", { name: "Real Estate" })).toBeInTheDocument();
    expect(screen.getByText("Attendance trends")).toBeInTheDocument();
  });
});
