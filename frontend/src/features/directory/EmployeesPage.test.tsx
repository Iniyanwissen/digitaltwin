import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { routes } from "@/app/routes";
import type { Employee, Page } from "@/api/types";

const EMPLOYEE: Employee = {
  employee_id: "EMP000001",
  code: "E1",
  employee_name: "Priya Nair",
  email: "priya.nair@northwind.example",
  job_role: "Engineering Manager",
  team_id: "TEAM_001",
  team_name: "Atlas",
  department_id: "DEP_ENG",
  department_name: "Engineering",
  home_floor_id: "BLD01_F02",
  home_floor_name: "Floor 2",
  preferred_zone_id: "BLD01_F02_ZA",
  manager_id: null,
  employment_type: "FULL_TIME",
  work_mode: "HYBRID",
  behavior_profile: "EARLY_BIRD",
  hire_date: "2020-01-01",
  assigned_workspace_id: null,
};

const RESPONSES: Record<string, unknown> = {
  "/api/v1/employees": { items: [EMPLOYEE], total: 1000, page: 1, page_size: 25 } satisfies Page<Employee>,
  "/api/v1/employees/facets": { work_mode: [{ value: "HYBRID", count: 600 }], behavior_profile: [], employment_type: [] },
  "/api/v1/departments": [],
  "/api/v1/teams": [],
  "/api/v1/floors": [],
  "/health": { status: "ok", checked_at: "", components: {} },
};

afterEach(() => vi.unstubAllGlobals());

describe("EmployeesPage", () => {
  it("renders employees from the API with filters and paging", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      const path = url.split("?")[0] ?? url;
      return new Response(JSON.stringify(RESPONSES[path] ?? {}), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    const router = createMemoryRouter(routes, { initialEntries: ["/directory/employees"] });
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("Priya Nair")).toBeInTheDocument();
    expect(screen.getByText("1–25 of 1,000")).toBeInTheDocument();
    expect(await screen.findByRole("option", { name: "Hybrid (600)" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("page_size=25"), expect.anything());
  });
});
