import { useState } from "react";

import { useDepartments, useFloors, useTeams } from "@/api/hooks";
import type { Team } from "@/api/types";
import { Badge, Card, type Column, DataTable, Loading, SearchInput, Select, StatCard } from "@/components/ui";
import { percent, weekdays } from "@/lib/format";

const COLUMNS: Column<Team>[] = [
  {
    header: "Team",
    cell: (t) => (
      <div>
        <div className="font-medium text-slate-900">{t.name}</div>
        <div className="text-xs text-slate-500">{t.team_id}</div>
      </div>
    ),
  },
  { header: "Department", cell: (t) => t.department_name },
  { header: "Members", cell: (t) => t.members, className: "text-right" },
  { header: "Home floor", cell: (t) => t.home_floor_name },
  { header: "Office days", cell: (t) => weekdays(t.office_days) },
  {
    header: "Seating zones",
    cell: (t) => t.zone_allocations.map((a) => `${a.zone_name} ${percent(a.share)}`).join(" · "),
  },
  {
    header: "Secure access",
    cell: (t) =>
      t.secure_zones.length ? (
        <Badge tone="red">{t.secure_zones.map((z) => z.zone_name).join(", ")}</Badge>
      ) : (
        "—"
      ),
  },
];

export function TeamsPage() {
  const teams = useTeams();
  const departments = useDepartments();
  const floors = useFloors();
  const [search, setSearch] = useState("");
  const [department, setDepartment] = useState("");
  const [floor, setFloor] = useState("");

  if (!teams.data) return <Loading />;
  const needle = search.trim().toLowerCase();
  const rows = teams.data.filter(
    (t) =>
      (!department || t.department_id === department) &&
      (!floor || t.home_floor_id === floor) &&
      (!needle || t.name.toLowerCase().includes(needle)),
  );

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {(departments.data ?? []).slice(0, 4).map((d) => (
          <StatCard key={d.department_id} label={d.name} value={d.employees} hint={`${d.teams} teams`} />
        ))}
      </div>
      <Card>
        <div className="flex flex-wrap items-end gap-3 border-b border-slate-200 p-3">
          <SearchInput value={search} onChange={setSearch} placeholder="Team name" />
          <Select
            label="Department"
            value={department}
            onChange={setDepartment}
            options={(departments.data ?? []).map((d) => ({ value: d.department_id, label: d.name }))}
          />
          <Select
            label="Home floor"
            value={floor}
            onChange={setFloor}
            options={(floors.data ?? []).map((f) => ({ value: f.floor_id, label: f.name }))}
          />
          <span className="ml-auto text-sm text-slate-500">{rows.length} teams</span>
        </div>
        <DataTable columns={COLUMNS} rows={rows} rowKey={(t) => t.team_id} empty="No teams match" />
      </Card>
    </div>
  );
}
