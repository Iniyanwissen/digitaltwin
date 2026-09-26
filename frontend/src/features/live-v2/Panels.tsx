import { useQuery } from "@tanstack/react-query";

import { humanize } from "@/lib/format";

import { liveV2Api } from "./api";
import { HVAC_NAME, trendArrow } from "./planStyle";
import type { LiveStoreV2 } from "./store";
import type { AreaDetail, Selection, V2Floor } from "./types";

const DETAIL_POLL_MS = 2000;

function Sparkline({ detail }: { detail: AreaDetail }) {
  const temps = detail.history.map((h) => h.temp).filter((t): t is number => t != null);
  if (temps.length < 2 || detail.setpoint_c == null) return null;
  const W = 280;
  const H = 64;
  const all = [...temps, detail.setpoint_c];
  const lo = Math.min(...all) - 0.3;
  const hi = Math.max(...all) + 0.3;
  const X = (i: number) => (i / (temps.length - 1)) * (W - 8) + 4;
  const Y = (v: number) => H - 6 - ((v - lo) / (hi - lo)) * (H - 14);
  const path = temps.map((v, i) => `${i ? "L" : "M"}${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join("");
  const last = temps[temps.length - 1]!;
  return (
    <div className="spark">
      <svg width="100%" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Temperature over the last hour">
        <line x1={4} x2={W - 4} y1={Y(detail.setpoint_c)} y2={Y(detail.setpoint_c)} stroke="var(--ink-3)" strokeDasharray="4 3" strokeWidth={1} />
        <path d={path} fill="none" stroke="var(--warm)" strokeWidth={2} />
        <circle cx={X(temps.length - 1)} cy={Y(last)} r={3} fill="var(--warm)" />
      </svg>
      <small>Last hour · dashed line = setpoint {detail.setpoint_c.toFixed(1)} °C</small>
    </div>
  );
}

function Rows({ rows }: { rows: [string, React.ReactNode][] }) {
  return (
    <dl>
      {rows.map(([k, v]) => (
        <div key={k} style={{ display: "contents" }}>
          <dt>{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Selection panel: desk identity only from workstation login; room/area from sensors + booking system. */
export function SelectionPanel({ selection, floor }: { selection: Selection; floor: V2Floor }) {
  const desk = useQuery({
    queryKey: ["v2-desk", selection?.id],
    queryFn: () => liveV2Api.desk(selection!.id),
    enabled: selection?.kind === "desk",
    refetchInterval: DETAIL_POLL_MS,
  });
  const area = useQuery({
    queryKey: ["v2-area", selection?.id],
    queryFn: () => liveV2Api.area(selection!.id),
    enabled: selection?.kind === "area",
    refetchInterval: DETAIL_POLL_MS,
  });

  let body: React.ReactNode = <p className="hint">Select a desk, room or area on the plan.</p>;
  if (selection?.kind === "desk" && desk.data) {
    const d = desk.data;
    const zone = floor.zones.find((z) => z.zone_id === d.zone_id);
    body = (
      <Rows
        rows={[
          ["Desk", d.workspace_id.split("_").at(-1)],
          ["Area", zone?.name ?? d.zone_id],
          ["Sensor", d.has_sensor ? `${humanize(d.sensor_status)}${d.last_sensor_change ? ` since ${d.last_sensor_change.slice(0, 5)}` : ""}` : "No sensor"],
          ["Workstation", d.logged_in_employee ? `${d.logged_in_employee} logged in` : "No login"],
          ["Device", humanize(d.device_type)],
        ]}
      />
    );
  } else if (selection?.kind === "area" && area.data) {
    const a = area.data;
    const trend = trendArrow(a.delta_15m);
    const rows: [string, React.ReactNode][] = [
      [a.area_type === "ROOM" ? "Room" : "Area", a.name],
      ["People", a.people == null ? "–" : `${a.people}${a.capacity ? ` of ${a.capacity}` : ""}`],
      [
        "Temperature",
        a.temperature == null ? (
          "–"
        ) : (
          <>
            {a.temperature.toFixed(1)} °C <span className={trend.cls}>{trend.text}</span>
          </>
        ),
      ],
      ["CO₂", a.co2 == null ? "–" : `${Math.round(a.co2).toLocaleString("en-US")} ppm`],
      ["HVAC", `${HVAC_NAME[a.hvac_mode ?? ""] ?? a.hvac_mode ?? "–"}${a.ventilation_boost ? " · vent boost" : ""}`],
      ["Lighting", a.light_level_pct ? `${a.light_level_pct}%` : "Off"],
    ];
    if (a.current_booking) {
      const b = a.current_booking;
      rows.push(["Booking", `${b.start}–${b.end} · ${b.attendees} people${b.released ? " · released" : b.checked_in ? " · checked in" : ""}`]);
    } else if (a.next_booking) {
      rows.push(["Next booking", `${a.next_booking.start} · ${a.next_booking.attendees} people`]);
    }
    if (a.last_action) rows.push(["Automation", `${a.last_action.t} ${a.last_action.reason}`]);
    body = (
      <>
        <Rows rows={rows} />
        <Sparkline detail={a} />
      </>
    );
  }
  return (
    <section className="sheet detail">
      <h2>Selection</h2>
      {body}
    </section>
  );
}

export function SustainabilityPanel({ store }: { store: LiveStoreV2 }) {
  const e = store.esg;
  return (
    <section className="sheet">
      <h2>Sustainability today</h2>
      <div className="esg-grid">
        <div className="hero">
          <b>{e ? `${e.saved_pct.toFixed(1)}%` : "–"}</b>
          <span>Energy saved vs. no automation</span>
        </div>
        <div>
          <b>{e ? `${Math.round(e.kwh).toLocaleString("en-US")} kWh` : "–"}</b>
          <span>Energy used</span>
        </div>
        <div>
          <b>{e ? `${Math.round(e.co2e_kg).toLocaleString("en-US")} kg` : "–"}</b>
          <span>CO₂e avoided</span>
        </div>
        <div>
          <b>{e ? `₹${e.cost_inr.toLocaleString("en-IN")}` : "–"}</b>
          <span>Cost saved</span>
        </div>
        <div>
          <b>{e ? `${e.comfort_pct.toFixed(1)}%` : "–"}</b>
          <span>Comfort compliance</span>
        </div>
      </div>
    </section>
  );
}

const TAG_CLASS: Record<string, string> = { HVAC: "t-hvac", Lighting: "t-light", Rooms: "t-room" };

export function AutomationLog({ store, floorId }: { store: LiveStoreV2; floorId: string }) {
  const onFloor = store.actions.filter((a) => a.floor === floorId);
  const items = (onFloor.length ? onFloor : store.actions).slice(0, 4);
  return (
    <section className="sheet">
      <h2>Automation</h2>
      {items.length === 0 ? (
        <p className="hint">No automation actions yet. Press Start.</p>
      ) : (
        <ul className="log">
          {items.map((a, i) => (
            <li key={`${a.t}-${a.area}-${i}`}>
              <time>{a.t}</time>
              <div>
                <span className={`tag ${TAG_CLASS[a.tag] ?? "t-hvac"}`}>{a.tag}</span>
                {a.reason}
                <small>{a.area_name}</small>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
