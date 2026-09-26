import { useEffect, useRef } from "react";

import { cn } from "@/lib/utils";

import type { LiveStore } from "./store";
import { TWIN, utilisationFill } from "./theme";
import type { FloorKpi, LiveLayout } from "./types";
import { useLiveRevision } from "./useLive";

interface Band {
  id: string;
  y0: number;
  y1: number;
}

function floorsFor(store: LiveStore, layout: LiveLayout): Pick<FloorKpi, "floor_id" | "name" | "desk_util_pct">[] {
  return store.kpis?.floors ?? layout.floors.map((f) => ({ floor_id: f.floor_id, name: f.name, desk_util_pct: 0 }));
}

/** Isometric floor stack coloured by desk utilisation (sensor), plus clickable floor rows. */
export function BuildingPanel({
  store,
  layout,
  floorId,
  onSelect,
}: {
  store: LiveStore;
  layout: LiveLayout;
  floorId: string;
  onSelect: (id: string) => void;
}) {
  const revision = useLiveRevision(store);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const bands = useRef<Band[]>([]);
  const floors = floorsFor(store, layout);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const list = floorsFor(store, layout);
    const n = list.length;
    const w = canvas.width * 0.62;
    const dx = canvas.width * 0.22;
    const dy = Math.min(20 * dpr, canvas.height / (n + 3));
    const gap = Math.min(28 * dpr, (canvas.height - dy * 2) / Math.max(1, n));
    bands.current = [];
    list.forEach((f, i) => {
      const y = canvas.height - dy - 8 * dpr - i * gap;
      const x0 = canvas.width * 0.06;
      ctx.beginPath();
      ctx.moveTo(x0, y);
      ctx.lineTo(x0 + w, y);
      ctx.lineTo(x0 + w + dx, y - dy);
      ctx.lineTo(x0 + dx, y - dy);
      ctx.closePath();
      ctx.fillStyle = utilisationFill(f.desk_util_pct);
      ctx.fill();
      const selected = f.floor_id === floorId;
      ctx.strokeStyle = selected ? TWIN.selected : TWIN.isoEdge;
      ctx.lineWidth = (selected ? 2 : 1) * dpr;
      ctx.stroke();
      ctx.fillStyle = TWIN.isoText;
      ctx.font = `${11 * dpr}px system-ui`;
      ctx.fillText(`${f.name}  ${f.desk_util_pct}%`, x0 + dx * 0.5 + 6 * dpr, y - dy / 2 + 4 * dpr);
      bands.current.push({ id: f.floor_id, y0: y - dy, y1: y });
    });
  }, [revision, floorId, store, layout]);

  const onClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const y = (e.clientY - rect.top) * (window.devicePixelRatio || 1);
    const band = bands.current.find((b) => y >= b.y0 - 6 && y <= b.y1 + 6);
    if (band) onSelect(band.id);
  };

  return (
    <section className="flex shrink-0 flex-col rounded-xl border border-twin-line bg-twin-panel p-3">
      <h2 className="mb-1 text-xs font-semibold tracking-wider text-twin-muted uppercase" title="Floors coloured by desk utilisation (sensor). Click a floor.">
        Building
      </h2>
      <canvas ref={canvasRef} onClick={onClick} className="h-36 w-full cursor-pointer" aria-label="Isometric building" />
      <div className="mt-2 space-y-1">
        {floors.map((f) => (
          <button
            key={f.floor_id}
            type="button"
            onClick={() => onSelect(f.floor_id)}
            className={cn(
              "grid w-full grid-cols-[64px_1fr_48px] items-center gap-2 rounded px-1 py-1 text-left text-sm hover:bg-twin-line/60",
              f.floor_id === floorId && "bg-twin-line/60",
            )}
          >
            <span>{f.name}</span>
            <span className="h-2 overflow-hidden rounded bg-twin-line">
              <span className="block h-full bg-twin-occupied" style={{ width: `${Math.min(100, f.desk_util_pct)}%` }} />
            </span>
            <span className="text-right tabular-nums">{f.desk_util_pct}%</span>
          </button>
        ))}
      </div>
    </section>
  );
}
