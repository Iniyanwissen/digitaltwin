import { Area, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, XAxis, YAxis } from "recharts";

import { cn } from "@/lib/utils";

import type { View } from "./floorRenderer";
import type { LiveStore } from "./store";
import { TWIN } from "./theme";
import { useLiveRevision } from "./useLive";

const DAY_START_MIN = 6 * 60;
const DAY_END_MIN = 22 * 60;
const HOUR_TICKS = [6, 9, 12, 15, 18, 21].map((h) => h * 60);

function toMinute(m: string): number {
  const [h = 0, mm = 0] = m.split(":").map(Number);
  return h * 60 + mm;
}

function Kpi({ label, value, truth = false }: { label: string; value: React.ReactNode; truth?: boolean }) {
  return (
    <div className={cn("rounded-lg border border-twin-line bg-twin-inset px-2 py-1.5", truth && "border-dashed")}>
      <b className="block text-lg tabular-nums">{value}</b>
      <span className="text-[10px] tracking-wide text-twin-muted uppercase">
        {label}
        {truth && "*"}
      </span>
    </div>
  );
}

export function SidePanel({ store, view }: { store: LiveStore; view: View }) {
  useLiveRevision(store);
  const k = store.kpis;
  const truth = store.truthSummary;
  const data = store.series
    .map((p) => ({ ...p, minute: toMinute(p.m) }))
    .filter((p) => p.minute >= DAY_START_MIN);

  return (
    <section className="flex min-h-0 flex-col gap-2 overflow-hidden rounded-xl border border-twin-line bg-twin-panel p-3">
      <h2 className="text-xs font-semibold tracking-wider text-twin-muted uppercase">Live KPIs</h2>
      <div className="grid grid-cols-3 gap-1.5">
        <Kpi label="Employees inside" value={k?.employees_inside ?? "–"} />
        <Kpi label="Occupied desks" value={k?.occupied_desks ?? "–"} />
        <Kpi label="Held desks" value={k?.held_desks ?? "–"} />
        <Kpi label="Available desks" value={k?.available_desks ?? "–"} />
        <Kpi label="Desk util" value={k ? `${k.desk_util_pct}%` : "–"} />
        <Kpi label="Room util" value={k ? `${k.room_util_pct}%` : "–"} />
        <Kpi label="Room occupants" value={k?.room_occupants ?? "–"} />
        <Kpi label="Building util" value={k ? `${k.building_util_pct}%` : "–"} />
        <Kpi label="Peak today" value={k ? `${k.peak_today}${k.peak_time ? ` @${k.peak_time}` : ""}` : "–"} />
        <Kpi label="ECO zones" value={k?.hvac_eco_zones ?? "–"} />
        {view === "simulation" && (
          <>
            <Kpi label="Truth inside" value={truth?.inside ?? "–"} truth />
            <Kpi label="Truth in meetings" value={truth?.in_meeting ?? "–"} truth />
          </>
        )}
      </div>

      <h2 className="mt-1 text-xs font-semibold tracking-wider text-twin-muted uppercase">Today — people vs desks</h2>
      <div className="h-40">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 6, right: 8, bottom: 0, left: -18 }}>
            <CartesianGrid stroke={TWIN.line} vertical={false} />
            <XAxis
              dataKey="minute"
              type="number"
              domain={[DAY_START_MIN, DAY_END_MIN]}
              ticks={HOUR_TICKS}
              tickFormatter={(v: number) => `${Math.floor(v / 60)}:00`}
              stroke={TWIN.label}
              fontSize={10}
            />
            <YAxis stroke={TWIN.label} fontSize={10} />
            {k && <ReferenceLine y={k.total_desks} stroke={TWIN.over} strokeDasharray="4 4" />}
            <Area dataKey="inside" name="Inside (badge)" fill={TWIN.accent} fillOpacity={0.25} stroke={TWIN.accent} isAnimationActive={false} />
            <Line dataKey="desks" name="Desks (sensor)" stroke={TWIN.occupied} dot={false} strokeWidth={1.5} isAnimationActive={false} />
            <Line dataKey="held" name="Held" stroke={TWIN.held} dot={false} strokeDasharray="3 3" strokeWidth={1.5} isAnimationActive={false} />
            <Line dataKey="rooms" name="In rooms" stroke={TWIN.anonymous} dot={false} strokeWidth={1.5} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div className="flex flex-wrap gap-3 text-[10px] text-twin-muted">
        <span className="text-twin-accent">■ inside (badge)</span>
        <span className="text-twin-occupied">— desks (sensor)</span>
        <span className="text-twin-held">┄ held</span>
        <span className="text-twin-anonymous">— in rooms</span>
        <span className="text-red-400">┄ desk capacity</span>
      </div>

      <h2 className="mt-1 text-xs font-semibold tracking-wider text-twin-muted uppercase">
        Live events{" "}
        <span className="normal-case">
          (<span className="text-twin-identified">identified</span> · <span className="text-twin-anonymous">anonymous</span> ·{" "}
          <span className="text-twin-system">system</span>)
        </span>
      </h2>
      <div className="min-h-0 flex-1 overflow-auto font-mono text-[11px] leading-5">
        {store.feed.map((f, i) => (
          <div
            key={`${f.t}-${f.entity}-${i}`}
            className={cn(
              "truncate border-b border-twin-line/50",
              f.identity === "IDENTIFIED" ? "text-twin-identified" : f.identity === "ANONYMOUS" ? "text-twin-anonymous" : "text-twin-system",
            )}
          >
            {f.t} {f.type} {f.entity} {f.detail}
          </div>
        ))}
        {store.feed.length === 0 && <div className="text-twin-muted">Waiting for events… press Start.</div>}
      </div>
      <div className="text-[10px] text-twin-muted">{store.eventsTotal.toLocaleString("en-US")} events processed</div>
    </section>
  );
}
