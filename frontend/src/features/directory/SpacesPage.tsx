import { useSearchParams } from "react-router";

import { useAccessPoints, useFloors, useRooms, useZones } from "@/api/hooks";
import type { AccessPoint, Room, Zone } from "@/api/types";
import { Badge, Card, type Column, DataTable, Loading, StatCard } from "@/components/ui";
import { humanize, number } from "@/lib/format";
import { cn } from "@/lib/utils";

const ZONE_COLUMNS: Column<Zone>[] = [
  {
    header: "Zone",
    cell: (z) => (
      <span className="flex items-center gap-2">
        <span className="font-medium text-slate-900">{z.name}</span>
        {z.is_restricted && <Badge tone="red">Restricted</Badge>}
      </span>
    ),
  },
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
  { header: "Door reader", cell: (r) => (r.has_badge_reader ? "Yes" : "—") },
  { header: "Check-in panel", cell: (r) => (r.has_panel ? "Yes" : "—") },
  { header: "Zone", cell: (r) => r.zone_name ?? r.zone_id },
];

const READER_TONE: Record<string, "slate" | "blue" | "amber" | "red"> = {
  BUILDING_ENTRANCE: "slate",
  FLOOR_LOBBY: "blue",
  ROOM_DOOR: "amber",
  SECURE_ZONE: "red",
};

const READER_COLUMNS: Column<AccessPoint>[] = [
  { header: "Reader", cell: (a) => <span className="font-medium text-slate-900">{a.name}</span> },
  { header: "ID", cell: (a) => a.access_point_id, className: "text-xs" },
  { header: "Type", cell: (a) => <Badge tone={READER_TONE[a.reader_type] ?? "slate"}>{humanize(a.reader_type)}</Badge> },
  { header: "Guards", cell: (a) => a.target_id, className: "text-xs" },
  { header: "Direction", cell: (a) => humanize(a.direction) },
];

export function SpacesPage() {
  const floors = useFloors();
  const [params, setParams] = useSearchParams();
  const floorId = params.get("floor") ?? floors.data?.[0]?.floor_id;
  const zones = useZones(floorId);
  const rooms = useRooms(floorId);
  const readers = useAccessPoints(floorId);

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
          <StatCard label="Sensors" value={floor.sensors} hint={`${floor.readers} badge readers · ${floor.zones} zones`} />
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
      <Card>
        <h2 className="border-b border-slate-200 px-3 py-2 text-sm font-semibold">Badge readers</h2>
        {readers.data ? (
          <DataTable columns={READER_COLUMNS} rows={readers.data} rowKey={(a) => a.access_point_id} empty="No readers on this floor" />
        ) : (
          <Loading />
        )}
      </Card>
    </div>
  );
}
