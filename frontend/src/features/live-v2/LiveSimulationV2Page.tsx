import "./twin-v2.css";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { humanize } from "@/lib/format";
import { useLiveConnection, useLiveRevision } from "@/features/live/useLive";

import { liveV2Api, V2_SOCKET_PATH } from "./api";
import { FloorPlanV2 } from "./FloorPlanV2";
import { AutomationLog, SelectionPanel, SustainabilityPanel } from "./Panels";
import { DEPT_COLOURS } from "./planStyle";
import { LiveStoreV2 } from "./store";
import type { Layer, Selection } from "./types";

const THEME_KEY = "live-v2-theme";
const LAYERS: [Layer, string][] = [
  ["occupancy", "Occupancy"],
  ["temperature", "Temperature"],
  ["lighting", "Lighting"],
  ["hvac", "HVAC"],
];
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function readTheme(): "light" | "dark" {
  try {
    return window.localStorage.getItem(THEME_KEY) === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

/** "2026-09-28T10:42:07+05:30" -> "Mon 28 Sep · 10:42" (building local time as sent). */
function clockLabel(iso: string | undefined): string {
  if (!iso) return "--";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  const wd = new Date(Date.UTC(y ?? 1970, (m ?? 1) - 1, d ?? 1)).getUTCDay();
  return `${WEEKDAYS[wd]} ${d} ${MONTHS[(m ?? 1) - 1]} · ${iso.slice(11, 16)}`;
}

function Swatch({ bg, border, round = false }: { bg: string; border: string; round?: boolean }) {
  return <i className="sw" style={{ background: bg, borderColor: border, borderRadius: round ? "50%" : undefined, width: round ? 10 : undefined }} />;
}

const LEGENDS: Record<Layer, [React.ReactNode, string][]> = {
  occupancy: [
    [<Swatch key="o" bg="var(--desk-occ)" border="var(--desk-occ-line)" />, "Occupied"],
    [<Swatch key="h" bg="var(--desk-held)" border="var(--desk-held-line)" />, "Held, away"],
    [<Swatch key="v" bg="var(--desk-vacant)" border="var(--desk-vacant-line)" />, "Available"],
    [<Swatch key="r" bg="color-mix(in srgb, var(--accent) 32%, var(--paper))" border="var(--room-line)" />, "Room in use"],
    [<b key="w" style={{ color: "var(--warm)", fontWeight: 500 }}>25.9° ▲</b>, "Warm and rising"],
  ],
  temperature: [
    [<Swatch key="1" bg="var(--t-cold)" border="var(--t-cold)" />, "21°"],
    [<Swatch key="2" bg="var(--t-comfort)" border="var(--desk-vacant-line)" />, "22.5–24.5° comfort"],
    [<Swatch key="3" bg="var(--t-warm)" border="var(--t-warm)" />, "26°"],
    [<Swatch key="4" bg="var(--t-hot)" border="var(--t-hot)" />, "27.5°"],
    [
      <span key="a">
        <b style={{ color: "var(--warm)", fontWeight: 500 }}>▲</b>
        <b style={{ color: "var(--cool)", fontWeight: 500 }}>▼</b>
      </span>,
      "Change in last 15 min",
    ],
  ],
  lighting: [
    [<Swatch key="f" bg="var(--l-full)" border="#C9A10A" />, "Full"],
    [<Swatch key="d" bg="var(--l-day)" border="#C9A10A" />, "Daylight dimmed"],
    [<Swatch key="m" bg="var(--l-dim)" border="var(--ink-3)" />, "Dimmed, empty"],
    [<Swatch key="x" bg="var(--l-off)" border="var(--ink-2)" />, "Off"],
  ],
  hvac: [
    [<Swatch key="e" bg="color-mix(in srgb, var(--h-eco) 28%, transparent)" border="var(--h-eco)" />, "Eco"],
    [<Swatch key="p" bg="color-mix(in srgb, var(--h-precool) 28%, transparent)" border="var(--h-precool)" />, "Pre-cool"],
    [<Swatch key="b" bg="color-mix(in srgb, var(--h-high) 28%, transparent)" border="var(--h-high)" />, "High / vent boost"],
  ],
};

/**
 * Live Simulation v2 (v0.3 pack): real floor plan in metres, crowd-driven environment and ESG
 * automation (docs/floor-twin-design-v2.md). Light by default; the dark toggle applies to this
 * page only. Every number comes from the v2 backend; this page formats and draws.
 */
export function LiveSimulationV2Page() {
  const [simulation, setSimulation] = useState(false);
  const [layer, setLayer] = useState<Layer>("occupancy");
  const [floorChoice, setFloorChoice] = useState<string | null>(null);
  const [selection, setSelection] = useState<Selection>(null);
  const [theme, setTheme] = useState<"light" | "dark">(readTheme);
  const { store, connection } = useLiveConnection(simulation, {
    path: V2_SOCKET_PATH,
    createStore: () => new LiveStoreV2(),
  });
  useLiveRevision(store);
  const layout = useQuery({ queryKey: ["v2-layout"], queryFn: liveV2Api.layout, staleTime: Infinity });

  useEffect(() => {
    try {
      window.localStorage.setItem(THEME_KEY, theme);
    } catch {
      /* storage unavailable: theme is per session */
    }
  }, [theme]);

  const deptColour = useMemo(
    () => Object.fromEntries((layout.data?.departments ?? []).map((d, i) => [d, DEPT_COLOURS[i % DEPT_COLOURS.length]!])),
    [layout.data],
  );

  const floors = layout.data?.floors ?? [];
  const floor = floors.find((f) => f.floor_id === floorChoice) ?? floors.find((f) => f.floor_number === 2) ?? floors[0];
  const status = store.status;
  const state = status?.status ?? "STOPPED";
  const kpi = floor ? store.floorKpis[floor.floor_id] : undefined;
  const truthOnFloor = floor ? (store.truthSummary as Record<string, number> | null)?.[`inside_${floor.floor_id}`] : undefined;
  const bookable = floor ? floor.rooms.filter((r) => r.is_bookable && !r.area_subtype).length : 0;

  return (
    <div className="twin2 -m-6 min-h-[calc(100%+3rem)]" data-theme={theme}>
      <header className="t2-header">
        <div>
          <b style={{ fontWeight: 600, fontSize: 15, display: "block" }}>Workplace twin v2</b>
          <span style={{ color: "var(--ink-2)", fontSize: 12 }}>{layout.data?.building.name ?? "Building A"}</span>
        </div>
        <span className="t2-clock">{clockLabel(status?.sim_time)}</span>
        <span className={`t2-live ${state === "RUNNING" ? "on" : ""}`} title={`Live connection: ${connection}`}>
          <i />
          {state === "RUNNING" ? `${status?.speed}×` : humanize(state)}
        </span>
        <button type="button" disabled={state === "RUNNING"} onClick={() => void liveV2Api.command(state === "PAUSED" ? "RESUME" : "START")}>
          {state === "PAUSED" ? "Resume" : "Start"}
        </button>
        <button type="button" disabled={state !== "RUNNING"} onClick={() => void liveV2Api.command("PAUSE")}>
          Pause
        </button>
        <button type="button" onClick={() => void liveV2Api.command("RESET")}>
          Reset
        </button>
        <select aria-label="Speed" value={status?.speed ?? ""} onChange={(e) => void liveV2Api.command("SET_SPEED", Number(e.target.value))}>
          {(status?.allowed_speeds ?? []).map((s) => (
            <option key={s} value={s}>
              {s}×
            </option>
          ))}
        </select>
        <span className="grow" />
        <div className="seg" role="group" aria-label="View">
          <button type="button" aria-pressed={!simulation} onClick={() => setSimulation(false)}>
            Operational
          </button>
          <button type="button" aria-pressed={simulation} onClick={() => setSimulation(true)}>
            Simulation
          </button>
        </div>
        <div className="seg" role="group" aria-label="Layer">
          {LAYERS.map(([key, label]) => (
            <button key={key} type="button" aria-pressed={layer === key} onClick={() => setLayer(key)}>
              {label}
            </button>
          ))}
        </div>
        <button
          type="button"
          aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
          onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
        >
          {theme === "dark" ? "Light" : "Dark"}
        </button>
      </header>

      {layout.isError && <p className="note" style={{ paddingTop: 16 }}>Live Simulation v2 is not available: {String(layout.error)}</p>}
      {floor && (
        <main className="t2-main">
          <div className="sheet">
            <div className="plan-head">
              <h1>{floor.name}</h1>
              <span className="meta">
                {humanize(floor.desk_policy)} · {floor.desks.length} desks · {bookable} rooms
              </span>
              <div className="seg" role="group" aria-label="Floor">
                {floors.map((f) => (
                  <button
                    key={f.floor_id}
                    type="button"
                    aria-pressed={f.floor_id === floor.floor_id}
                    onClick={() => {
                      setFloorChoice(f.floor_id);
                      setSelection(null);
                    }}
                  >
                    {f.floor_number}
                  </button>
                ))}
              </div>
            </div>
            <div className="opstrip">
              <div>
                <b>{kpi ? `${Math.round(kpi.desk_util_pct)}%` : "–"}</b>
                <span>Desk utilisation</span>
              </div>
              <div>
                <b>{kpi ? `${kpi.occupied_desks} · ${kpi.held_desks}` : "–"}</b>
                <span>Desks occupied · held</span>
              </div>
              <div>
                <b>{kpi ? `${kpi.rooms_in_use}/${kpi.rooms}` : "–"}</b>
                <span>Meeting rooms in use</span>
              </div>
              <div>
                <b>{kpi?.est_people ?? "–"}</b>
                <span>Estimated people</span>
              </div>
              <div>
                <b>{kpi?.warm_spots ?? "–"}</b>
                <span>Warm spots (≥ 25.5 °C)</span>
              </div>
              {simulation && (
                <div className="truth">
                  <b>{truthOnFloor ?? 0}</b>
                  <span>True headcount*</span>
                </div>
              )}
            </div>
            <div className="plan-wrap">
              <FloorPlanV2
                floor={floor}
                store={store}
                layer={layer}
                simulation={simulation}
                deptColour={deptColour}
                selection={selection}
                onSelect={setSelection}
              />
            </div>
            <div className="legend">
              {LEGENDS[layer].map(([swatch, label]) => (
                <span key={label}>
                  {swatch}
                  {label}
                </span>
              ))}
              {simulation &&
                Object.entries(deptColour).map(([dept, colour]) => (
                  <span key={dept}>
                    <Swatch bg={colour} border={colour} round />
                    {dept}
                  </span>
                ))}
            </div>
            <p className="note">
              {simulation
                ? "Dots are ground truth from the simulation. Figures above stay sensor- and badge-based; the striped cell is truth."
                : "Shows only what building systems report: desk sensors, logins, room counters, badge readers and zone sensors."}
            </p>
          </div>
          <aside>
            <SelectionPanel selection={selection} floor={floor} />
            <SustainabilityPanel store={store} />
            <AutomationLog store={store} floorId={floor.floor_id} />
          </aside>
        </main>
      )}
      {!floor && !layout.isError && <p className="note" style={{ paddingTop: 16 }}>Loading floor plan…</p>}
    </div>
  );
}
