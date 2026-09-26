import { useEffect, useMemo, useRef, useState } from "react";

import { humanize } from "@/lib/format";

import { liveApi } from "./api";
import { buildScene, drawFloor, pick, type Overlay, type Pick, type View } from "./floorRenderer";
import type { LiveStore } from "./store";
import { HVAC_LEGEND, OCCUPANCY_LEGEND, TEMP_LEGEND } from "./theme";
import type { DeskDetail, LiveLayout, RoomDetail } from "./types";

type Detail = { kind: "desk"; data: DeskDetail } | { kind: "room"; data: RoomDetail } | null;

export function FloorPanel({
  store,
  layout,
  floorId,
  view,
  overlay,
  deptColor,
}: {
  store: LiveStore;
  layout: LiveLayout;
  floorId: string;
  view: View;
  overlay: Overlay;
  deptColor: Record<string, string>;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const scene = useMemo(() => buildScene(layout, floorId), [layout, floorId]);
  const settings = useRef({ scene, view, overlay, deptColor });
  const [selected, setSelected] = useState<Pick>(null);
  const [detail, setDetail] = useState<Detail>(null);

  useEffect(() => {
    settings.current = { scene, view, overlay, deptColor };
    store.dirty = true;
  }, [scene, view, overlay, deptColor, store]);

  // Render loop: redraw only when the store changed or dots are still moving.
  useEffect(() => {
    let raf = 0;
    const loop = (now: number) => {
      const canvas = canvasRef.current;
      if (canvas && store.dirty) {
        const s = settings.current;
        store.dirty = drawFloor(canvas, s.scene, store, s.view, s.overlay, s.deptColor, now);
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    const onResize = () => {
      store.dirty = true;
    };
    window.addEventListener("resize", onResize);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", onResize);
    };
  }, [store]);

  // Details come from the API: desk identity only from workstation login (server-enforced).
  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    const load = async () => {
      const d: Detail =
        selected.kind === "desk"
          ? { kind: "desk", data: await liveApi.desk(selected.id) }
          : { kind: "room", data: await liveApi.room(selected.id) };
      if (!cancelled) setDetail(d);
    };
    void load();
    const timer = setInterval(() => void load(), 2000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [selected]);

  const onClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const hit = pick(e.currentTarget, scene, e.clientX - rect.left, e.clientY - rect.top);
    setSelected(hit);
    if (!hit) setDetail(null);
  };

  const floor = layout.floors.find((f) => f.floor_id === floorId);
  const legend = overlay === "temperature" ? TEMP_LEGEND : overlay === "hvac" ? HVAC_LEGEND : OCCUPANCY_LEGEND;

  return (
    <section className="relative flex min-h-0 flex-col rounded-xl border border-twin-line bg-twin-panel p-3">
      <h2 className="mb-2 text-xs font-semibold tracking-wider text-twin-muted uppercase">
        {floor ? `${floor.name} — ${humanize(floor.desk_policy)} · ${floor.desks} desks` : "Floor"}
      </h2>
      <div className="relative min-h-0 flex-1">
        <canvas ref={canvasRef} onClick={onClick} className="block h-full w-full cursor-crosshair" aria-label="Floor plan" />
        {detail && <DetailCard detail={detail} onClose={() => (setSelected(null), setDetail(null))} />}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-twin-muted">
        {legend.map(([color, label]) => (
          <span key={label} className="flex items-center gap-1">
            <i className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: color }} />
            {label}
          </span>
        ))}
        {view === "simulation" && (
          <>
            <span className="text-twin-text">· Dots = simulation truth by department:</span>
            {Object.entries(deptColor).map(([dept, color]) => (
              <span key={dept} className="flex items-center gap-1">
                <i className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: color }} />
                {dept}
              </span>
            ))}
          </>
        )}
      </div>
    </section>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-twin-muted">{label}</span>
      <span className="text-right">{value}</span>
    </div>
  );
}

function DetailCard({ detail, onClose }: { detail: NonNullable<Detail>; onClose: () => void }) {
  return (
    <div className="absolute top-2 right-2 w-72 space-y-1 rounded-lg border border-twin-line bg-twin-bg/95 p-3 text-xs shadow-xl">
      <div className="flex items-start justify-between">
        <b className="text-sm">{detail.kind === "desk" ? detail.data.workspace_id : detail.data.name}</b>
        <button type="button" onClick={onClose} className="text-twin-muted hover:text-twin-text" aria-label="Close">
          ✕
        </button>
      </div>
      {detail.kind === "desk" ? (
        <>
          <Row label="Zone" value={detail.data.zone_id} />
          <Row label="Device" value={humanize(detail.data.device_type)} />
          <Row label="Sensor" value={detail.data.has_sensor ? detail.data.sensor_status : "no sensor"} />
          <Row label="Last sensor change" value={detail.data.last_sensor_change ?? "–"} />
          <Row label="Logged in (workstation)" value={detail.data.logged_in_employee ?? "–"} />
          <p className="pt-1 text-twin-muted">Identity comes only from the workstation login, never from the sensor.</p>
        </>
      ) : (
        <>
          <Row label="Type" value={humanize(detail.data.area_subtype ?? detail.data.room_type)} />
          <Row label="Count (sensor)" value={`${detail.data.sensor_count} / ${detail.data.capacity}`} />
          <Row label="Door reader" value={detail.data.has_badge_reader ? "yes (identified)" : "no"} />
          <Row label="Check-in panel" value={detail.data.has_panel ? "yes" : "no"} />
          <Row
            label="Booking now"
            value={
              detail.data.current_booking
                ? `${detail.data.current_booking.start}–${detail.data.current_booking.end} · ${detail.data.current_booking.expected_attendees} people${detail.data.current_booking.checked_in ? " · checked in" : ""}`
                : "–"
            }
          />
        </>
      )}
    </div>
  );
}
