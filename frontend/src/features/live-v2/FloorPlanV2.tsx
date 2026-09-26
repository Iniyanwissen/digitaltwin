import { useMemo } from "react";

import {
  CHIP_COLOURS,
  CHIP_TEXT,
  COMMON_ZONE_TYPES,
  hvacState,
  lightFill,
  temperatureFill,
  trendArrow,
  type RoomBadge,
} from "./planStyle";
import type { LiveStoreV2 } from "./store";
import type { Layer, Selection, V2Floor } from "./types";

interface Props {
  floor: V2Floor;
  store: LiveStoreV2;
  layer: Layer;
  simulation: boolean;
  deptColour: Record<string, string>;
  selection: Selection;
  onSelect: (s: Selection) => void;
}

const f1 = (v: number | null | undefined) => (v == null ? "–" : v.toFixed(1));

/**
 * Floor twin v2 drawn in metres (floor-twin-design-v2.md §3-4). Values come from the live store
 * (backend-computed); this component only maps them to shapes, colours and labels.
 */
export function FloorPlanV2({ floor, store, layer, simulation, deptColour, selection, onSelect }: Props) {
  const occ = layer === "occupancy";
  // Area id per zone: a zone filled by a common area is represented by that room.
  const zoneArea = useMemo(() => {
    const map: Record<string, string> = {};
    for (const z of floor.zones) map[z.zone_id] = z.zone_id;
    for (const r of floor.rooms) if (r.area_subtype) map[r.zone_id] = r.room_id;
    return map;
  }, [floor]);
  const commonRoom = useMemo(() => {
    const map: Record<string, (typeof floor.rooms)[number]> = {};
    for (const r of floor.rooms) if (r.area_subtype) map[r.zone_id] = r;
    return map;
  }, [floor]);
  const columnsY = useMemo(
    () => [0, ...new Set(floor.zones.map((z) => Math.round(z.y))), floor.height].sort((a, b) => a - b),
    [floor],
  );
  const columnsX = useMemo(() => Array.from({ length: Math.floor(floor.width / 8) + 1 }, (_, i) => i * 8), [floor]);
  const W = floor.width;
  const H = floor.height;

  const areaLabel = (areaId: string, x: number, y: number, w: number, h: number, isRoom: boolean, small: boolean) => {
    const v = store.areas[areaId];
    if (!v) return null;
    const trend = trendArrow(v[1]);
    let text: string;
    let colour = "var(--ink)";
    let top = !isRoom;
    if (occ) {
      if (!store.warmAreas.has(areaId)) return null;
      text = isRoom && w < 5.5 ? `${f1(v[0])}°▲` : `${f1(v[0])}° ${trend.text}`;
      colour = "var(--warm)";
      top = true;
    } else if (layer === "temperature") {
      text = small ? `${f1(v[0])}°` : `${f1(v[0])}°  ${trend.text}`;
      colour = small || trend.cls === "" ? "var(--ink)" : trend.colour;
    } else if (layer === "lighting") {
      text = v[4] ? `${v[4]}%` : "Off";
    } else {
      const hv = hvacState(v);
      if (!hv) return null;
      text = hv[0];
    }
    return (
      <text
        x={x + w - 0.4}
        y={isRoom && !top ? y + h - 0.45 : y + 1.05}
        textAnchor="end"
        fontSize={small ? 0.5 : 0.6}
        fontWeight={500}
        fill={colour}
        pointerEvents="none"
      >
        {text}
      </text>
    );
  };

  const overlayFill = (areaId: string): string | null => {
    const v = store.areas[areaId];
    if (!v || occ) return null;
    if (layer === "temperature") return temperatureFill(v[0]);
    if (layer === "lighting") return lightFill(v[4]);
    const hv = hvacState(v);
    return hv ? `color-mix(in srgb, ${hv[1]} 20%, transparent)` : null;
  };

  const select = (s: Selection) => () => onSelect(s);
  const onKey = (s: Selection) => (e: React.KeyboardEvent) => {
    if (e.key === "Enter") onSelect(s);
  };

  return (
    <svg className="plan" viewBox={`-0.8 -0.8 ${W + 1.6} ${H + 1.6}`} role="img" aria-label={`${floor.name} plan`}>
      <defs>
        <pattern id="t2-hatch" width={0.7} height={0.7} patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <line x1={0} y1={0} x2={0} y2={0.7} stroke="var(--core-hatch)" strokeWidth={0.18} />
        </pattern>
      </defs>
      <rect x={0} y={0} width={W} height={H} fill="var(--paper)" />

      {/* zones */}
      {floor.zones
        .filter((z) => z.zone_type !== "MEETING")
        .map((z) => {
          const area = zoneArea[z.zone_id]!;
          const common = commonRoom[z.zone_id];
          const fill = COMMON_ZONE_TYPES.has(z.zone_type) ? "var(--z-common)" : "var(--z-work)";
          const s: Selection = { kind: "area", id: area };
          const ov = overlayFill(area);
          return (
            <g key={z.zone_id} onClick={select(s)} style={{ cursor: "pointer" }}>
              <rect x={z.x} y={z.y} width={z.w} height={z.h} fill={fill} />
              {ov && <rect x={z.x + 0.08} y={z.y + 0.08} width={z.w - 0.16} height={z.h - 0.16} fill={ov} pointerEvents="none" />}
              {z.is_restricted && (
                <rect x={z.x + 0.15} y={z.y + 0.15} width={z.w - 0.3} height={z.h - 0.3} fill="none" stroke="var(--z-secure)" strokeWidth={0.1} strokeDasharray=".6 .35" />
              )}
              <text x={z.x + 0.5} y={z.y + 1.05} fontSize={0.66} fontWeight={500} fill="var(--ink-2)">
                {z.name + (z.is_restricted ? " · secure" : "")}
              </text>
              {common && (
                <text x={z.x + 0.5} y={z.y + 1.9} fontSize={0.6} fill="var(--ink-3)">
                  {`${store.rooms[common.room_id] ?? 0} of ${common.capacity}`}
                </text>
              )}
              {selection?.kind === "area" && selection.id === area && (
                <rect x={z.x + 0.2} y={z.y + 0.2} width={z.w - 0.4} height={z.h - 0.4} fill="none" stroke="var(--focus)" strokeWidth={0.14} />
              )}
              {areaLabel(area, z.x, z.y, z.w, z.h, false, false)}
            </g>
          );
        })}

      {/* cores, facade, glazing, columns, readers */}
      {floor.cores.map((c, i) => (
        <g key={`core${i}`}>
          <rect x={c.x} y={c.y} width={c.w} height={c.h} fill="url(#t2-hatch)" stroke="var(--wall)" strokeWidth={0.12} />
          <text x={c.x + c.w / 2} y={c.y + c.h / 2 + 0.22} textAnchor="middle" fontSize={0.62} fill="var(--ink-3)">
            {c.label}
          </text>
        </g>
      ))}
      <rect x={0} y={0} width={W} height={H} fill="none" stroke="var(--wall)" strokeWidth={0.28} />
      <rect x={0.14} y={0.14} width={W - 0.28} height={H - 0.28} fill="none" stroke="var(--glass)" strokeWidth={0.14} strokeDasharray="1.7 .3" />
      {columnsX.flatMap((x) =>
        columnsY.map((y) => <rect key={`c${x}-${y}`} x={x - 0.22} y={y - 0.22} width={0.44} height={0.44} fill="var(--column)" />),
      )}

      {/* meeting rooms */}
      {floor.rooms
        .filter((r) => !r.area_subtype)
        .map((r) => {
          const count = store.rooms[r.room_id] ?? 0;
          const u = Math.min(1, count / Math.max(1, r.capacity));
          const chip: RoomBadge | undefined = store.chips[r.room_id] ?? (store.booked[r.room_id] ? "booked" : undefined);
          const over = occ && chip === "over";
          const released = occ && chip === "released";
          const dashed = occ && (chip === "released" || chip === "booked");
          const small = r.capacity === 1;
          const s: Selection = { kind: "area", id: r.room_id };
          const ov = overlayFill(r.room_id);
          const label = chip ? (r.w < 5.5 ? CHIP_TEXT[chip][1] : CHIP_TEXT[chip][0]) : "";
          const narrow = r.w < 5.5;
          const chipText = chip === "booked" ? (narrow ? `${store.booked[r.room_id]}` : `${label} ${store.booked[r.room_id]}`) : label;
          const chipW = Math.min(chipText.length * 0.31 + 0.7, r.w - 0.7);
          return (
            <g
              key={r.room_id}
              tabIndex={0}
              role="button"
              aria-label={`${r.name}, ${count} of ${r.capacity}`}
              onClick={select(s)}
              onKeyDown={onKey(s)}
              style={{ cursor: "pointer" }}
            >
              <rect
                x={r.x + 0.08}
                y={r.y + 0.08}
                width={r.w - 0.16}
                height={r.h - 0.16}
                fill={!occ ? "var(--panel)" : count ? `color-mix(in srgb, var(--accent) ${Math.round(10 + 30 * u)}%, var(--paper))` : "var(--z-meet)"}
                stroke={over ? "var(--danger)" : released ? "var(--released)" : "var(--room-line)"}
                strokeWidth={over || released ? 0.15 : 0.08}
                strokeDasharray={dashed ? ".45 .3" : undefined}
              />
              {ov && <rect x={r.x + 0.08} y={r.y + 0.08} width={r.w - 0.16} height={r.h - 0.16} fill={ov} pointerEvents="none" />}
              <text x={r.x + 0.4} y={r.y + (small ? 1 : 1.15)} fontSize={small ? 0.54 : 0.66} fontWeight={500} fill="var(--room-text)">
                {r.name}
              </text>
              <text x={r.x + 0.4} y={r.y + (small ? 1.75 : 2)} fontSize={0.58} fill="var(--ink-2)">
                {`${count}/${r.capacity}`}
              </text>
              {occ && chip && !small && (
                <g>
                  <rect x={r.x + 0.35} y={r.y + r.h - 1.25} width={chipW} height={0.8} rx={0.4} fill={CHIP_COLOURS[chip][1]} stroke={CHIP_COLOURS[chip][0]} strokeWidth={0.05} />
                  <text x={r.x + 0.35 + chipW / 2} y={r.y + r.h - 0.66} textAnchor="middle" fontSize={0.5} fontWeight={500} fill={CHIP_COLOURS[chip][0]}>
                    {chipText}
                  </text>
                </g>
              )}
              {selection?.kind === "area" && selection.id === r.room_id && (
                <rect x={r.x + 0.2} y={r.y + 0.2} width={r.w - 0.4} height={r.h - 0.4} fill="none" stroke="var(--focus)" strokeWidth={0.14} />
              )}
              {areaLabel(r.room_id, r.x, r.y, r.w, r.h, true, small)}
            </g>
          );
        })}

      {/* desks (fade on non-occupancy layers) */}
      <g opacity={occ ? 1 : 0.35}>
        {floor.desks.map((d) => {
          const value = store.desks[d.workspace_id] ?? [0, 0];
          const state = value[0] ? "occ" : value[1] ? "held" : "vacant";
          const [fill, line] = !occ
            ? ["var(--desk-vacant)", "var(--desk-vacant-line)"]
            : state === "occ"
              ? ["var(--desk-occ)", "var(--desk-occ-line)"]
              : state === "held"
                ? ["var(--desk-held)", "var(--desk-held-line)"]
                : ["var(--desk-vacant)", "var(--desk-vacant-line)"];
          const s: Selection = { kind: "desk", id: d.workspace_id };
          return (
            <g
              key={d.workspace_id}
              tabIndex={0}
              role="button"
              aria-label={`Desk ${d.workspace_id}, ${state}`}
              onClick={select(s)}
              onKeyDown={onKey(s)}
              style={{ cursor: "pointer" }}
            >
              <rect x={d.x + 0.07} y={d.y + 0.05} width={d.w - 0.14} height={d.h - 0.1} rx={0.1} fill={fill} stroke={line} strokeWidth={0.06} />
              {occ && state === "held" && <circle cx={d.x + d.w / 2} cy={d.y + d.h / 2} r={0.13} fill="var(--panel)" />}
              {selection?.kind === "desk" && selection.id === d.workspace_id && (
                <rect x={d.x - 0.1} y={d.y - 0.1} width={d.w + 0.2} height={d.h + 0.2} rx={0.18} fill="none" stroke="var(--focus)" strokeWidth={0.12} />
              )}
            </g>
          );
        })}
      </g>

      {floor.readers.map((r) => (
        <g key={r.access_point_id} transform={`translate(${r.x} ${r.y})`}>
          <rect
            x={-0.26}
            y={-0.26}
            width={0.52}
            height={0.52}
            rx={0.1}
            transform="rotate(45)"
            fill={r.reader_type === "SECURE_ZONE" ? "var(--danger)" : r.reader_type === "ROOM_DOOR" ? "var(--accent)" : "var(--ink-2)"}
          />
          <title>{`${r.reader_type.replace("_", " ").toLowerCase()} reader`}</title>
        </g>
      ))}

      {/* ground-truth dots (Simulation view only) */}
      {simulation && (
        <g>
          {[...store.dots.entries()]
            .filter(([, d]) => d.floor === floor.floor_id)
            .map(([id, d]) => (
              <circle
                key={id}
                className="dot"
                r={0.3}
                fill={deptColour[d.dept] ?? "var(--ink-2)"}
                stroke="var(--paper)"
                strokeWidth={0.09}
                style={{ transform: `translate(${d.toX}px, ${d.toY}px)` }}
              />
            ))}
        </g>
      )}
    </svg>
  );
}
