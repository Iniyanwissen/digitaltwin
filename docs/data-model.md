# Data Model

> Status: DRAFT v0.1. Related: `architecture.md`, `event-model.md`

Covers:
1. Identifier conventions
2. PostgreSQL operational database (`workplace`)
3. Mock SaaS database (`workplace_saas`)
4. Current state (Redis)
5. Warehouse layers: RAW, STAGING, CORE, MART (DuckDB locally, Snowflake in cloud)
6. Metric definitions

---

## 1. Identifier Conventions

IDs are human-readable, deterministic, and generated from the layout configuration and seed, so the same config always yields the same IDs.

| Entity | Pattern | Example |
|---|---|---|
| Organization | `ORG<nn>` | `ORG01` |
| Building | `BLD<nn>` | `BLD01` |
| Floor | `<building>_F<nn>` | `BLD01_F02` |
| Zone | `<floor>_Z<code>` | `BLD01_F02_ZA` |
| Desk / workspace | `DESK_<building>_F<nn>_<nnn>` | `DESK_BLD01_F02_045` |
| Cabin | `CABIN_<building>_F<nn>_<nn>` | `CABIN_BLD01_F04_03` |
| Room | `ROOM_<building>_F<nn>_<nn>` | `ROOM_BLD01_F02_04` |
| Common area | `AREA_<building>_F<nn>_<code>` | `AREA_BLD01_F01_CAF` |
| Access point | `AP_<building>_<name><nn>` | `AP_BLD01_ENT01` |
| Sensor | `SEN_<DSK/RM/ENV>_<nnnnnn>` | `SEN_DSK_000021` |
| Department | `DEP_<code>` | `DEP_ENG` |
| Team | `TEAM_<nnn>` | `TEAM_014` |
| Employee | `EMP<nnnnnn>` | `EMP000042` |
| Visitor | `VIS<nnnnnn>` | `VIS000123` |
| Meeting | `MTG-<yyyymmdd>-<nnnn>` | `MTG-20260925-0142` |
| Special event | `SEV-<nnnn>` | `SEV-0007` |

Rooms and common areas share the `room` table and are distinguished by `room_type`. Surrogate keys (`*_sk`) exist only in the warehouse.

---

## 2. PostgreSQL: `workplace` Database

Managed with Alembic. Four schemas:
- `master`: office hierarchy, people
- `config`: configuration versions and layouts
- `sim`: simulation runs
- `ops`: pipeline and source monitoring

All tables have `created_at` and `updated_at` (timestamptz).

### 2.1 `master` schema

```
organization
  org_id              text PK
  name                text

building
  building_id         text PK
  org_id              text FK → organization
  name                text
  timezone            text            -- e.g. 'Asia/Kolkata'
  max_occupancy       int             -- fire/safety limit
  gross_area_sqm      numeric

floor
  floor_id            text PK
  building_id         text FK → building
  floor_number        int
  name                text
  max_occupancy       int
  desk_policy         text            -- ASSIGNED | HOT_DESK
  plan_width          numeric         -- layout units for SVG
  plan_height         numeric
  is_available        bool

zone
  zone_id             text PK
  floor_id            text FK → floor
  name                text
  zone_type           text            -- OPEN_WORKSPACE | TEAM_NEIGHBORHOOD | MEETING | CAFETERIA
                                      -- | LOUNGE | COLLABORATION | CABIN_BLOCK | ENTRANCE | CIRCULATION
  x, y, width, height numeric
  max_occupancy       int
  area_sqm            numeric
  is_hvac_zone        bool            -- v1: every zone is its own HVAC zone

workspace
  workspace_id        text PK
  floor_id            text FK → floor
  zone_id             text FK → zone
  workspace_type      text            -- DESK | CABIN
  x, y                numeric
  status              text            -- ACTIVE | UNAVAILABLE
  has_sensor          bool

room                                  -- meeting rooms AND common areas
  room_id             text PK
  floor_id            text FK → floor
  zone_id             text FK → zone
  name                text
  room_type           text            -- SMALL_MEETING | MEDIUM_MEETING | LARGE_CONFERENCE
                                      -- | AUDITORIUM | COMMON_AREA
  area_subtype        text            -- for COMMON_AREA: CAFETERIA | LOUNGE | COLLABORATION
  capacity            int
  x, y, width, height numeric
  is_bookable         bool
  status              text            -- ACTIVE | UNAVAILABLE

access_point
  access_point_id     text PK
  building_id         text FK
  floor_id            text FK
  name                text
  direction           text            -- IN | OUT | IN_OUT
  x, y                numeric

sensor
  sensor_id           text PK
  sensor_type         text            -- DESK_OCCUPANCY | ROOM_COUNT | ENVIRONMENT
  target_type         text            -- WORKSPACE | ROOM | ZONE
  target_id           text
  floor_id            text FK
  zone_id             text FK
  metrics             text[]          -- ENVIRONMENT only
  poll_interval_s     int
  installed_at        date
  is_active           bool

department
  department_id       text PK
  name                text

team
  team_id             text PK
  department_id       text FK
  name                text
  home_floor_id       text FK → floor
  office_days         smallint[]      -- ISO weekdays, e.g. {2,3,4}
  size_target         int

team_zone_allocation
  team_id             text FK
  zone_id             text FK
  share               numeric         -- 0..1, planned share of the team's seating
  PK (team_id, zone_id)

employee
  employee_id         text PK
  employee_name       text
  email               text UNIQUE
  team_id             text FK
  department_id       text FK
  job_role            text
  manager_id          text FK → employee (nullable)
  home_floor_id       text FK → floor
  preferred_zone_id   text FK → zone
  employment_type     text            -- FULL_TIME | CONTRACTOR | INTERN
  work_mode           text            -- OFFICE | HYBRID | REMOTE
  behavior_profile    text            -- EARLY_BIRD | STANDARD | LATE_STARTER | MEETING_HEAVY
                                      -- | REMOTE_HEAVY | MOBILE_WORKER
  active_flag         bool
  hire_date           date

employee_work_pattern                 -- planned weekly attendance
  employee_id         text FK
  iso_weekday         smallint        -- 1..7
  planned_mode        text            -- OFFICE | REMOTE | FLEX
  PK (employee_id, iso_weekday)

workspace_assignment                  -- ASSIGNED-policy floors only
  assignment_id       bigserial PK
  employee_id         text FK
  workspace_id        text FK
  valid_from          date
  valid_to            date (nullable)
```

Notes:
- Master data is generated by `EmployeeGenerator` and `LayoutLoader` from config and seed. Regenerating replaces master data. The warehouse keeps history via SCD2 dimensions.
- Physical layout (coordinates) comes from `config/layouts/*.yaml`. PostgreSQL stores a normalized copy for joins and API queries. The layout YAML stays the single source of truth.

### 2.2 `config` schema

```
office_configuration
  config_id           uuid PK
  name                text
  simulation_yaml     jsonb           -- resolved simulation.yaml
  profiles_yaml       jsonb
  calendar_yaml       jsonb
  automation_yaml     jsonb
  layout_yaml         jsonb
  content_hash        text            -- hash of all of the above
  is_active           bool
  created_at          timestamptz

master_data_version
  version_id          uuid PK
  config_id           uuid FK
  seed                bigint
  generated_at        timestamptz
  employee_count      int
  content_hash        text
  is_current          bool
```

### 2.3 `sim` schema

```
simulation_run
  simulation_run_id   uuid PK
  config_id           uuid FK
  master_data_version uuid FK
  config_snapshot     jsonb           -- full resolved config at start
  seed                bigint
  mode                text            -- LIVE | BATCH
  sim_start_date      date
  sim_end_date        date            -- BATCH: last day; LIVE: last day reached
  initial_speed       int
  status              text            -- CREATED | RUNNING | PAUSED | STOPPED | COMPLETED | FAILED
  wall_started_at     timestamptz
  wall_ended_at       timestamptz
  sim_time_reached    timestamptz
  events_generated    bigint
  truth_events        bigint
  error_message       text

run_speed_change
  simulation_run_id   uuid FK
  wall_time           timestamptz
  sim_time            timestamptz
  old_speed           int
  new_speed           int

run_metrics_snapshot                  -- written periodically for comparison between runs
  simulation_run_id   uuid FK
  sim_time            timestamptz
  employees_inside    int
  occupied_desks      int
  occupied_rooms      int
  events_generated    bigint
  PK (simulation_run_id, sim_time)
```

### 2.4 `ops` schema

```
pipeline_run
  pipeline_run_id     uuid PK
  trigger             text            -- SCHEDULED | HISTORY_COMPLETED | MANUAL
  started_at          timestamptz
  ended_at            timestamptz
  status              text            -- RUNNING | SUCCEEDED | FAILED
  error_message       text

pipeline_layer_count
  pipeline_run_id     uuid FK
  layer               text            -- RAW | STAGING | CORE | MART
  object_name         text
  rows_total          bigint
  rows_added          bigint
  PK (pipeline_run_id, layer, object_name)

ingestion_watermark
  source_name         text PK         -- raw_archive | pg_master | saas_room_bookings | ...
  watermark_value     text            -- last file manifest / updated_at
  updated_at          timestamptz

source_status_snapshot                -- periodic persistence of processor counters
  source_name         text
  snapshot_at         timestamptz
  status              text            -- CONNECTED | DEGRADED | DISCONNECTED | SIMULATED
  events_received     bigint
  last_event_time     timestamptz
  records_processed   bigint
  processing_failures bigint
  avg_latency_ms      numeric
  PK (source_name, snapshot_at)
```

---

## 3. Mock SaaS: `workplace_saas` Database

Owned exclusively by `mock-saas`. Every table has `updated_at` (indexed, for incremental extraction), `record_status`, and `simulation_run_id` (nullable for admin-created records).

```
room_booking
  booking_id              text PK
  room_id                 text
  organizer_employee_id   text
  attendee_employee_ids   text[]
  title                   text
  start_time              timestamptz
  end_time                timestamptz
  expected_attendees      int
  meeting_id              text        -- link to engine meeting plan
  status                  text        -- CONFIRMED | CANCELLED
  record_status           text
  updated_at              timestamptz

special_event
  special_event_id        text PK
  name                    text
  event_date              date
  start_time              timestamptz
  end_time                timestamptz
  building_id             text
  floor_ids               text[]
  expected_employees      int
  expected_guests         int
  rooms_reserved          text[]
  desks_unavailable       text[]
  status                  text        -- PLANNED | CANCELLED | COMPLETED
  record_status           text
  updated_at              timestamptz

visitor_registration
  visitor_id              text PK
  visitor_name            text
  company                 text
  host_employee_id        text
  special_event_id        text (nullable)
  building_id             text
  expected_arrival        timestamptz
  expected_departure      timestamptz
  badge_id                text
  status                  text        -- REGISTERED | CHECKED_IN | CANCELLED
  record_status           text
  updated_at              timestamptz

leave_record
  leave_id                text PK
  employee_id             text
  leave_date              date
  leave_type              text        -- ANNUAL | SICK | OTHER
  record_status           text
  updated_at              timestamptz
```

The SaaS system has no foreign keys to master data. It stores IDs as opaque strings, as a real external system would.

---

## 4. Current State (Redis)

Maintained by the event processor. Key prefix includes the run: `st:{run}:...`, where `{run}` is the active `simulation_run_id`.

| Key | Type | Fields | Source |
|---|---|---|---|
| `st:{run}:person:{employee_or_visitor_id}` | hash | inside, access_in_time, access_point_id, visit_id, workspace_id, login_time, last_event_time | ACCESS_*, WORKSPACE_* |
| `st:{run}:inside:{building_id}` | set | employee and visitor IDs currently inside | ACCESS_* |
| `st:{run}:desk:{workspace_id}` | hash | sensor_status, sensor_changed_at, sensor_online, logged_in_employee_id, login_time, last_event_time | OCCUPANCY_CHANGED, WORKSPACE_*, SENSOR_STATUS_CHANGED |
| `st:{run}:room:{room_id}` | hash | occupied, occupancy_count, changed_at, sensor_online | ROOM_OCCUPANCY_CHANGED |
| `st:{run}:floor:{floor_id}` | hash | occupied_desks, logged_in_desks, room_occupants, common_area_occupants, est_headcount | derived counters |
| `st:{run}:building:{building_id}` | hash | inside_count, visitors_inside, peak_today, peak_today_time | derived counters |
| `st:{run}:env:{zone_id}` | hash | temperature, humidity, co2, light, noise, reading_time | ENVIRONMENT_READING |
| `st:{run}:hvac:{zone_id}` | hash | mode, setpoint, last_action_time, rule_id | AUTOMATION_ACTION |
| `st:{run}:sensor:{sensor_id}` | hash | status, last_heartbeat | heartbeats, status events |
| `ts:{run}:{scope}:{metric}:{date}` | hash (sim minute → value) | today's rolling series | derived each sim minute |
| `dedupe:{run}` | set with TTL buckets | event IDs | all |
| `metrics:source:{source}` | hash | events_received, last_event_time, failures, latency_ewma_ms | all |

Rules:
- Floor `est_headcount` = occupied desks (sensor) + room occupants + common-area occupants (sensors). It is anonymous and labeled "estimated" in the UI.
- Identity views (who is inside, who is logged in where) come only from `person` and `desk.logged_in_employee_id`.
- On `RESET`, all keys for the run are deleted.

---

## 5. Warehouse

Four schemas: `RAW`, `STAGING`, `CORE`, `MART`. The same dbt models run on DuckDB (local) and Snowflake (cloud). Where SQL differs (JSON access, date functions), dbt macros handle both dialects.

Timestamps are stored as UTC `TIMESTAMP_TZ` plus derived local `event_date` and `event_minute_of_day` columns in STAGING.

### 5.1 RAW (loaded as-is, append-only)

Common columns for event tables:

```
event_id, event_type, event_version, event_time, ingest_time, source,
source_device_id, identity_class, entity_type, entity_id, building_id,
floor_id, zone_id, correlation_id, simulation_run_id, sequence_number,
payload (JSON / VARIANT), processed_at, stream_id,
_file_name, _file_row, _loaded_at
```

| Table | Content |
|---|---|
| `RAW_ACCESS_EVENTS` | ACCESS_IN / ACCESS_OUT |
| `RAW_WORKSPACE_EVENTS` | WORKSPACE_LOGIN / LOGOUT |
| `RAW_OCCUPANCY_EVENTS` | OCCUPANCY_CHANGED, ROOM_OCCUPANCY_CHANGED, desk/room SENSOR_HEARTBEAT |
| `RAW_ENVIRONMENT_EVENTS` | ENVIRONMENT_READING |
| `RAW_SYSTEM_EVENTS` | SENSOR_STATUS_CHANGED, AUTOMATION_ACTION, SIMULATION_LIFECYCLE |
| `RAW_GROUND_TRUTH` | TRUTH_* (simulation-internal) |
| `RAW_BOOKING_EVENTS` | room booking records from SaaS (`record` JSON, `_extracted_at`, `_watermark`) |
| `RAW_VISITOR_REGISTRATIONS` | SaaS visitor records |
| `RAW_SPECIAL_EVENTS` | SaaS special event records |
| `RAW_LEAVE_RECORDS` | SaaS leave records |
| `RAW_MASTER_<ENTITY>` | full snapshot per load of each `master` table (`_snapshot_at`) |
| `RAW_SIMULATION_RUNS` | snapshot of `sim.simulation_run` |

### 5.2 STAGING (clean, typed, deduplicated; one model per source entity)

| Model | Grain | Logic |
|---|---|---|
| `STG_ACCESS_EVENTS` | one row per unique access event | dedupe on (run, event_id) keeping earliest `ingest_time`; typed payload columns; `is_late` flag; `lateness_seconds` |
| `STG_WORKSPACE_EVENTS` | one row per unique workspace event | same dedupe; `logout_reason` |
| `STG_OCCUPANCY` | one row per unique desk or room occupancy change | split `space_type` = DESK / ROOM; heartbeats excluded |
| `STG_SENSOR_HEARTBEATS` | one row per heartbeat | used for gap detection |
| `STG_ENVIRONMENT` | one row per sensor × metric × reading | explodes the `readings` array; drops null values but counts them |
| `STG_SYSTEM_EVENTS` | one row per system event | |
| `STG_BOOKINGS` | latest version per booking_id | dedupe on `updated_at` |
| `STG_VISITORS`, `STG_SPECIAL_EVENTS`, `STG_LEAVE` | latest version per ID | |
| `STG_MASTER_*` | latest snapshot rows | input to SCD2 snapshots |
| `STG_GROUND_TRUTH` | one row per truth transition | |

Data quality counters (duplicates removed, late events, invalid payloads) are captured in `STAGING.DQ_EVENT_QUALITY` (per run, per day, per event type).

### 5.3 CORE

#### Dimensions

| Dimension | Type | Key attributes |
|---|---|---|
| `DIM_DATE` | static | date_key, date, iso_weekday, is_weekend, is_holiday, holiday_name, week, month, quarter, year |
| `DIM_TIME` | static, minute grain (1,440 rows) | time_key, hour, minute, time_band (EARLY, MORNING_PEAK, MIDDAY, AFTERNOON, EVENING), is_core_hours |
| `DIM_BUILDING` | SCD1 | building_sk, building_id, name, timezone, max_occupancy, gross_area_sqm |
| `DIM_FLOOR` | SCD2 | floor_sk, floor_id, building_sk, floor_number, max_occupancy, desk_policy, desk_count, room_count, is_available, valid_from, valid_to, is_current |
| `DIM_ZONE` | SCD2 | zone_sk, zone_id, floor_sk, zone_type, max_occupancy, area_sqm |
| `DIM_WORKSPACE` | SCD2 | workspace_sk, workspace_id, zone_sk, floor_sk, workspace_type, status, has_sensor |
| `DIM_ROOM` | SCD2 | room_sk, room_id, zone_sk, floor_sk, room_type, area_subtype, capacity, is_bookable |
| `DIM_SENSOR` | SCD2 | sensor_sk, sensor_id, sensor_type, target_type, target_id, zone_sk |
| `DIM_TEAM` | SCD2 | team_sk, team_id, name, department_name, home_floor_id, office_days |
| `DIM_EMPLOYEE` | SCD2 | employee_sk, employee_id, name, email, team_sk, department, job_role, work_mode, behavior_profile, home_floor_id, active_flag. **Only PII-bearing table.** |
| `DIM_VISITOR` | SCD1 | visitor_sk, visitor_id, company, host_employee_id, special_event_id |
| `DIM_SPECIAL_EVENT` | SCD1 | special_event_sk, attributes from SaaS |

SCD2 is implemented with dbt snapshots on `STG_MASTER_*`.

#### Facts

| Fact | Grain | Key measures / columns |
|---|---|---|
| `FACT_ACCESS_EVENT` | one access event | employee_sk / visitor_sk, building_sk, access_point_id, direction, event_time, date_key, time_key, is_late |
| `FACT_BUILDING_VISIT` | one person-visit (paired IN → OUT) | person_sk, arrival_time, departure_time, duration_minutes, exit_inferred (missing ACCESS_OUT), entry_inferred (missing ACCESS_IN, first login seen) |
| `FACT_WORKSPACE_SESSION` | one login → logout session | employee_sk, workspace_sk, floor_sk, login_time, logout_time, duration_minutes, logout_reason, assignment_type |
| `FACT_OCCUPANCY` | one occupied interval per desk sensor | workspace_sk, sensor_sk, occupied_start, occupied_end, duration_seconds (built from change events; open intervals closed at day end) |
| `FACT_ROOM_USAGE` | one occupied interval per room sensor | room_sk, occupied_start, occupied_end, max_count, avg_count, matched_booking_id, booked_attendees |
| `FACT_ROOM_BOOKING` | one booking | room_sk, organizer_employee_sk, start, end, expected_attendees, status, was_used (overlap with FACT_ROOM_USAGE), actual_max_count, is_ghost_booking |
| `FACT_SPACE_UTILIZATION_15MIN` | space × 15-minute bucket | space_type (DESK / ROOM / COMMON_AREA), space_sk, floor_sk, zone_sk, bucket_start, occupied_seconds, logged_in_seconds (desks only), avg_count, max_count, capacity, sensor_online_seconds |
| `FACT_BUILDING_OCCUPANCY_15MIN` | building × 15-minute bucket | headcount_end, headcount_max (from visits), visitors_max, estimated_floor_headcount (per floor) |
| `FACT_ENVIRONMENT` | sensor × metric × reading | zone_sk, sensor_sk, metric_type, metric_value, unit, reading_time |
| `FACT_AUTOMATION_EVENT` | one automation action | zone_sk, rule_id, trigger (JSON), action, action_params, reading_time |
| `FACT_SENSOR_STATUS` | one status interval per sensor | sensor_sk, status, status_start, status_end |
| `FACT_GROUND_TRUTH_ACTIVITY` | one person-activity interval (**simulation-internal**) | person_id, state, location_type, location_id, start, end |

Design notes:
- **Interval facts** (visits, sessions, occupancy, room usage) are the backbone of utilization. Events are converted to intervals once in CORE.
- **`FACT_SPACE_UTILIZATION_15MIN`** is the main periodic snapshot. Almost every utilization mart aggregates from it, which keeps marts cheap and consistent.
- Sensor facts and identity facts are never joined on person. Desk-level comparisons (`logged_in_seconds` vs `occupied_seconds`) are joined on workspace and time only.

### 5.4 MART

All marts exclude employee-level PII. The lowest person-related grain is team.

| Mart | Grain | Answers |
|---|---|---|
| `MART_CURRENT_OCCUPANCY` | building / floor, latest snapshot | fallback/analytics copy of current state (live UI uses Redis) |
| `MART_FLOOR_UTILIZATION` | floor × date (+ hour) | avg/peak desk utilization, room utilization, est. headcount vs capacity |
| `MART_TEAM_UTILIZATION` | team × date | attendance count, attendance rate, desk-hours used, floor distribution (% of team sessions per floor) |
| `MART_DESK_UTILIZATION` | desk × date | occupied hours, utilization %, logged-in hours, **login-without-occupancy hours** (desk holding), rarely-used flag |
| `MART_ROOM_UTILIZATION` | room × date | occupied hours, utilization %, avg occupancy vs capacity (right-sizing), bookings, ghost bookings, walk-ins |
| `MART_DAILY_ATTENDANCE` | building × date | unique employees, unique visitors, attendance % of active employees, by work mode |
| `MART_PEAK_OCCUPANCY` | building / floor × date | peak headcount, peak time, peak utilization %, avg utilization % |
| `MART_REAL_ESTATE_UTILIZATION` | building × period (rolling 30/60/90 days) | total capacity, avg/peak occupancy, unused capacity, desk-to-employee ratio, P90 peak, recommendation flags |
| `MART_RECOMMENDATIONS` | building / floor × rule × evaluation date | rule_id, observation text, supporting metric values, severity. Rules from `config/recommendations.yaml` |
| `MART_HEATMAP` | zone / desk × period type (TODAY, 7D, 30D) | utilization %, band (VERY_LOW … VERY_HIGH) |
| `MART_ENVIRONMENT_HOURLY` | zone × hour | avg/min/max per metric, avg occupancy (occupancy vs temperature) |
| `MART_BOOKING_EFFECTIVENESS` | room / floor × date | booked hours, used booked hours, ghost booking rate, no-show rate |
| `MART_DATA_QUALITY` | run × date × event type | duplicates, late %, missing heartbeat %, sensor downtime % |
| `MART_SENSOR_ACCURACY` | run × date × space type (**simulation evaluation**) | sensor occupancy vs ground truth: precision, recall, avg detection lag, count error |

---

## 6. Metric Definitions

Defined once in `packages/domain/metrics` (for the API) and mirrored in dbt macros (for marts). Tests assert both give the same results on fixture data.

| Metric | Definition |
|---|---|
| **Core hours** | configurable, default 08:00–18:00 on working days (`DIM_DATE.is_holiday = false`, not weekend) |
| **Desk utilization %** | Σ desk `occupied_seconds` in core hours ÷ Σ available desk-seconds in core hours (ACTIVE desks with sensor online) |
| **Desk usage rate %** | desks occupied at least `min_use_minutes` (default 30) in a day ÷ ACTIVE desks |
| **Room utilization %** | Σ room occupied seconds in core hours ÷ Σ room available seconds in core hours |
| **Room occupancy fit** | avg occupancy count while occupied ÷ capacity (right-sizing signal) |
| **Building headcount (t)** | people with an open visit at time t (identity-aware, from access events, inferred exits applied) |
| **Peak occupancy** | max building headcount over the day, sampled every minute |
| **Building utilization %** | headcount ÷ building max_occupancy |
| **Attendance rate %** | unique employees with ≥1 visit ÷ active employees expected to work that day (excluding leave, weekends, holidays) |
| **Desk-to-employee ratio** | ACTIVE desks ÷ active non-remote employees |
| **Unused capacity** | total desks − peak occupied desks (per day), averaged over the period |
| **Ghost booking** | confirmed booking with zero sensor-occupied overlap within `ghost_grace_minutes` (default 10) of start |
| **Desk holding** | logged-in seconds where the desk sensor reports vacant, per desk-day |
| **Utilization band** | Very Low <20%, Low 20–40%, Moderate 40–60%, High 60–80%, Very High ≥80% (configurable) |

Recommendation rules (examples, configurable in `config/recommendations.yaml`):

| Rule | Condition | Observation |
|---|---|---|
| `CONSOLIDATION_OPPORTUNITY` | avg building utilization < 40% for 60 consecutive working days | "Potential space consolidation opportunity." |
| `EXPANSION_INVESTIGATION` | peak utilization > 90% on ≥ 30% of working days in last 60 | "Capacity expansion may need investigation." |
| `UNDERUSED_FLOOR` | floor avg desk utilization < 25% for 30 working days | "Floor {floor} is underutilized; consider consolidating teams." |
| `ROOM_RIGHT_SIZING` | room occupancy fit < 35% over 30 days for rooms with capacity ≥ 8 | "Room {room} is usually used by small groups." |
| `GHOST_BOOKINGS` | ghost booking rate > 20% over 30 days | "High rate of unused bookings; consider auto-release." |

All recommendations are rule-based and show the metric values that triggered them.
