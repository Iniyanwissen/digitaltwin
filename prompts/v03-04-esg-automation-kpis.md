# v0.3 · Step 5 — ESG automation, KPIs and panels

_(Run `/clear` before pasting. Use plan mode.)_

Read `CLAUDE.md` and `docs/environment-and-esg.md` §3–6. Visual reference: `design/floor-twin-design.html` (sustainability panel, automation log, lighting/HVAC layers).

**Engine / BMS**
- Implement the rule table in §4 in order, with per-area cooldowns and at most one HVAC and one lighting action per area per tick. Every action emits `AUTOMATION_ACTION` with `reason`.
- Meeting rooms: `RELEASE_GHOST_BOOKING` updates the SaaS booking (`status = RELEASED`, `release_reason = NO_SHOW`, `released_at`) through `SaasClient`, then lights off + ECO. `PRECOOL_FOR_BOOKING` reads upcoming bookings from SaaS (observed system data). Advisory flags (oversized, over capacity) change nothing physical except the vent boost.
- Automation effects feed back into the physics (setpoint, ventilation, light level), so the demo loop closes: crowd → warm ▲ → action → ▼.
- Config switch `bms.enabled` (default true) for the shadow baseline check and scenario S5.

**Frontend**
- Sustainability panel (hero energy saved %, kWh, CO₂e, ₹, comfort %) and automation log (last 4, tag + what + why), per the reference.
- Lighting and HVAC layers use the live `areas` data; room chips show *Released* / *Over* / *Too big* / *Booked*.

**Warehouse**
- `FACT_ENERGY_15MIN`, `MART_ESG_DAILY`, `FACT_AUTOMATION_EVENT.reason`, released bookings in `MART_BOOKING_EFFECTIVENESS`; a simple ESG section on Historical Analytics (daily saved kWh and CO₂e trend).

**Acceptance**
- 60× demo on a weekday: at least one auto-release, one pre-cool, one vent boost, one daylight dim and one eco action appear by 11:30 sim-time on Floor 2.
- Saved % is between 10% and 35% for a typical weekday with defaults (report the value); comfort compliance ≥ 90%.
- Rules never read ground truth (test: feed a fake truth that contradicts sensors → rules follow sensors).
- Released bookings visible in SaaS API (`updated_since`) and in the booking-effectiveness mart.

Report against the list (with the numbers), then stop.
