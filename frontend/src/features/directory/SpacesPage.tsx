import { useSearchParams } from "react-router";

import { useFloors, useRooms, useZones } from "@/api/hooks";
import type { Room, Zone } from "@/api/types";
import { Badge, Card, type Column, DataTable, Loading, StatCard } from "@/components/ui";
import { humanize, number } from "@/lib/format";
import { cn } from "@/lib/utils";

const ZONE_COLUMNS: Column<Zone>[] = [
  { header: "Zone", cell: (z) => <span className="font-medium text-slate-900">{z.name}</span> },
  { header: "ID", cell: (z) => z.zone_id, className: "text-xs" },
  { header: "Type", cell: (z) => humanize(z.zone_type) },
  { header: "Workspaces", cell: (z) => z.workspaces || "—", className: "text-right" },
  { header: "Max occupancy", cell: (z) => z.max_occupancy || "—", className: "text-right" },
  { header: "Area (m²)", cell: (z) => number(z.area_sqm), className: "text-right" },
];

const ROOM_COLUMNS: Column<Room>[] = [
  { header: "Room", cell: (r) => <span className="font-medium text-slate-900">{r.name}</span> },
  { header: "ID", cell: (r) => r.room_id, className: "text-xs" },
  {
    header: "Type",
    cell: (r) =>
      r.room_type === "COMMON_AREA" ? <Badge tone="amber">{humanize(r.area_subtype)}</Badge> : humanize(r.room_type),
  },
  { header: "Capacity", cell: (r) => r.capacity, className: "text-right" },
  { header: "Bookable", cell: (r) => (r.is_bookable ? "Yes" : "No") },
  { header: "Zone", cell: (r) => r.zone_name ?? r.zone_id },
];

export function SpacesPage() {
  const floors = useFloors();
  const [params, setParams] = useSearchParams();
  const floorId = params.get("floor") ?? floors.data?.[0]?.floor_id;
  const zones = useZones(floorId);
  const rooms = useRooms(floorId);

  if (!floors.data) return <Loading />;
  const floor = floors.data.find((f) => f.floor_id === floorId);

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        {floors.data.map((f) => (
          <button
            key={f.floor_id}
            type="button"
            onClick={() => setParams({ floor: f.floor_id })}
            className={cn(
              "rounded-md border px-3 py-1.5 text-sm",
              f.floor_id === floorId ? "border-brand-500 bg-brand-50 text-brand-700" : "border-slate-300 bg-white text-slate-600 hover:bg-slate-50",
            )}
          >
            {f.name}
          </button>
        ))}
      </div>

      {floor && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          <StatCard label="Desks" value={floor.desks} hint={floor.cabins ? `+ ${floor.cabins} cabins` : humanize(floor.desk_policy)} />
          <StatCard label="Meeting rooms" value={floor.rooms} hint={`${floor.room_seats} seats`} />
          <StatCard label="Common areas" value={floor.common_areas} hint={`${floor.common_area_capacity} capacity`} />
          <StatCard label="Sensors" value={floor.sensors} hint={`${floor.zones} zones`} />
          <StatCard label="Max occupancy" value={floor.max_occupancy} hint={humanize(floor.desk_policy)} />
        </div>
      )}

      <Card>
        <h2 className="border-b border-slate-200 px-3 py-2 text-sm font-semibold">Zones</h2>
        {zones.data ? <DataTable columns={ZONE_COLUMNS} rows={zones.data} rowKey={(z) => z.zone_id} /> : <Loading />}
      </Card>
      <Card>
        <h2 className="border-b border-slate-200 px-3 py-2 text-sm font-semibold">Rooms and common areas</h2>
        {rooms.data ? <DataTable columns={ROOM_COLUMNS} rows={rooms.data} rowKey={(r) => r.room_id} /> : <Loading />}
      </Card>
    </div>
  );
}
