# Implementation Plan

> Status: DRAFT v0.1. Related: all docs in `docs/`
> Phases follow SPEC §43 as adjusted by §51.12. Phase 8 is split into 8A/8B, data quality becomes Phase 9, and later phases shift by one.

---

## 1. Working Agreement

For every phase:

1. **Plan:** Claude Code proposes the task breakdown, files to touch, and any deviations from the docs. It waits for approval.
2. **Implement** in small commits.
3. **Verify:** run all tests and linters, then run the acceptance checks for the phase.
4. **Document:** update the relevant `docs/` files if decisions changed. Append to `docs/decision-log.md`.
5. **Summarize:** what was built, how to run it, known gaps.
6. Commit, tag (`phase-N`), then `/clear` before the next phase.

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

### Tooling decisions
- Python 3.12, `uv` for dependency management, one `pyproject.toml` per service plus `packages/domain`.
- Node 20, `npm`, Vite, TypeScript strict mode.
- `Makefile` targets: `up`, `down`, `test`, `lint`, `fmt`, `migrate`, `seed`, `generate-history`, `dbt-build`, `reset`.

---

## 2. Phase Overview

| Phase | Name | Outcome |
|---|---|---|
| 1 | Foundation | Skeleton services running in Docker, UI shell with navigation |
| 2 | Master data | Office hierarchy and synthetic employees generated from config |
| 3 | Simulation core | Clock, scheduler, planner, person state machines, ground truth, control panel |
| 4 | Identity events + processing | Access and workstation events flow through Redis to current state and raw archive |
| 5 | Occupancy sensors + SaaS | Desk/room sensors, heartbeats, mock SaaS with bookings |
| 6 | Live dashboard | Overview KPIs, live workplace, building view, live event viewer |
| 7 | Floor Digital Twin | SVG floor plans with live desk/room states |
| 8A | Historical generation + warehouse core | Batch mode, loaders, dbt RAW → CORE on DuckDB |
| 8B | Analytics marts + UI | Marts, real-estate analytics, heat maps, pipeline and sources pages |
| 9 | Data quality | Anomalies enabled, DQ marts, sensor accuracy |
| 10 | Snowflake | Snowflake adapters, dbt-snowflake target |
| 11 | Azure | Event Hubs and ADLS adapters, IaC |
| 12 | Scenarios + capacity planning | Special events, visitors, scenario simulator |
| 13 | Environment + HVAC automation | Environment physics, env sensors, BMS rules, environmental monitoring |

The MVP is Phases 1–7: a fully local, live, event-driven workplace simulation with a digital twin.

---

## 3. Phases

### Phase 1: Foundation

**Scope**
- Repository structure per `architecture.md` §10.
- `packages/domain` skeleton:
  - config schema (Pydantic) and loader
  - enums
  - adapter Protocols (empty implementations allowed)
  - event envelope model
- PostgreSQL with two databases (`workplace`, `workplace_saas`) and Alembic set up for `workplace` (empty baseline migration).
- `api` service: FastAPI app factory, settings from env, structured logging, `/health` (checks postgres and redis), `/api/v1/meta` (version, config summary).
- `simulation-engine` and `event-processor` services: runnable skeletons with `/health` (engine) and a heartbeat log line (processor).
- `frontend`:
  - Vite + React + TS + Tailwind
  - app shell with sidebar navigation for all SPEC §39 sections (placeholder pages)
  - typed API client
  - health indicator in the header
- `docker-compose.yml`: postgres, redis, api, simulation-engine, event-processor, frontend. Plus `.env.example` and `Makefile`.
- CI config (GitHub Actions or equivalent): lint + test.

**Acceptance criteria**
- `docker compose up` → UI at `localhost:5173` shows navigation and a green health indicator.
- `GET /health` reports postgres and redis status.
- `make test` and `make lint` pass in all packages.
- Invalid `simulation.yaml` causes the API and engine to fail fast with a readable validation error.

**Out of scope:** any data generation.

---

### Phase 2: Office Master Data and Synthetic Employees

**Scope**
- `config/layouts/building_a.yaml` (1 building, 4 floors, medium scale), plus `LayoutGenerator` for small/medium/large presets.
- Alembic migrations for `master`, `config`, `sim`, `ops` schemas (`data-model.md` §2).
- Generators:
  - `LayoutLoader`, `SensorGenerator`, `OrgGenerator`, `EmployeeGenerator`, `WorkPatternGenerator`, `AssignmentGenerator`
  - `RngFactory` (named seeded streams)
- CLI / Make target `seed`: generate master data for the active config and seed.
- API read endpoints:
  - buildings, floors (with layout geometry), zones, workspaces, rooms, sensors
  - teams, departments, employees (paginated, filterable)
- UI pages: Employees, Teams, Rooms, Workspaces (tables with filters). The Building View shows static capacity per floor.

**Acceptance criteria**
- Generating twice with the same seed and config produces identical master data (content hash test).
- Counts match config (employees, desks, rooms, sensors) for all three presets.
- Work mode and profile mixes are within ±2% of config for medium scale.
- Every team has a home floor and zone allocations summing to 1.0.
- Every desk with `has_sensor` has exactly one desk sensor; every room/common area has one count sensor; every zone has one environment sensor.

---

### Phase 3: Simulation Clock and Employee State Machine

**Scope**
- `ScaledRealtimeClock`, `VirtualClock`, scheduler with lazy cancellation and priorities.
- Day planner:
  - calendar and leave (leave stored in memory until Phase 5)
  - team-correlated attendance with calibration
  - arrival/departure per profile
  - MeetingScheduler (room booking in memory until Phase 5)
- Person state machines, activity model, lunch and meeting constraints.
- Desk assignment engine (assigned and hot-desk, overflow).
- Truth events (`TRUTH_STATE_TRANSITION`, `TRUTH_DESK_SEARCH_FAILED`) to an in-memory sink, plus a debug JSONL dump.
- Control channel via Redis pub/sub: START, PAUSE, RESUME, STOP, RESET, SET_SPEED. Status snapshots.
- `simulation_run` tracking in PostgreSQL.
- UI Simulation Control panel: status, sim date/time, speed selector, buttons, engine-side counters (labeled "simulation truth").

**Acceptance criteria**
- Invariant tests pass for a full simulated day at small scale (`simulation-engine.md` §14).
- Calibration tests pass at medium scale (attendance ±3 pp, arrival curve shape, meetings per person ±10%, team correlation higher than random pairs).
- Two batch runs of the same day with the same seed produce identical truth content hashes.
- From the UI:
  - start at 60x and watch the "people inside" counter rise through the morning and fall in the evening
  - pause/resume/speed change work without time jumps
  - reset clears state
- One medium-scale day in batch mode completes in < 30 s.

**Out of scope:** observable (non-truth) events.

---

### Phase 4: Access-Card and Workspace-Login Events

**Scope**
- Event envelope finalized, with the payload registry and identity lookup table (`event-model.md`).
- AccessControlObserver and WorkstationObserver, including realism rules (tailgate, missed badge-out, logout reasons, no-login).
- Delivery layer: AnomalyInjector (implemented, all probabilities 0), LiveSink, InMemorySink.
- `RedisStreamPublisher` / `RedisStreamConsumer`.
- Event processor:
  - validation and deadletter
  - dedupe
  - person and desk-login state
  - building inside set and counters
  - raw archive (`LocalFileRawArchive` with manifests)
  - source metrics
  - live pub/sub feed
- API endpoints: current people inside (identity-aware), desk logins, source metrics.

**Acceptance criteria**
- Contract tests: every emitted event validates against its payload schema.
- Privacy test: identity fields exist only on IDENTIFIED events.
- For a simulated day at 60x: Redis `inside_count` tracks the engine's true count within the gap explained by tailgating/missed badge-outs. The report shows both numbers.
- Raw archive files follow the partition layout, and manifests match row counts.
- Killing and restarting the event processor mid-run resumes from the consumer group with no lost or double-applied state.

---

### Phase 5: Desk/Room Occupancy Sensors and Mock SaaS

**Scope**
- DeskSensorObserver (debounce, hold time, flicker, false positives) and RoomSensorObserver (count lag, noise), for rooms and common areas.
- Heartbeats, gateway `SENSOR_STATUS_CHANGED` (failure mechanism present, probability 0).
- Processor state for desks (sensor), rooms, floors (`est_headcount`), sensors.
- `mock-saas` service:
  - own DB migrations
  - read APIs with `updated_since` + pagination
  - write APIs
  - optional simulated rate-limit headers and transient errors
- The engine writes bookings and leave records to mock-saas via `SaasClient`.
- Docker Compose adds `mock-saas`.

**Acceptance criteria**
- The SPEC §48 end-to-end flow is reproduced by a scripted scenario test. Observed event sequence and state match `event-model.md` §11 (timings within configured lag distributions).
- Current state shows desks that are "logged in + vacant" during meetings. The count is non-zero during meeting peaks.
- No anonymous event or state key links a room count change to an employee (privacy test extended to state).
- `GET /v1/room-bookings?updated_since=...` returns the day's bookings with stable pagination.

---

### Phase 6: Live Dashboard and Event Stream

**Scope**
- API WebSocket `/ws/live`: throttled event batches and state deltas, subscription filters.
- Processor: today's rolling series per building and floor (sim-minute resolution).
- UI:
  - **Overview**: SPEC §24 KPIs that are available so far (employees inside, occupied/available desks, desk/room/building utilization %, peak today), plus occupancy-over-time, floor utilization, team distribution (today)
  - **Live Workplace**: floor cards with live counts
  - **Building View**: floor utilization bars, click-through placeholder to the twin
  - **Live Events**: streaming table with filters (event type, employee, floor, workspace, sensor), pause/auto-scroll, rate indicator
  - **Simulation Control**: integrated live counters

**Acceptance criteria**
- At 60x with medium scale, the UI stays responsive (no dropped frames beyond minor, WebSocket backlog bounded). The event rate indicator shows the actual flow.
- KPI values in the UI equal the API/Redis values (automated API-level test, plus a manual check).
- Filters work on live and buffered events.
- All utilization calculations come from the API. The frontend only formats.

---

### Phase 7: Floor Digital Twin

**Scope**
- SVG floor renderer driven by the layout from the API: zones, desks, rooms, cabins, common areas, entrances.
- Desk visual states:
  - `VACANT`, `OCCUPIED` (sensor)
  - `RESERVED` (logged in + vacant, shown as a distinct "held" style)
  - `UNAVAILABLE`
- Rooms show count / capacity.
- Click panel for a desk: workspace ID, zone, sensor status, logged-in employee (**only from login state**), last occupancy event, utilization today (from rolling state).
- Click panel for a room: count, capacity, current booking (from SaaS via API), today's usage.
- "Current occupancy" heat map mode (historical modes come in 8B).
- Building View → floor click-through.

**Acceptance criteria**
- Renders a 250-desk floor with live updates at 60x without visible lag.
- A test asserts that the desk detail endpoint returns an employee only when a login session exists, and never derives one from sensor state.
- Layout changes in YAML (after re-seeding) are reflected in the twin with no frontend code changes.

**Milestone: MVP complete.**

---

### Phase 8A: Historical Generation and Warehouse Core

**Scope**
- Engine BATCH mode:
  - `GENERATE_HISTORY` command
  - parallel day workers
  - BatchSink writing the raw archive layout
  - coarser environment interval, heartbeats off
- `pipeline-runner` service:
  - archive loader (manifest watermark)
  - PostgreSQL master snapshot loader
  - SaaS incremental loader
  - DuckDB build + atomic swap
  - `ops.pipeline_run` and layer counts
- dbt project (dbt-duckdb):
  - RAW sources
  - STAGING models
  - CORE dims (SCD2 snapshots) and facts, including interval facts and `FACT_SPACE_UTILIZATION_15MIN`
  - dbt tests
- Cross-dialect macros prepared for Snowflake (JSON access, date functions).

**Acceptance criteria**
- `make generate-history DAYS=30` completes, and the pipeline builds CORE successfully.
- 365 medium-scale days complete in < 30 min (generation) plus a reasonable pipeline time (target < 15 min on DuckDB).
- dbt tests pass (uniqueness, not-null, relationships, accepted values).
- Reconciliation tests:
  - RAW distinct events = STAGING rows (no anomalies)
  - interval facts close all sessions at day end
  - `FACT_SPACE_UTILIZATION_15MIN` totals equal `FACT_OCCUPANCY` durations
- Re-running the pipeline without new files adds zero rows (idempotency).

---

### Phase 8B: Analytics Marts and UI

**Scope**
- All marts from `data-model.md` §5.4, except the DQ and sensor-accuracy marts (Phase 9). Metric macros match the domain metric definitions.
- `config/recommendations.yaml` and `MART_RECOMMENDATIONS`.
- `DuckDbWarehouseRepository` and API analytics endpoints.
- UI:
  - **Historical Analytics**: attendance trends, peak trend, hourly patterns
  - **Real Estate Analytics**: SPEC §28 metrics and rule-based observations with supporting values
  - **Teams**: team distribution by floor (bars + heat map)
  - **Rooms**: utilization, right-sizing, booking effectiveness
  - **Heat maps**: Today / 7-day / 30-day modes on the twin
  - **Data Pipeline**: lineage view with live record counts per layer
  - **Data Sources**: status, events received, last event, records processed, failures, latency

**Acceptance criteria**
- Metric parity test: domain metric functions and dbt marts give identical results on a fixture dataset.
- With 90 days of history, Real Estate Analytics shows at least one triggered and one non-triggered rule, each with its metric values.
- Heat maps in 7D/30D modes match the corresponding `MART_HEATMAP` values.
- The Data Pipeline page shows counts moving after a live micro-batch.

---

### Phase 9: Data Quality Scenarios

**Scope**
- Enable anomaly configuration: duplicates, late, out-of-order, missing, sensor failures, partial env nulls.
- Staging DQ handling and `STAGING.DQ_EVENT_QUALITY`.
- Processor behavior under anomalies (event-time guards) verified.
- `MART_DATA_QUALITY` and `MART_SENSOR_ACCURACY` (vs `FACT_GROUND_TRUTH_ACTIVITY`).
- UI: data quality panel on the Data Sources page, and a Simulation Debug view (truth vs observed for a selected desk or room, clearly labeled).

**Acceptance criteria**
- With anomalies enabled, the reported rates in `MART_DATA_QUALITY` are within tolerance of the configured probabilities.
- Duplicates never inflate facts (reconciliation test with anomalies on).
- Late events never regress current state (processor property test).
- The sensor accuracy mart reports precision/recall and detection lag consistent with observer config.

---

### Phase 10: Snowflake Integration

**Scope**
- `SnowflakeLoader`: stage from local files first (PUT + COPY INTO); ADLS external stage after Phase 11.
- dbt-snowflake target using the same models.
- `SnowflakeWarehouseRepository`.
- Setup SQL: database, schemas, roles, warehouse (script, no hardcoded credentials, key-pair auth via env).

**Acceptance criteria**
- Switching `WAREHOUSE=snowflake` requires no code changes outside adapters and dbt profiles.
- On a fixed 7-day dataset, every mart has identical row counts and matching aggregates (within rounding) on DuckDB and Snowflake.

---

### Phase 11: Azure Event Hubs and ADLS

**Scope**
- `AzureEventHubPublisher`, `AzureEventHubConsumer` (Blob checkpointing).
- `AdlsRawArchive`.
- Snowflake external stage on ADLS.
- IaC (Bicep or Terraform) for:
  - Event Hubs namespace + hubs
  - storage account with `raw` container
  - managed identity / connection settings
- Docs for setup and teardown.

**Acceptance criteria**
- Switching `EVENT_BUS=eventhubs` and `RAW_ARCHIVE=adls` runs a live simulation end to end with the same UI behavior. Engine and processor business logic are unchanged.
- The same seed produces the same raw content in ADLS as locally (content-hash comparison on one day).

---

### Phase 12: Scenario Simulator and Capacity Planning

**Scope**
- Admin UI for special events and visitor registrations (API → mock SaaS).
- Engine planner integration: visitor persons, attendance uplift, reserved rooms, unavailable desks.
- **Scenario Simulator (Mode 1)**: deterministic calculation. Inputs are SPEC §3 fields; the calculation uses historical marts (floor peaks, team attendance by weekday). Outputs:
  - building and floor projected occupancy
  - desk shortage/surplus
  - room sufficiency
  - spare capacity by floor
  - temporary space suggestions (rule-based)
- **Capacity Planning** page: scenario comparison and saved scenarios.
- Optional **Mode 2**: run an actual batch simulation for the scenario date and compare with Mode 1.

**Acceptance criteria**
- The SPEC §3 example (800 capacity, 620 employees + 150 guests) produces a correct, explained result with the floor breakdown.
- A created special event appears in the next simulated day: visitors badge in, reserved rooms are blocked, and occupancy rises accordingly.

---

### Phase 13: Environmental Sensors and HVAC Automation

**Scope**
- Environment physics model and EnvironmentSensorObserver.
- BMS with `ObservedStateView`, rules from `config/automation_rules.yaml`, hysteresis and cooldowns.
- `AUTOMATION_ACTION` events, HVAC state in Redis, `FACT_ENVIRONMENT`, `FACT_AUTOMATION_EVENT`, `MART_ENVIRONMENT_HOURLY`.
- UI:
  - **Environmental Monitoring**: zone metrics, temperature by zone, occupancy vs temperature
  - automation log
  - HVAC mode overlay on the twin

**Acceptance criteria**
- Temperature series are smooth: tick-to-tick change is ≤ configured max; no jumps.
- An empty zone switches to ECO after 15 simulated minutes and back when occupied, with no flapping (cooldown respected).
- A test proves the BMS cannot access ground truth (type-level: `ObservedStateView` only).
- CO2 rises with occupancy and falls under increased ventilation.

---

## 4. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Python DES too slow at large scale | per-day parallelism in batch; vectorized environment ticks; profile early in Phase 3; large scale is a stretch goal |
| UI overwhelmed at 60x | server-side throttling and aggregation; WebSocket sends deltas, not full state; event viewer caps its buffer |
| DuckDB locking between API and pipeline | build-and-swap file strategy (`architecture.md` §8.3) |
| Scope creep in later phases | MVP boundary at Phase 7; non-goals in SPEC §51.13 |
| Unrealistic-looking data | calibration tests in Phase 3; visual review checkpoints at the end of Phases 6 and 8B |
| Identity leakage through correlation | envelope validator, privacy tests on events and state, no correlation IDs on anonymous events |

---

## 5. Open Questions (to confirm before or during Phase 1)

1. Default timezone `Asia/Kolkata`? (affects calendar and core hours)
2. v1 layout: one building with 4 floors at medium scale. Is a second building needed early?
3. Hand-written `building_a.yaml` layout or generated from presets only?
4. Frontend component library: plain Tailwind, or Tailwind + shadcn/ui?
5. Should historical generation be allowed while a live run is active? (current design: one active run at a time)
6. Do you have Snowflake and Azure accounts available (trial/free tier) for Phases 10–11, or should those stay adapter-only for now?
7. Weekend attendance: keep the small default (1–3%), or zero?
8. CI platform: GitHub Actions?
