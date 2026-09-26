> **Repo note (2026-09-27):** in this repo, v0.3 applies to **Live Simulation v2** only (`/live-v2`, `/api/v2`, `config/v2/`). Live Simulation v1 and the other pages keep the v0.2 design. See `decision-log.md`.

# Crowd-Driven Environment and ESG Automation

> Status: v0.3 (prototype scope for pitching). Extends `simulation-engine.md` §10–11 (environment, BMS), `event-model.md` §5.8–5.9, `data-model.md` §2/§4/§5.
> Scope: HVAC, lighting, meeting rooms. Out of scope (future pitch ideas only): floor consolidation, blinds, plug loads, lifts.

---

## 1. What changes

| Area | v0.2 | v0.3 |
|---|---|---|
| Environment granularity | one sensor per zone | one **environment area** per zone *and* per bookable room / common area (each is an HVAC + lighting zone) |
| Temperature driver | zone occupancy load, OU noise | **crowd load per area** (people / capacity) + solar gain by facade and hour, first-order response to setpoint |
| Automation | HVAC eco/high, setpoint, ventilation | + lighting (dim, daylight, off), meeting rooms (auto-release, pre-cool, right-size flag) |
| Outputs | readings + actions | + energy per area-interval, baseline energy, CO₂e, cost, comfort, 15-min temperature trend |

The rule from v0.1 stands: **automation reads observed data only** (sensors, bookings), never ground truth.

---

## 2. Crowd → environment model (per area, every tick)

Inputs per area `a`: observed-independent ground truth `people(a)` (physics uses truth — the room really heats up; only the BMS is limited to sensors), capacity, floor area m², facade, HVAC mode, setpoint, lighting level.

```
load        = min(1.5, people / capacity)                      # crowding, >1 means over capacity
solar       = solar_gain_c[facade] × daylight(hour)            # 0 when no facade or at night
target_temp = setpoint(mode) + occupancy_heat_c × load + solar
temp       ← target + (temp − target) × exp(−k(mode) × dt_min) + noise(σ=0.03·√dt_min)

gen_ppm     = co2_gen_ppm_per_min × load
vent        = ventilation_per_min[mode or BOOST]
co2_ss      = 420 + gen_ppm / vent
co2        ← co2_ss + (co2 − co2_ss) × exp(−vent × dt_min)

light_lux   = lux_full × light_level% (+ daylight lux on facade areas)
```

- `daylight(hour)` = sin curve 07:00–18:00, peak 1.0 at 12:30 (config).
- Defaults give: a full 4-seat room at setpoint 23.5 → ~24.8 °C; 5 people in it → ~25.5 °C+ and CO₂ > 1,000 ppm within ~15 sim-minutes. This is what makes the automation visible in a demo.
- Heat carries over between ticks, so crowding followed by cooling shows ▲ then ▼ in the 15-min trend.

---

## 3. Energy, carbon, cost and comfort (simple, explainable)

Per area per interval (dt in hours):

```
hvac_kw     = area_m2 × hvac_w_per_m2[mode] / 1000   (+ boost_w_per_m2 when ventilation boosted)
light_kw    = area_m2 × lighting_w_per_m2 × light_level% / 1000
energy_kwh  = (hvac_kw + light_kw) × dt
baseline_kwh = area_m2 × (hvac_w_per_m2[NORMAL] + lighting_w_per_m2) / 1000 × dt   during operating hours (07:00–20:00), else night setback
saved_kwh   = baseline_kwh − energy_kwh
co2e_kg     = kwh × grid_emission_factor_kg_per_kwh          # config, default 0.71 (verify against the latest CEA factor)
cost_inr    = kwh × tariff_inr_per_kwh                       # config, default 8.0, flat
comfort_ok  = occupied minute with 22.5 ≤ temp ≤ 25.5 and co2 < 1000
```

The baseline is a **shadow baseline** (what the same areas would draw with no automation). For a rigorous comparison, scenario S5 (BMS A/B, same seed) remains available.

---

## 4. Automation rules (prototype set)

All thresholds in config. Each rule has a per-area cooldown (default 10 min). Every action emits `AUTOMATION_ACTION` with a human-readable `reason`.

| Rule ID | Trigger (observed) | Action | Log text example |
|---|---|---|---|
| `HVAC_ECO_WHEN_EMPTY` | area count/desk sensors = 0 for 15 min | `SET_HVAC_MODE` ECO (setpoint 25.5) | "Team hub set to eco. Empty for 15 min." |
| `HVAC_NORMAL_ON_OCCUPANCY` | occupied while ECO | `SET_HVAC_MODE` NORMAL | "Team hub back to normal. People detected." |
| `COOL_WHEN_WARM` | temp ≥ 25.5 and occupied | `ADJUST_SETPOINT` −1 (min 22.5) | "Cooling increased in Noyyal. 25.8 °C with 5 people." |
| `VENT_BOOST_ON_CO2` | CO₂ > 1,000 ppm | `INCREASE_VENTILATION` on (off below 750) | "Boardroom ventilation boosted. CO₂ 1,020 ppm." |
| `PRECOOL_FOR_BOOKING` | booking starts ≤ 20 min, expected ≥ 50% capacity, room ECO | `SET_HVAC_MODE` PRECOOL | "Amaravathi pre-cooling. Booked for 11:00, 7 attendees." |
| `LIGHTS_DIM_WHEN_EMPTY` | zone empty 15 min | `SET_LIGHT_LEVEL` 30% | "Team hub dimmed to 30%." |
| `LIGHTS_OFF_EMPTY_ROOM` | room count = 0 for 5 min, no booking in next 30 min | `SET_LIGHT_LEVEL` 0 | "Vaigai lights off." |
| `DAYLIGHT_HARVEST` | facade zone, daylight(hour) ≥ 0.6, occupied | `SET_LIGHT_LEVEL` 70% | "Workspace A and B dimmed to 70%. Daylight." |
| `LIGHTS_OFF_AFTER_HOURS` | after 20:00 and zone empty | `SET_LIGHT_LEVEL` 0 | "Floor 2 lights off after hours." |
| `RELEASE_GHOST_BOOKING` | booking started 10 min ago, room count = 0, no panel check-in | `RELEASE_BOOKING` (SaaS status → `RELEASED`) + lights off + ECO | "Workshop booking released. No one arrived 10 min after start." |
| `FLAG_OVERSIZED_ROOM` | meeting in progress with count ≤ 35% capacity for 15 min | `FLAG_ROOM_RIGHTSIZE` (advisory) | "Bhavani oversized: 2 people in 6 seats." |
| `FLAG_OVER_CAPACITY` | count > capacity for 5 min | `FLAG_OVER_CAPACITY` (advisory) + vent boost | "Noyyal over capacity: 5 in 4 seats." |

Rules are evaluated in this order per area; at most one HVAC and one lighting action per area per tick.

---

## 5. Contract changes

### 5.1 Master data (`data-model.md` §2)
- `floor`: `plan_width_m`, `plan_height_m` (metres; layout units = metres).
- `zone`: `facade` (`N|S|E|W|null`), `area_m2`, polygon/rect in metres.
- `room`: `area_m2`, `room_type` adds `FOCUS_BOOTH`; common areas stay `COMMON_AREA` rooms that fill their zone.
- `workspace`: `w`, `h` (m), `facing`.
- New `floor_core` (x, y, w, h, label) — render-only.
- New `env_area` view: every zone + every room with `area_m2`, `facade`, `capacity`, `env_sensor_id`, `hvac_zone_id` (= area id), `lighting_zone_id` (= area id).
- Sensors: an `ENVIRONMENT` sensor per env area (rooms gain one).

### 5.2 Events (`event-model.md`)
- `ENVIRONMENT_READING` payload adds: `setpoint_c`, `hvac_mode` (`ECO|NORMAL|HIGH|PRECOOL`), `ventilation_boost` (bool), `light_level_pct`, `entity_type` may now be `ROOM`.
- `AUTOMATION_ACTION.action` adds: `SET_LIGHT_LEVEL`, `RELEASE_BOOKING`, `FLAG_ROOM_RIGHTSIZE`, `FLAG_OVER_CAPACITY`; payload adds `reason` (plain text), `area_type` (`ZONE|ROOM`), `booking_id` (for room actions).
- New system event `ENERGY_INTERVAL` (source `BMS`, identity `SYSTEM`, stream `ev.environment`), one per env area per 15 sim-minutes:
  `{ "area_id", "kwh_hvac", "kwh_lighting", "kwh_baseline", "hvac_mode", "light_level_pct_avg", "occupied_minutes", "comfort_ok_minutes" }`
- SaaS `room_booking.status` adds `RELEASED` with `release_reason = NO_SHOW`, `released_at`; `updated_at` changes so incremental loaders pick it up.

### 5.3 Processor / live state
- Per env area: `temp`, `delta_15m` (from a 15-min ring buffer of readings), `co2`, `mode`, `setpoint`, `light_level`, `last_action`.
- ESG rollups (today, per floor and building): kWh, baseline kWh, saved %, CO₂e, ₹, comfort %.
- Live frame (`live-streaming.md` §4) adds:
  - `areas: { "<area_id>": [temp, delta_15m, co2, mode, light_level, setpoint] }` (replaces `zones`)
  - `esg: { kwh, saved_pct, saved_kwh, co2e_kg, cost_inr, comfort_pct }`
  - `automation`: last N actions with `reason`

### 5.4 Warehouse
- `FACT_ENERGY_15MIN` (area × interval: kWh by end use, baseline, comfort minutes) from `ENERGY_INTERVAL`.
- `FACT_AUTOMATION_EVENT` gains `reason`, `area_type`, `booking_id`.
- `MART_ESG_DAILY` (floor/building × day: kWh, baseline, saved %, CO₂e, ₹, comfort %, actions by rule, bookings released, hours reclaimed).
- `MART_BOOKING_EFFECTIVENESS` counts `RELEASED` bookings and reclaimed room-hours.

---

## 6. KPIs (pitch set)

| KPI | Definition |
|---|---|
| Energy saved % | (baseline − actual) / baseline, today |
| Energy used | Σ kWh today |
| CO₂e avoided | saved kWh × grid factor |
| Cost saved | saved kWh × tariff |
| Comfort compliance | comfort-ok occupied minutes / occupied minutes |
| Warm spots | areas occupied and ≥ 25.5 °C now |
| Room-hours reclaimed | Σ remaining duration of released bookings |
| Automation actions | count by rule today |
