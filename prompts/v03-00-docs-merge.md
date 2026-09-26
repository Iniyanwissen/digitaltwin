# v0.3 · Step 1 — Merge the design and data amendments into the docs

_(Run `/clear` before pasting. Use plan mode.)_

Read `CLAUDE.md`, `docs/floor-twin-design-v2.md`, `docs/environment-and-esg.md`, and `config/esg-additions.yaml`. Skim `design/floor-plan-v2.json`.

Update the existing docs so they stay the single source of truth. **Change docs and config only — no code.**
1. `docs/visualization-spec.md`: replace §2 tokens with the light/dark table from `floor-twin-design-v2.md` §2; point §5 (twin) to the v2 doc; add the temperature trend and warm-spot indicators; KPI strip limit of 5.
2. `docs/data-model.md`: apply `environment-and-esg.md` §5.1 and §5.4 (metres, facade, area_m2, FOCUS_BOOTH, floor_core, env_area, room env sensors, FACT_ENERGY_15MIN, MART_ESG_DAILY, released bookings).
3. `docs/event-model.md`: apply §5.2 (ENVIRONMENT_READING fields, new AUTOMATION_ACTION actions + `reason`, ENERGY_INTERVAL, booking `RELEASED`).
4. `docs/simulation-engine.md`: replace the environment/BMS sections with a pointer to `environment-and-esg.md` §2–4 and note that physics uses truth while rules use observed data.
5. `docs/live-streaming.md` §4: `areas` replaces `zones`; add `esg`; automation entries carry `reason`.
6. Merge `config/esg-additions.yaml` into `config/simulation.yaml` (replace `environment` and `bms`, add `energy`, add `layout.floor_plan_file` and `floor_overrides`). Update the Pydantic config schema description in the plan if needed.
7. `docs/implementation-plan.md`: add a "v0.3 increment" section listing steps 2–5 of `prompts/README.md` with acceptance criteria copied from those prompts.
8. `docs/decision-log.md`: add D-16 light default theme, D-17 real floor plan in metres, D-18 per-area environment (zones + rooms), D-19 shadow baseline for energy savings, D-20 prototype automation scope (HVAC, lighting, rooms).

List any contradictions you had to resolve, then stop.
