import { useDeferredValue, useState } from "react";

import { useDepartments, useEmployeeFacets, useEmployees, useFloors, useTeams } from "@/api/hooks";
import type { Employee, EmployeeQuery } from "@/api/types";
import { Badge, Card, type Column, DataTable, Loading, Pagination, SearchInput, Select } from "@/components/ui";
import { humanize } from "@/lib/format";

const PAGE_SIZE = 25;

type Filters = Omit<EmployeeQuery, "page" | "page_size" | "search">;

const COLUMNS: Column<Employee>[] = [
  {
    header: "Employee",
    cell: (e) => (
      <div>
        <div className="font-medium text-slate-900">{e.employee_name}</div>
        <div className="text-xs text-slate-500">
          <b className="text-slate-700">{e.code}</b> · {e.employee_id} · {e.email}
        </div>
      </div>
    ),
  },
  { header: "Role", cell: (e) => e.job_role },
  {
    header: "Team",
    cell: (e) => (
      <div>
        <div>{e.team_name}</div>
        <div className="text-xs text-slate-500">{e.department_name}</div>
      </div>
    ),
  },
  { header: "Home floor", cell: (e) => e.home_floor_name },
  { header: "Work mode", cell: (e) => <Badge tone={e.work_mode === "OFFICE" ? "emerald" : e.work_mode === "HYBRID" ? "blue" : "slate"}>{humanize(e.work_mode)}</Badge> },
  { header: "Profile", cell: (e) => humanize(e.behavior_profile) },
  { header: "Assigned desk", cell: (e) => e.assigned_workspace_id ?? "—", className: "text-xs" },
];

export function EmployeesPage() {
  const [search, setSearch] = useState("");
  const [filters, setFilters] = useState<Filters>({});
  const [page, setPage] = useState(1);
  const deferredSearch = useDeferredValue(search);

  const employees = useEmployees({ ...filters, search: deferredSearch, page, page_size: PAGE_SIZE });
  const departments = useDepartments();
  const teams = useTeams();
  const floors = useFloors();
  const facets = useEmployeeFacets();

  const setFilter = (key: keyof Filters) => (value: string) => {
    setFilters((f) => ({ ...f, [key]: value || undefined }));
    setPage(1);
  };
  const facetOptions = (values: { value: string; count: number }[] | undefined) =>
    (values ?? []).map((v) => ({ value: v.value, label: `${humanize(v.value)} (${v.count})` }));

  return (
    <Card>
      <div className="flex flex-wrap items-end gap-3 border-b border-slate-200 p-3">
        <SearchInput
          value={search}
          onChange={(v) => {
            setSearch(v);
            setPage(1);
          }}
          placeholder="Name, E-code, ID, email or role"
        />
        <Select
          label="Department"
          value={filters.department_id ?? ""}
          onChange={setFilter("department_id")}
          options={(departments.data ?? []).map((d) => ({ value: d.department_id, label: d.name }))}
        />
        <Select
          label="Team"
          value={filters.team_id ?? ""}
          onChange={setFilter("team_id")}
          options={(teams.data ?? [])
            .filter((t) => !filters.department_id || t.department_id === filters.department_id)
            .map((t) => ({ value: t.team_id, label: t.name }))}
        />
        <Select
          label="Home floor"
          value={filters.floor_id ?? ""}
          onChange={setFilter("floor_id")}
          options={(floors.data ?? []).map((f) => ({ value: f.floor_id, label: f.name }))}
        />
        <Select label="Work mode" value={filters.work_mode ?? ""} onChange={setFilter("work_mode")} options={facetOptions(facets.data?.work_mode)} />
        <Select
          label="Profile"
          value={filters.behavior_profile ?? ""}
          onChange={setFilter("behavior_profile")}
          options={facetOptions(facets.data?.behavior_profile)}
        />
      </div>
      {employees.data ? (
        <>
          <DataTable columns={COLUMNS} rows={employees.data.items} rowKey={(e) => e.employee_id} empty="No employees match" />
          <Pagination page={page} pageSize={PAGE_SIZE} total={employees.data.total} onPage={setPage} />
        </>
      ) : (
        <Loading />
      )}
    </Card>
  );
}
