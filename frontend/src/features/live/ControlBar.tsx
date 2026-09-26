import { cn } from "@/lib/utils";

import { liveApi } from "./api";
import type { Overlay, View } from "./floorRenderer";
import type { LiveStore } from "./store";
import type { Connection } from "./useLive";
import { useLiveRevision } from "./useLive";

const STATUS_STYLE: Record<string, string> = {
  RUNNING: "bg-green-900 text-green-200",
  PAUSED: "bg-yellow-900 text-yellow-200",
  STOPPED: "bg-twin-line text-twin-muted",
};

const button = "rounded-md border border-twin-line bg-twin-panel px-3 py-1 text-sm hover:border-twin-accent disabled:opacity-40";

export function ControlBar({
  store,
  connection,
  view,
  onView,
  overlay,
  onOverlay,
}: {
  store: LiveStore;
  connection: Connection;
  view: View;
  onView: (v: View) => void;
  overlay: Overlay;
  onOverlay: (o: Overlay) => void;
}) {
  useLiveRevision(store);
  const status = store.status;
  const state = status?.status ?? "STOPPED";
  const clock = status ? `${status.sim_time.slice(0, 10)} ${status.sim_time.slice(11, 19)}` : "--";

  return (
    <div className="flex flex-wrap items-center gap-3 border-b border-twin-line px-4 py-2">
      <span className="min-w-44 text-lg font-semibold tabular-nums">{clock}</span>
      <span className={cn("rounded-full px-2 py-0.5 text-xs", STATUS_STYLE[state])}>{state}</span>
      <button
        type="button"
        className={button}
        disabled={state === "RUNNING"}
        onClick={() => void liveApi.command(state === "PAUSED" ? "RESUME" : "START")}
      >
        ▶ {state === "PAUSED" ? "Resume" : "Start"}
      </button>
      <button type="button" className={button} disabled={state !== "RUNNING"} onClick={() => void liveApi.command("PAUSE")}>
        ⏸ Pause
      </button>
      <button type="button" className={button} onClick={() => void liveApi.command("RESET")}>
        ↺ Reset
      </button>
      <label className="flex items-center gap-2 text-xs text-twin-muted">
        Speed
        <select
          className="rounded-md border border-twin-line bg-twin-panel px-2 py-1 text-sm text-twin-text"
          value={status?.speed ?? ""}
          onChange={(e) => void liveApi.command("SET_SPEED", Number(e.target.value))}
        >
          {(status?.allowed_speeds ?? []).map((s) => (
            <option key={s} value={s}>
              {s}×
            </option>
          ))}
        </select>
      </label>
      <span className="flex-1" />
      <span className="text-xs text-twin-muted">View</span>
      <div className="flex overflow-hidden rounded-md border border-twin-line">
        {(["operational", "simulation"] as const).map((v) => (
          <button
            key={v}
            type="button"
            onClick={() => onView(v)}
            className={cn("px-3 py-1 text-sm", view === v ? "bg-twin-accent text-white" : "bg-twin-panel text-twin-text")}
          >
            {v === "operational" ? "Operational" : "Simulation (truth)"}
          </button>
        ))}
      </div>
      <label className="flex items-center gap-2 text-xs text-twin-muted">
        Overlay
        <select
          className="rounded-md border border-twin-line bg-twin-panel px-2 py-1 text-sm text-twin-text"
          value={overlay}
          onChange={(e) => onOverlay(e.target.value as Overlay)}
        >
          <option value="occupancy">Occupancy</option>
          <option value="temperature">Temperature</option>
          <option value="hvac">HVAC mode</option>
        </select>
      </label>
      <span
        title={`Live connection: ${connection}`}
        className={cn(
          "h-2.5 w-2.5 rounded-full",
          connection === "open" ? "bg-twin-occupied" : connection === "connecting" ? "bg-twin-held" : "bg-red-500",
        )}
      />
    </div>
  );
}
