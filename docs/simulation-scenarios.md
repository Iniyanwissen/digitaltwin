# Simulation Scenarios

> Status: DRAFT v0.2. Implemented in Phase 10 (S6/S7 in Phase 9). Related: `simulation-engine.md`, `visualization-spec.md`

All scenarios reuse the same engine. A scenario is a **config overlay + optional injected events**, run in BATCH mode (or LIVE for demos), stored as a `simulation_run` with `mode = SCENARIO`, `scenario_type`, the overlay, the seed, and a `baseline_run_id`. Comparisons are always scenario vs baseline with the **same seed and date range**, so differences come from the change, not from randomness.

```
scenario request (UI) → API validates overlay → engine runs baseline (cached) + scenario
                      → pipeline builds marts for both run IDs → comparison endpoint → UI
```

Common result shape:

```json
{
  "scenario_id": "…", "type": "TEAM_MOVE", "baseline_run_id": "…", "scenario_run_id": "…",
  "inputs": { … },
  "metrics": [ { "name": "floor_peak_util_pct", "scope": "BLD01_F03", "baseline": 71.2, "scenario": 88.4, "delta": 17.2 } ],
  "observations": [ { "rule_id": "FLOOR_OVER_90", "text": "Floor 3 exceeds 90% desk utilisation on Tue–Thu.", "values": { … } } ]
}
```

---

## S1. Special Event Capacity (SPEC §3, §21)

**Inputs:** date, start/end, expected employees, guests, floors available, rooms reserved, desks unavailable.

**Mode 1 (deterministic, instant):**
1. Baseline for that weekday from history: P50 and P90 building/floor peak, room demand by hour (`MART_PEAK_OCCUPANCY`, `MART_FLOOR_UTILIZATION`).
2. Projected occupancy = max(expected employees, P90 weekday attendance) + guests during the event window.
3. Allocate guests to the event space (auditorium / reserved rooms) first, overflow to common areas; employees to their home floors using team distribution.
4. Output per floor: projected occupancy, desk shortage/surplus, room sufficiency, spare capacity, building utilisation vs `max_occupancy`; rule-based suggestions (e.g. "open Floor 4 collaboration area as overflow").

**Mode 2 (simulated):** create a `special_event` in mock SaaS, run the day in batch with visitors injected (visitor persons: badge arrival around start, event space, common areas, leave after end), compare against Mode 1.

**UI:** Scenario Simulator form → H7 bullet charts per floor + observations; "Run full simulation" button for Mode 2.

---

## S2. What-if Team Move

**Inputs:** team(s), target floor/zone, date range (default: last 4 weeks replayed).

**Algorithm:** overlay changes `team.home_floor_id` and `team_zone_allocation`; rerun with the same seed.

**Outputs:** floor utilisation before/after, desk shortages, meeting travel (cross-floor meeting share from `MART_TEAM_COLLAB_NETWORK`), floor-lobby reader passes (from `AREA_ACCESS`) as a movement proxy.

**UI entry points:** Teams → N2 scatter (click a relocation candidate) or Scenario Simulator form.

---

## S3. Hot-desk Policy Test

**Inputs:** floor(s), policy (`ASSIGNED` ↔ `HOT_DESK`), optional desk reduction % (simulate removing desks).

**Algorithm:** overlay `floor.desk_policy` and/or mark N% desks `UNAVAILABLE`; rerun.

**Outputs:** `TRUTH_DESK_SEARCH_FAILED` count (desk shortages), overflow-area usage, peak desk utilisation, desks-per-employee ratio, share of people seated off their home floor.

**Typical question answered:** "Can we remove 20% of Floor 2 desks if we switch it to hot-desking?"

---

## S4. Evacuation Drill

**Inputs:** date and time of alarm, floors affected, exit capacity (people/minute per exit, config), pre-movement delay distribution.

**Algorithm:**
1. Take the ground-truth state at the alarm time (from a live run or by simulating the day up to that time).
2. Switch all persons to `EVACUATING`: pre-movement delay (log-normal, median 60 s), walk time to the nearest exit from their location (layout distance / walking speed 1.2 m/s; layout units → metres via config), queueing at exits (capacity per minute).
3. Emit truth transitions only (no badge-outs during evacuation, which is realistic) plus a synthetic `ACCESS_OUT` sweep flagged `EVACUATION`.

**Outputs:** time to clear per floor, P95 clearance, exit queue peaks, people unaccounted for by badge data (inside per badge vs truth) — shows why badge data alone is unreliable for mustering.

**UI:** twin in Simulation View replays the evacuation; per-floor clearance curve.

---

## S5. Energy Savings (BMS A/B)

**Inputs:** date range, rule set A (baseline rules) vs rule set B (e.g. BMS off, or tighter ECO threshold).

**Algorithm:** same seed, same people; only `automation_rules` differ. Energy proxy per zone-minute: HVAC mode weight (ECO 0.4, NORMAL 1.0, HIGH 1.4) × (1 + ventilation boost 0.2) — weights in config.

**Outputs:** energy proxy saved %, comfort violations (minutes with temperature > 25.5 °C or CO2 > 1,000 ppm while occupied), number of automation actions.

**UI:** H3 side-by-side for A and B; summary cards.

---

## S6. Data-quality Chaos (Phase 9)

**Inputs:** anomaly probabilities (duplicates, late, out-of-order, missing, sensor failure rate/duration).

**Outputs:** `MART_DATA_QUALITY` rates vs configured, dedupe effectiveness, late-event impact on current state (should be none), dashboards with sensor gaps.

---

## S7. Sensor Accuracy (Phase 9)

**Inputs:** detection delay, vacancy timeout, count noise, coverage %.

**Outputs:** `MART_SENSOR_ACCURACY` precision/recall and lag vs ground truth; how utilisation KPIs shift with sensor settings (e.g. a 10-minute vacancy timeout inflates desk utilisation).

---

## Run tracking additions (`sim.simulation_run`)

```
scenario_type        text        -- NULL | SPECIAL_EVENT | TEAM_MOVE | DESK_POLICY | EVACUATION | ENERGY_AB | DQ_CHAOS | SENSOR_ACCURACY
scenario_overlay     jsonb
baseline_run_id      uuid
```

Baseline runs are cached by `(config content hash, seed, date range)` and reused across scenarios.
