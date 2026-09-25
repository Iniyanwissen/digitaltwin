# Implementation Plan

> Status: DRAFT v0.2. Related: all docs in `docs/`
> v0.2 changes: **everything local first** (cloud phases deferred to `cloud-migration.md`), a Phase 0 cleanup of previously generated code, porting from the working reference simulator (`reference/refsim`), and the new visualisation and scenario work.

---

## 1. Working Agreement

For every phase:

1. **Plan:** Claude Code proposes the task breakdown, files to touch, and any deviations from the docs. It waits for approval.
2. **Implement** in small commits.
3. **Verify:** run all tests and linters, then run the acceptance checks for the phase.
4. **Document:** update the relevant `docs/` files if decisions changed. Append to `docs/decision-log.md`.
5. **Summarize:** what was built, how to run it, known gaps.
6. Commit, tag (`phase-N`), then `/clear` before the next phase.

Prompts for each step are in `prompts/`; the `/phase N` slash command (`.claude/commands/phase.md`) runs the same workflow.

### Global Definition of Done (applies to every phase)

- `docker compose up` starts all services for that phase with no errors and no cloud credentials.
- `make test` and `make lint` pass. Tools:
  - Python: ruff, mypy (strict on `packages/domain` and `simulation-engine`), pytest
  - Frontend: eslint, tsc, vitest
- No hardcoded counts, layouts, credentials, or magic numbers in business logic. All come from config.
- No random calls outside `RngFactory` (enforced by a lint rule / grep check in CI).
- No business logic in React components or FastAPI route handlers.
- New config keys are documented in `config/*.yaml` with comments.
- The app is runnable and demonstrable at the end of the phase.
- Reference tests (`reference/tests`) that apply to the ported code are ported into the service test suites and pass.

### Tooling decisions
- Python 3.12, `uv` for dependency management, one `pyproject.toml` per service plus `packages/domain`.
- Node 20, `npm`, Vite, TypeScript strict mode.
- `Makefile` targets: `up`, `down`, `test`, `lint`, `fmt`, `migrate`, `seed`, `generate-history`, `dbt-build`, `reset`.

---

## 2. Phase Overview

| Phase | Name | Outcome |
|---|---|---|
| 0 | Cleanup and alignment | Previously generated schema/views audited, removed or remapped; repo matches `architecture.md` |
| 1 | Foundation | Skeleton services in Docker, UI shell with navigation and design tokens |
| 2 | Master data | Layout + synthetic organisation generated from config (ported from reference) |
| 3 | Simulation core | Clock, scheduler, planner, person state machines, desk assignment, meetings, control panel |
| 4 | Identity events + processing | Access (entrance, floors, secure zones, room doors), room check-in, workstation → Redis → current state + raw archive |
| 5 | Sensors, environment, SaaS | Desk/room sensors, environment physics, BMS automation, mock SaaS bookings/leave |
| 6 | Live dashboard | Overview KPIs, live workplace, building view, live events, environmental monitoring |
| 7 | Digital twin visuals | 2D floor twin, isometric building, Simulation View dots, time scrubber |
| 8A | History + warehouse core | Batch generation, loaders, dbt RAW → CORE on DuckDB |
| 8B | Analytics UI | Marts, hybrid charts, heat maps, network graphs, movement flow, pipeline + sources pages |
| 9 | Data quality + realism | Anomalies, sensor faults, walk-ins, DQ and sensor-accuracy marts |
| 10 | Scenario simulations | Capacity/special events, what-if team moves, hot-desk policy, evacuation drill, energy savings |
| Deferred | Cloud | Azure Event Hubs, ADLS, Snowpipe, Snowflake Dynamic Tables (`cloud-migration.md`) |

**MVP = Phases 0–7**: a fully local, live, event-driven workplace simulation with a digital twin.

---

## 3. Phases

### Phase 0: Cleanup and Alignment
Follow `cleanup-guide.md` with prompts `00-cleanup-audit.md` → `01-cleanup-execute.md`.

**Acceptance criteria**
- `docs/cleanup-report.md` lists every pre-existing file/table/view with a KEEP / ADAPT / REPLACE / DELETE decision, approved by you before deletion.
- No leftover schema, migration, seed script, mock JSON or UI page that contradicts `data-model.md`, `event-model.md` or `visualization-spec.md`.
- No random/mock data generation remains in the frontend or API.
- Kept UI components are restyled to the tokens in `visualization-spec.md` §2.
- `docker compose up` still starts (even if pages are placeholders).

### Phase 1: Foundation
**Scope**
- Repo structure per `architecture.md` §10 (including `reference/`, `mock-data/`, `prompts/`, `.claude/commands/`).
- `packages/domain`: config schema for `config/simulation.yaml` (Pydantic, fail fast), enums, adapter Protocols, event envelope + identity table.
- PostgreSQL (`workplace`, `workplace_saas`), Alembic baseline.
- `api` (FastAPI factory, settings, structured logging, `/health`, `/api/v1/meta`); `simulation-engine` and `event-processor` skeletons.
- Frontend: Vite + React + TS + Tailwind, app shell with the SPEC §39 navigation, design tokens, typed API client, health indicator.
- Docker Compose (postgres, redis, api, simulation-engine, event-processor, frontend), `.env.example`, `Makefile`, CI.

**Acceptance criteria**
- `docker compose up` → UI shell at `localhost:5173` with green health indicator.
- `make test` / `make lint` pass. Invalid `simulation.yaml` fails fast with a readable error.

### Phase 2: Master Data
**Scope**
- Port `reference/refsim/layout.py` and `master.py` into `simulation-engine/engine/generators` (typed, Pydantic models, `RngFactory`).
- Alembic migrations for `master`, `config`, `sim`, `ops` (`data-model.md` §2, v0.2 fields: reader types, restricted zones, room readers/panels, device types, `floor_snapshot`).
- `make seed` loads generated master data into PostgreSQL. `mock-data/master/*.csv` must be reproducible byte-for-byte from the same config + seed.
- API read endpoints + UI pages: Employees, Teams, Rooms, Workspaces, Building View (static capacity).

**Acceptance criteria**
- Port of `test_master_data_is_deterministic` passes; counts match all three presets.
- Every restricted zone has a secure reader and at least one `zone_access_rule`.
- Generated CSVs equal `mock-data/master` for the default config.

### Phase 3: Simulation Core
**Scope**
- Port clock, scheduler, planner (calendar, leave, team-correlated attendance with weekday calibration), person state machine, activity model, desk assignment, meeting scheduler from `reference/refsim/engine.py`.
- Truth events to an in-memory/debug sink. Redis control channel (START/PAUSE/RESUME/STOP/RESET/SET_SPEED). `simulation_run` tracking.
- UI Simulation Control panel.

**Acceptance criteria**
- Ported tests pass: truth sequences, non-negative counts, reproducibility, calibration.
- 60x run from the UI: truth "inside" rises and falls over the day; pause/speed/reset work without time jumps.
- One medium day in batch mode < 30 s.

### Phase 4: Identity Events and Processing
**Scope**
- Access observer (entrance, floor lobby, secure zone, room door readers; tailgating, missed badge-out, internal badge compliance), room-panel check-in, workstation observer (logout reasons, no-login).
- Delivery layer (anomalies implemented, all 0), `RedisStreamPublisher`/`Consumer`.
- Event processor: validation/deadletter, dedupe, event-time guards, person/floor/desk-login state, raw archive with manifests, source metrics, live pub/sub. Logic mirrors `reference/refsim/state.py`.
- API: people inside, current floor per person (identity-aware, from readers), desk logins, source metrics.

**Acceptance criteria**
- Contract + privacy tests (port `test_anonymous_events_never_carry_identity`, `test_logins_only_after_arrival`).
- Raw archive layout and manifests match `mock-data/raw` structure.
- Processor restart resumes from the consumer group with no lost/double-applied state.

### Phase 5: Sensors, Environment, BMS and Mock SaaS
**Scope**
- Desk sensor (detection delay, vacancy hold), room/common-area count sensor (lag, noise), heartbeats.
- Environment physics and BMS rules (observed data only) — already in the reference, port them.
- `mock-saas` service + DB; engine writes bookings and leave via `SaasClient`.
- Processor state for desks, rooms, floors, env, HVAC.

**Acceptance criteria**
- SPEC §48 flow reproduced by a scripted test (`event-model.md` §11).
- "Logged in + vacant" desks non-zero during meeting peaks; port `test_sensor_lags_truth_and_login_persists_during_meetings`.
- Port `test_live_and_batch_produce_the_same_world`.
- `GET /v1/room-bookings?updated_since=…` paginates stably.

### Phase 6: Live Dashboard, Events and Environmental Monitoring
**Scope** (`visualization-spec.md` §4: Overview, Live Workplace, Building View, Live Events, Environmental Monitoring, Simulation Control)
- WebSocket `/ws/live` implementing the frame contract in `live-streaming.md` §4 (throttled deltas, resync).
- Processor rolling series (per sim-minute).
- Hybrid charts H1 (people vs desks vs capacity) and H3 (temperature vs occupancy with HVAC bands).

**Acceptance criteria**
- Medium scale at 60x: UI responsive, bounded WebSocket backlog, KPI parity with API/Redis (automated).
- Live Events filters work; identity class colour-coding present.
- Frontend performs no utilisation maths (only formatting).

### Phase 7: Digital Twin Visuals
**Scope** (`visualization-spec.md` §5)
- 2D floor twin (static layer cached, dynamic layer per frame), overlays (occupancy, temperature, HVAC, bookings), desk/room detail panels.
- Isometric building view with per-floor utilisation.
- Simulation View: truth dots on a Canvas/PixiJS layer with tweening, clearly labelled, toggleable.
- Time scrubber backed by `sim.floor_snapshot` (writer in the processor, one row per floor per sim-minute).

**Acceptance criteria**
- 250-desk floor with dots at 60x renders ≥ 50 fps on a laptop (dirty-flag rendering).
- Desk detail never shows an employee unless a workstation login exists (test).
- Scrubbing any minute of today restores desk/room/zone state within 200 ms.
- Operational View never renders truth data (test on the API: truth endpoints are separate and flagged).

**Milestone: MVP complete.**

### Phase 8A: Historical Generation and Warehouse Core
**Scope**
- Engine BATCH mode, `GENERATE_HISTORY`, parallel day workers, BatchSink.
- `pipeline-runner`: archive loader, PostgreSQL master snapshots, SaaS incremental loader, DuckDB build-and-swap, `ops` tables.
- dbt (dbt-duckdb): RAW sources, STAGING, CORE (incl. `FACT_AREA_ACCESS`, `FACT_ROOM_CHECK_IN`, interval facts, `FACT_SPACE_UTILIZATION_15MIN`), dbt tests.
- `mock-data/raw` must load as-is (it is the first fixture).

**Acceptance criteria**
- `make generate-history DAYS=30` + pipeline succeed; 365 medium days < 30 min generation.
- Reconciliation and idempotency tests as in v0.1.

### Phase 8B: Analytics UI
**Scope**
- All marts (`data-model.md` §5.4 v0.2) including network and flow marts.
- Pages: Historical Analytics, Real Estate Analytics (rule-based observations), Teams (distribution + collaboration network + co-location vs collaboration), Rooms (booked-vs-used Gantt), heat maps (Today / 7D / 30D), Data Pipeline, Data Sources.
- Hybrid charts H2, H4–H7 from `visualization-spec.md` §6.

**Acceptance criteria**
- Metric parity test (domain metrics vs dbt) passes.
- Network graph renders ≤ 150 team nodes smoothly; edges filterable by threshold.
- Ghost bookings visible in the room timeline and counted in `MART_BOOKING_EFFECTIVENESS`.

### Phase 9: Data Quality and Realism
**Scope**
- Enable anomalies (duplicates, late, out-of-order, missing, sensor failures, env nulls, `ACCESS_DENIED`), desk-sensor flicker/false positives, walk-in meetings, late joiners.
- `STAGING.DQ_EVENT_QUALITY`, `MART_DATA_QUALITY`, `MART_SENSOR_ACCURACY`; DQ panel; Simulation Debug (truth vs observed).

**Acceptance criteria**: as v0.1 Phase 9.

### Phase 10: Scenario Simulations
**Scope** (`simulation-scenarios.md`)
- S1 Special event capacity (admin UI → SaaS → planner; visitors, reserved rooms, unavailable desks) + Scenario Simulator Mode 1 (deterministic) and Mode 2 (batch sim).
- S2 What-if team move. S3 Hot-desk policy test. S4 Evacuation drill. S5 Energy savings (BMS on/off A/B).
- Capacity Planning page with saved and compared scenarios.

**Acceptance criteria**
- SPEC §3 example (800 capacity, 620 + 150) explained per floor.
- Every scenario is a tagged `simulation_run` (mode `SCENARIO`) with inputs stored, reproducible by seed, and comparable against a baseline run.

### Deferred: Cloud
See `cloud-migration.md`: C1 Event Hubs + ADLS adapters, C2 Snowpipe auto-ingest + dbt-snowflake, C3 Dynamic Tables for near-real-time marts. Entry criterion: MVP complete and local pipeline stable.

---

## 4. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Old generated code keeps leaking back in | Phase 0 report + `CLAUDE.md` rule: only files described in docs/ may exist |
| Python DES too slow at large scale | per-day parallelism; reference measured ~2 s/day at medium |
| UI overwhelmed at 60x | server-side throttling, deltas only, canvas layers, dirty-flag rendering |
| DuckDB locking | build-and-swap |
| Truth leaking into operational views | separate endpoints/channels for truth, UI labelling, API tests |
| Scope creep | MVP boundary at Phase 7; cloud deferred |

---

## 5. Open Questions (answer before Phase 1)

1. Default timezone `Asia/Kolkata`? (config default)
2. v1: one building, 4 floors, medium preset — OK?
3. Frontend component library: Tailwind only, or Tailwind + shadcn/ui? (spec assumes shadcn/ui primitives, restyled)
4. Keep weekend attendance at 2% of office-mode employees?
5. CI: GitHub Actions?
6. Which existing UI screens do you want to keep visually (Phase 0 decides structurally)?
