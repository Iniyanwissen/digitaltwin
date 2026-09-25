# Visualization and UI Specification

> Status: DRAFT v0.2. Related: `live-streaming.md`, `data-model.md`, `event-model.md`
> A working prototype of the core views (isometric building, 2D floor twin, Simulation View dots, overlays, hybrid chart, live feed, KPIs) is in `reference/refsim/viewer/index.html`. Run `python -m refsim serve` from `reference/` to see it. The React app must reproduce its behaviour and visual language, not its code structure.

---

## 1. Principles

- **Every number comes from the backend.** The frontend formats and draws; it never computes utilisation, counts or aggregates.
- **Every screen maps to a defined data source** (§3). If a widget has no row in §3, it does not get built.
- **Two views of the world, never mixed:**
  - **Operational View** (default): what the building's systems report — badge readers, logins, anonymous sensors, BMS.
  - **Simulation View**: ground truth from the engine (moving people). Always labelled "Simulation truth", dashed borders on truth KPIs, separate API endpoints/channels.
- **Identity only from identity-aware sources.** Desk details show an employee only when a workstation login exists. Room sensors show counts, never names. Door-reader entries may show who badged in (access control), labelled as such.
- **Live where it matters, cached where it doesn't.** Live data via WebSocket deltas; historical charts cached aggressively (past days never change).
- **Team-level for people analytics.** Network, flow and distribution views aggregate at team level.

---

## 2. Design Tokens (match the reference viewer)

| Token | Value | Use |
|---|---|---|
| `--bg` | `#0e1117` | app background |
| `--panel` | `#161b24` | cards/panels |
| `--line` | `#262e3b` | borders, grid lines |
| `--text` / `--muted` | `#e6e9ef` / `#8a94a6` | text |
| `--accent` | `#4f8cff` | primary actions, "people (badge)" series |
| `--occupied` | `#22c55e` | desk occupied (sensor) |
| `--held` | `#f59e0b` | logged in + vacant ("held") |
| `--vacant` | `#334155` | vacant desk |
| `--unavailable` | `#0b0e13` | unavailable desk |
| `--room` | `rgba(79,140,255, .15–.7)` | room fill scaled by count/capacity |
| `--identified` / `--anonymous` / `--system` | `#4f8cff` / `#a78bfa` / `#94a3b8` | event identity class colouring |
| HVAC | ECO `#22c55e` · NORMAL `#94a3b8` · HIGH `#f97316` | HVAC overlay/bands |
| Temperature ramp | 21 °C blue → 24 °C purple → 27 °C red | temperature overlay |
| Utilisation bands | Very Low <20 · Low 20–40 · Moderate 40–60 · High 60–80 · Very High ≥80 | heat maps (green → red) |
| Department palette | `#60a5fa #f472b6 #34d399 #fbbf24 #a78bfa #f87171 #2dd4bf #fb923c` | dots, network nodes, team charts |

Typography: system UI stack, tabular numerals for KPIs and clocks, monospace for event feeds. Dark theme default; light theme optional later.

---

## 3. Screen → Data Mapping

| Screen (nav) | Widgets | API | Backed by | Update |
|---|---|---|---|---|
| **Overview** | KPI cards (SPEC §24), H1 hybrid chart, floor utilisation bars, team distribution today | `/api/v1/live/kpis`, `/ws/live` | Redis state + rolling series | live |
| **Live Workplace** | floor cards (est. headcount, occupied/held desks, room occupants, ECO zones) | `/ws/live` | Redis `st:floor:*` | live |
| **Building View** | isometric stack, per-floor utilisation, click → twin | `/api/v1/layout`, `/ws/live` | layout + Redis | live |
| **Floor Digital Twin** | 2D floor, overlays, desk/room panels, Simulation View dots, time scrubber | `/api/v1/layout/floors/{id}`, `/ws/live`, `/api/v1/replay/{floor}?minute=`, `/api/v1/truth/positions` (sim view only) | layout, Redis, `sim.floor_snapshot`, engine truth | live + replay |
| **Employees** | table (filters: team, dept, work mode, profile), person detail: today's badge/login timeline | `/api/v1/employees`, `/api/v1/employees/{id}/today` | PostgreSQL master + Redis person state (identified events only) | on demand |
| **Teams** | distribution by floor (bars + zone heat map), collaboration network, co-location vs collaboration | `/api/v1/analytics/teams/*` | `MART_TEAM_UTILIZATION`, `MART_TEAM_COLLAB_NETWORK`, `MART_TEAM_COLOCATION` | cached |
| **Rooms** | utilisation table, right-sizing, booked-vs-used Gantt (H2), ghost bookings | `/api/v1/analytics/rooms/*`, `/api/v1/bookings?date=` | `MART_ROOM_UTILIZATION`, `MART_BOOKING_EFFECTIVENESS`, `FACT_ROOM_USAGE`, SaaS | cached (today: live overlay) |
| **Workspaces** | desk table, rarely-used flag, desk holding hours | `/api/v1/analytics/desks` | `MART_DESK_UTILIZATION` | cached |
| **Live Events** | virtualised event table, filters (type, employee, floor, workspace, sensor, identity class), rate indicator | `/ws/live?channel=events` | processor live feed | live |
| **Environmental Monitoring** | zone metric tiles, temperature by zone, H3 (temp vs occupancy + HVAC bands), automation log | `/ws/live`, `/api/v1/analytics/environment/hourly` | Redis env/hvac, `MART_ENVIRONMENT_HOURLY`, `FACT_AUTOMATION_EVENT` | live + cached |
| **Real Estate Analytics** | capacity metrics, P90 peak, desk-to-employee ratio, rule-based observations with metric values | `/api/v1/analytics/real-estate` | `MART_REAL_ESTATE_UTILIZATION`, `MART_RECOMMENDATIONS` | cached |
| **Capacity Planning** | saved scenarios, scenario comparison (bullet charts H7) | `/api/v1/scenarios` | scenario runs | on demand |
| **Scenario Simulator** | scenario forms S1–S5, results | `/api/v1/scenarios/*` | `simulation-scenarios.md` | on demand |
| **Historical Analytics** | attendance trend, peak trend, H4 arrivals/headcount, H5 calendar heat map, H6 floor small multiples, movement flow Sankey | `/api/v1/analytics/history/*` | `MART_DAILY_ATTENDANCE`, `MART_PEAK_OCCUPANCY`, `MART_MOVEMENT_FLOW`, `FACT_BUILDING_OCCUPANCY_15MIN` | cached |
| **Data Pipeline** | lineage (Sources → RAW → STAGING → CORE → MART → App) with live record counts | `/api/v1/pipeline` | `ops.pipeline_run`, `ops.pipeline_layer_count` | poll 5 s |
| **Data Sources** | per-source status, events received, last event, records processed, failures, latency; DQ panel (Phase 9) | `/api/v1/sources` | processor counters, `ops.source_status_snapshot`, `MART_DATA_QUALITY` | poll 2 s |
| **Simulation Control** | status, sim date/time, speed, START/PAUSE/RESUME/STOP/RESET, history generation, truth counters (dashed) | `/api/v1/simulation/*`, `/ws/live?channel=status` | engine status | live |
| **Settings** | active config (read-only v1), seed, presets | `/api/v1/meta` | config | on demand |

---

## 4. Live Screens

- KPI cards: value, label, optional delta vs same time last week (cached). Truth KPIs have dashed borders and an asterisk.
- **H1 People vs desks (hybrid)** — x: 06:00–22:00 sim time.
  - Area: employees inside (badge, identified).
  - Lines: occupied desks (sensor), held desks (dashed), room occupants.
  - Horizontal dashed line: desk capacity; shaded band above 90% of capacity.
  - Optional ghost line: same weekday last week (from warehouse).
- Live Events: virtualised list (react-virtual), buffer capped at 2,000 rows, pause/auto-scroll, identity-class colour.

---

## 5. Digital Twin

### 5.1 Isometric building (2.5D)
- Floors stacked as parallelograms, coloured by desk utilisation (green → red), selected floor outlined, label `Floor n  xx%`.
- Click selects the floor for the 2D view. Optional mini-sparkline per floor on hover.
- Canvas 2D (no 3D engine). Full 3D (three.js) is explicitly out of scope.

### 5.2 2D floor twin
- **Layers:**
  1. Static layer (zones, zone labels, restricted-zone dashed red border, readers as triangles: entrance white, lobby white, room door blue, secure red) — rendered once per floor/resize into an offscreen canvas.
  2. Overlay layer: occupancy (default) | temperature | HVAC mode | bookings (today's booked rooms outlined) | heat map (Today / 7D / 30D from `MART_HEATMAP`).
  3. Dynamic layer: desks (state colours §2), rooms/common areas (fill by count/capacity, `count/cap` label, red border if count > capacity).
  4. Simulation View layer: truth dots (Canvas or PixiJS), department colours, 900 ms ease-in-out tweening between positions; dots leave/enter when changing floors.
- **Detail panels:**
  - Desk: workspace ID, zone, sensor status + last change, logged-in employee (**workstation login only**), utilisation today, device type.
  - Room: type, capacity, sensor count, current booking + check-in status, door-reader entries today (identified, labelled), today's usage bar.
  - Zone: temperature, CO2, HVAC mode, last automation action.
- **Time scrubber:** slider over today (per sim-minute), play/pause replay at 1–60x. Reads `sim.floor_snapshot`; while scrubbing, live updates are buffered and "Back to live" returns.

### 5.3 Rendering performance rules
- Redraw only when dirty (new frame received, tween in progress, user interaction).
- Never create one DOM/SVG node per desk or person for live updates; SVG is acceptable for the static layer only.
- Batch state updates from each WebSocket frame into one render.
- Level of detail: building view uses floor aggregates; desks/dots load only for the open floor.
- Device-pixel-ratio aware canvases; resize invalidates the static cache.

---

## 6. Hybrid Charts

| ID | Chart | Composition | Data |
|---|---|---|---|
| H1 | People vs desks vs capacity | area (inside) + lines (occupied, held, rooms) + capacity line + >90% band | live series |
| H2 | Booked vs used (per room, Gantt) | booking bars + sensor-occupied bars stacked per room row; ghost bookings hatched; check-ins as ticks | `FACT_ROOM_BOOKING`, `FACT_ROOM_USAGE`, `FACT_ROOM_CHECK_IN` |
| H3 | Temperature vs occupancy | occupancy bars + temperature line (dual axis) + HVAC mode background bands + automation markers | `MART_ENVIRONMENT_HOURLY`, `FACT_AUTOMATION_EVENT` |
| H4 | Arrivals and headcount | arrival/departure histogram (15 min) + cumulative headcount line | `FACT_BUILDING_VISIT` |
| H5 | Attendance calendar heat map | weekdays × weeks (or weekday × hour) cells coloured by attendance % | `MART_DAILY_ATTENDANCE` |
| H6 | Floor small multiples | one sparkline per floor, shared y-scale, peak marker | `MART_FLOOR_UTILIZATION` |
| H7 | Scenario bullet charts | projected occupancy bar vs capacity marker vs historical P90 band, per floor | scenario results |

Library guidance: Recharts `ComposedChart` for H1, H3, H4, H6; custom SVG/visx for H2, H5, H7.

---

## 7. Network and Flow Graphs

| ID | Graph | Nodes / edges | Data | Library |
|---|---|---|---|---|
| N1 | Team collaboration network | nodes = teams (size = headcount, colour = department); edges = shared meetings (width = meeting hours) | `MART_TEAM_COLLAB_NETWORK` | d3-force (or react-force-graph-2d on canvas) |
| N2 | Co-location vs collaboration | scatter: x = seating proximity, y = collaboration strength; top-left quadrant = "collaborate a lot, sit apart" → relocation candidates; click opens S2 what-if | `MART_TEAM_COLOCATION` | Recharts scatter |
| N3 | Movement flow | Sankey: entrance → floors → area types (desk, meeting, cafeteria, collaboration); or chord between floors | `MART_MOVEMENT_FLOW` | d3-sankey / d3-chord |

Controls: period (7D/30D), department filter, edge threshold slider, highlight a team. No individual-level networks.

---

## 8. Recommended Frontend Dependencies

See `dependencies.md` for versions. Core: React 18, TypeScript, Vite, Tailwind, TanStack Query (REST caching), Zustand (live state store), Recharts, d3 (force, sankey, chord, scale), @tanstack/react-virtual, pixi.js (optional for dots > 1,000), date-fns.

---

## 9. Acceptance Checklist (UI)

- [ ] Every widget traces to a row in §3.
- [ ] No utilisation/aggregate maths in React components.
- [ ] Operational and Simulation views are visually distinct; truth never appears in Operational View.
- [ ] Desk identity only from login; room identity only from door readers (labelled).
- [ ] Twin at 60x medium scale stays ≥ 50 fps; WebSocket backlog bounded.
- [ ] Tokens from §2 used everywhere; no hard-coded colours in components.
