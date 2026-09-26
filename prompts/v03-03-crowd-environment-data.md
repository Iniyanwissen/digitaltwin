# v0.3 · Step 4 — Crowd-driven environment data

_(Run `/clear` before pasting. Use plan mode.)_

Read `CLAUDE.md` and `docs/environment-and-esg.md` §1–3 and §5. Config is in `config/simulation.yaml` (`environment`, `energy`).

**Engine (and `reference/refsim`, so the oracle stays in sync)**
- Environment areas = every zone + every room/common area; each gets an environment sensor.
- Per tick: crowd load from ground-truth people per area, solar gain by facade and hour, first-order temperature response to the mode setpoint, CO₂ mass balance with ventilation by mode/boost, lighting level and lux (formulas in §2). Keep the dedicated `environment` RNG stream.
- `ENVIRONMENT_READING` per area with the new fields (`setpoint_c`, `hvac_mode`, `ventilation_boost`, `light_level_pct`).
- `ENERGY_INTERVAL` per area every 15 sim-minutes with HVAC/lighting kWh, shadow-baseline kWh, occupied and comfort-ok minutes (§3).
- Existing HVAC rules keep working per area (rules still read observed data only).

**Processor / API**
- Per-area live state incl. `delta_15m` from a ring buffer; ESG rollups (today per floor/building).
- Live frame: `areas` (replaces `zones`) and `esg` per `environment-and-esg.md` §5.3. Snapshot and replay (`sim.floor_snapshot`) include areas.

**Data**
- Regenerate `mock-data/` (master + one weekday) and `mock-data/samples/` including `ENERGY_INTERVAL`.
- Update `docs/mock-data.md` counts.

**Tests (add to both reference and services)**
- Crowding: a room at 125% load for 15 sim-minutes ends ≥ 1.0 °C above setpoint and CO₂ > 1,000 ppm (with automation disabled).
- Empty area converges to its mode setpoint; ECO area drifts up, never below.
- `delta_15m` sign matches the recent readings.
- Energy: automation disabled ⇒ actual ≈ baseline (±2%); kWh non-negative; comfort minutes ≤ occupied minutes.
- Live and batch still produce the same identity/occupancy events (existing test).

Report against the list, then stop.
