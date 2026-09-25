import { Link } from "react-router";

import { useBuildings } from "@/api/hooks";
import type { FloorSummary } from "@/api/types";
import { Badge, Card, Loading, StatCard } from "@/components/ui";
import { humanize, number } from "@/lib/format";
import { cn } from "@/lib/utils";

function FloorRow({ floor }: { floor: FloorSummary }) {
  const load = floor.employees_per_workspace;
  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-center gap-6">
        <div className="w-28">
          <div className="text-lg font-semibold">{floor.name}</div>
          <Badge tone={floor.desk_policy === "ASSIGNED" ? "amber" : "blue"}>{humanize(floor.desk_policy)}</Badge>
        </div>
        <Metric label="Workspaces" value={floor.workspaces} hint={floor.cabins ? `${floor.cabins} cabins` : undefined} />
        <Metric label="Meeting rooms" value={floor.rooms} hint={`${floor.room_seats} seats`} />
        <Metric label="Common areas" value={floor.common_areas} hint={floor.common_areas ? `${floor.common_area_capacity} capacity` : undefined} />
        <Metric label="Max occupancy" value={floor.max_occupancy} />
        <div className="min-w-56 flex-1">
          <div className="flex justify-between text-xs text-slate-500">
            <span>
              {floor.home_employees} employees · {floor.home_teams} teams
            </span>
            <span>{load.toFixed(2)} per workspace</span>
          </div>
          <div className="mt-1 h-2 overflow-hidden rounded-full bg-slate-100">
            <div
              className={cn("h-full rounded-full", load > 1.3 ? "bg-amber-500" : "bg-brand-500")}
              style={{ width: `${Math.min(100, (load / 1.5) * 100)}%` }}
            />
          </div>
        </div>
        <Link to={`/directory/spaces?floor=${floor.floor_id}`} className="text-sm text-brand-600 hover:underline">
          Spaces →
        </Link>
      </div>
    </Card>
  );
}

function Metric({ label, value, hint }: { label: string; value: number; hint?: string }) {
  return (
    <div className="w-28">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="text-lg font-semibold">{number(value)}</div>
      {hint && <div className="text-xs text-slate-500">{hint}</div>}
    </div>
  );
}

export function BuildingPage() {
  const buildings = useBuildings();
  if (!buildings.data) return <Loading />;

  return (
    <div className="space-y-6">
      {buildings.data.map((b) => {
        const topFirst = [...b.floors].sort((x, y) => y.floor_number - x.floor_number);
        return (
          <section key={b.building_id} className="space-y-3">
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <StatCard label={b.name} value={`${b.floors.length} floors`} hint={b.timezone} />
              <StatCard label="Max occupancy" value={number(b.max_occupancy)} hint="safety limit" />
              <StatCard label="Gross area" value={`${number(b.gross_area_sqm)} m²`} />
              <StatCard label="Entrances" value={b.access_points.length} hint={b.access_points.map((a) => a.name).join(", ")} />
            </div>
            <p className="text-sm text-slate-500">Static capacity per floor. Live occupancy arrives in Phase 6.</p>
            <div className="space-y-2">
              {topFirst.map((f) => (
                <FloorRow key={f.floor_id} floor={f} />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
