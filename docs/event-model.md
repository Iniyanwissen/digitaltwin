# Event Model

> Status: DRAFT v0.1. Related: `architecture.md`, `simulation-engine.md`, `data-model.md`

---

## 1. Data Categories

Every dataset in the system belongs to exactly one category (SPEC §41). The category determines storage and schema design.

| Category | Examples | Storage | Characteristics |
|---|---|---|---|
| **Event** | `ACCESS_IN`, `WORKSPACE_LOGIN`, `OCCUPANCY_CHANGED` | event bus → raw archive → warehouse facts | immutable, append-only, event-time ordered |
| **State** | employee inside, desk occupied, room count | Redis current state | mutable, derived from events, latest value only |
| **Time-series** | temperature, CO2 every N minutes | events → `FACT_ENVIRONMENT` | regular interval, per sensor per metric |
| **Master** | employee, workspace, floor | PostgreSQL → `DIM_*` | slowly changing, SCD2 in the warehouse |
| **Transactional** | room booking, visitor registration, leave | mock SaaS DB → REST → RAW | mutable records with `updated_at` |
| **Analytical** | daily floor utilization | warehouse `MART_*` | aggregated, rebuilt by dbt |
| **Simulation-internal** | ground truth transitions | truth stream → `RAW_GROUND_TRUTH` | never used by operational marts or UI |

Transactional SaaS data is **not** carried in the event envelope. It is pulled as records via REST (see §8).

---

## 2. Common Event Envelope

All streamed events use this envelope. It is defined once as a Pydantic model in `packages/domain`.

```json
{
  "event_id": "5f0c8a3e-7b2d-5c1e-9a44-2f6d1b0e7c11",
  "event_type": "ACCESS_IN",
  "event_version": 1,
  "event_time": "2026-09-25T09:14:32.000",
  "ingest_time": "2026-09-25T09:14:33.200",
  "source": "ACCESS_CONTROL",
  "source_device_id": "AP_BLD01_ENT01",
  "identity_class": "IDENTIFIED",
  "entity_type": "EMPLOYEE",
  "entity_id": "EMP000042",
  "building_id": "BLD01",
  "floor_id": "BLD01_F01",
  "zone_id": null,
  "correlation_id": "VISIT-EMP000042-20260925-1",
  "simulation_run_id": "b1e2...",
  "sequence_number": 184223,
  "payload": { }
}
```

### Field definitions

| Field | Type | Required | Notes |
|---|---|---|---|
| `event_id` | UUID | yes | `UUIDv5(simulation_run_id, sequence_number)`. Duplicated events keep the same `event_id`. |
| `event_type` | enum | yes | see §4 |
| `event_version` | int | yes | payload schema version, starts at 1 |
| `event_time` | timestamp (sim) | yes | when the event happened according to the source device |
| `ingest_time` | timestamp (sim) | yes | when the event reached ingestion. Set by the engine's delivery model. `ingest_time >= event_time`. Late events have a large gap. |
| `source` | enum | yes | see §3 |
| `source_device_id` | string | yes | access point, workstation, sensor, or BMS controller ID |
| `identity_class` | enum | yes | `IDENTIFIED`, `ANONYMOUS`, `SYSTEM`. Determined by `event_type`, never set freely. |
| `entity_type` | enum | yes | `EMPLOYEE`, `VISITOR`, `WORKSPACE`, `ROOM`, `SENSOR`, `ZONE` |
| `entity_id` | string | yes | ID of the entity the event is about |
| `building_id` | string | yes | |
| `floor_id` | string | no | null for building-level events |
| `zone_id` | string | no | |
| `correlation_id` | string | no | **IDENTIFIED events only.** Links events of one person-visit. Always null for ANONYMOUS events. |
| `simulation_run_id` | UUID | yes | |
| `sequence_number` | int64 | yes | monotonic per run, in generation order (not delivery order) |
| `payload` | object | yes | type-specific, see §5 |

Fields added by the event processor (wall clock, not part of the published envelope):

| Field | Notes |
|---|---|
| `processed_at` | wall-clock time the processor handled the event, used for pipeline latency monitoring |
| `stream_id` | Redis stream entry ID or Event Hubs offset/partition |

### Timestamp semantics

- All business timestamps are **simulated time**, timezone-aware, in the building's configured timezone and serialized as ISO-8601 with offset. Warehouse stores UTC plus the local-date columns.
- `event_time` for sensors is the sensor's own reported time. It already includes sensor detection lag (a desk sensor reports occupancy some seconds after the person sits down).
- Lateness = `ingest_time - event_time`. `STAGING` flags events as late when this exceeds `late_threshold_seconds` (config, default 300).
- Out-of-order = delivered in a different order than `event_time` for the same entity.

---

## 3. Sources

| Source | Identity class | Represents | Device ID |
|---|---|---|---|
| `ACCESS_CONTROL` | IDENTIFIED | badge readers at entrances | access point ID |
| `WORKSTATION` | IDENTIFIED | desk login system / docking | workspace ID |
| `DESK_SENSOR` | ANONYMOUS | under-desk PIR occupancy sensor | sensor ID |
| `ROOM_SENSOR` | ANONYMOUS | people-count sensor in rooms and common areas | sensor ID |
| `ENV_SENSOR` | ANONYMOUS | environmental multi-sensor per zone | sensor ID |
| `SENSOR_GATEWAY` | SYSTEM | IoT gateway reporting device health | gateway ID |
| `BMS` | SYSTEM | building management system (simulated HVAC control) | BMS controller ID |
| `SIMULATION` | internal | ground truth and run lifecycle | engine ID |

SaaS sources (`BOOKING_SYSTEM`, `VISITOR_SYSTEM`, `HR_SYSTEM`) are record-based and pulled via REST. See §8.

---

## 4. Event Types

| Event type | Source | Identity | Entity | Stream |
|---|---|---|---|---|
| `ACCESS_IN` | ACCESS_CONTROL | IDENTIFIED | EMPLOYEE / VISITOR | `ev.access` |
| `ACCESS_OUT` | ACCESS_CONTROL | IDENTIFIED | EMPLOYEE / VISITOR | `ev.access` |
| `WORKSPACE_LOGIN` | WORKSTATION | IDENTIFIED | EMPLOYEE | `ev.workspace` |
| `WORKSPACE_LOGOUT` | WORKSTATION | IDENTIFIED | EMPLOYEE | `ev.workspace` |
| `OCCUPANCY_CHANGED` | DESK_SENSOR | ANONYMOUS | WORKSPACE | `ev.occupancy` |
| `ROOM_OCCUPANCY_CHANGED` | ROOM_SENSOR | ANONYMOUS | ROOM | `ev.occupancy` |
| `SENSOR_HEARTBEAT` | DESK_SENSOR / ROOM_SENSOR / ENV_SENSOR | ANONYMOUS | SENSOR | `ev.occupancy` / `ev.environment` |
| `ENVIRONMENT_READING` | ENV_SENSOR | ANONYMOUS | ZONE | `ev.environment` |
| `SENSOR_STATUS_CHANGED` | SENSOR_GATEWAY | SYSTEM | SENSOR | `ev.system` |
| `AUTOMATION_ACTION` | BMS | SYSTEM | ZONE | `ev.system` |
| `TRUTH_STATE_TRANSITION` | SIMULATION | internal | EMPLOYEE / VISITOR | `ev.truth` |
| `TRUTH_DESK_SEARCH_FAILED` | SIMULATION | internal | EMPLOYEE | `ev.truth` |
| `SIMULATION_LIFECYCLE` | SIMULATION | SYSTEM | - | `ev.system` |

### Identity rule (enforced in code)

- `identity_class` is derived from `event_type` by a single lookup table in the domain package.
- The envelope validator rejects any ANONYMOUS event where:
  - `entity_type` is `EMPLOYEE` or `VISITOR`
  - `correlation_id` is not null
  - the payload contains any key from a denylist (`employee_id`, `visitor_id`, `person_id`, `email`, `name`)
- Truth events never go to operational consumers (see §7).

---

## 5. Payload Schemas

### 5.1 `ACCESS_IN` / `ACCESS_OUT`

```json
{
  "access_point_id": "AP_BLD01_ENT01",
  "credential_type": "EMPLOYEE_BADGE",
  "direction": "IN",
  "result": "GRANTED",
  "special_event_id": null
}
```

- `credential_type`: `EMPLOYEE_BADGE` | `VISITOR_BADGE`
- `result`: `GRANTED` only in v1 (denials are out of scope)
- `special_event_id`: set for visitor badges issued for a special event
- Realistic imperfections (handled by the observer, not the payload): tailgating produces a missing `ACCESS_IN`; forgetting to badge out produces a missing `ACCESS_OUT`. The processor closes open visits at end of day with an inferred exit (state only, never a fabricated event).

### 5.2 `WORKSPACE_LOGIN`

```json
{
  "workspace_id": "DESK_BLD01_F02_045",
  "login_method": "BADGE_TAP",
  "assignment_type": "HOT_DESK"
}
```

- `login_method`: `BADGE_TAP` | `DOCKING` | `PASSWORD`
- `assignment_type`: `ASSIGNED` | `HOT_DESK` | `OVERFLOW`

### 5.3 `WORKSPACE_LOGOUT`

```json
{
  "workspace_id": "DESK_BLD01_F02_045",
  "logout_reason": "EXPLICIT",
  "session_login_time": "2026-09-25T09:01:10+05:30"
}
```

- `logout_reason`: `EXPLICIT` | `SWITCH` (logged into another desk) | `TIMEOUT` (idle policy) | `END_OF_DAY` (system sweep)

### 5.4 `OCCUPANCY_CHANGED` (desk sensor)

```json
{
  "sensor_id": "SEN_DSK_000021",
  "workspace_id": "DESK_BLD01_F02_045",
  "sensor_type": "DESK_OCCUPANCY",
  "occupancy_status": 1,
  "previous_status": 0
}
```

- Emitted on debounced state change only. Periodic state is carried by `SENSOR_HEARTBEAT`.

### 5.5 `ROOM_OCCUPANCY_CHANGED`

```json
{
  "sensor_id": "SEN_RM_000104",
  "room_id": "ROOM_BLD01_F02_04",
  "room_type": "MEDIUM_MEETING",
  "capacity": 8,
  "occupied": true,
  "occupancy_count": 4,
  "previous_count": 3,
  "count_confidence": 0.9
}
```

- Also used for common areas (`room_type = COMMON_AREA`: cafeteria, lounge, collaboration area).
- `occupancy_count` is a sensor estimate and may differ from truth by ±1 (configurable count noise).
- Emitted when the reported count changes.

### 5.6 `SENSOR_HEARTBEAT`

```json
{
  "sensor_id": "SEN_DSK_000021",
  "sensor_type": "DESK_OCCUPANCY",
  "current_value": 1,
  "battery_pct": 87,
  "rssi_dbm": -61
}
```

- Emitted every `poll_interval` per sensor (config per sensor type).
- Absence of heartbeats is how missing data and failures are detected downstream.
- For volume reasons, heartbeat intervals default to 5 min for desks and rooms. Environment sensors do not send separate heartbeats because their readings serve that purpose.

### 5.7 `ENVIRONMENT_READING`

One event per sensor per reading, containing all metrics of that sensor.

```json
{
  "sensor_id": "SEN_ENV_000012",
  "readings": [
    {"metric_type": "TEMPERATURE", "value": 23.4, "unit": "C"},
    {"metric_type": "HUMIDITY", "value": 48.2, "unit": "PCT"},
    {"metric_type": "CO2", "value": 612, "unit": "PPM"},
    {"metric_type": "LIGHT", "value": 420, "unit": "LUX"},
    {"metric_type": "NOISE", "value": 46.5, "unit": "DBA"}
  ]
}
```

- Multi-metric events reduce event volume 5x vs one event per metric. `STAGING` explodes them to one row per metric, matching the SPEC §12 schema (`sensor_id, zone_id, metric_type, metric_value, unit, timestamp`).
- A failed sensor stops emitting. Individual metrics may be missing (`value: null`) under the partial-failure anomaly.

### 5.8 `SENSOR_STATUS_CHANGED`

```json
{
  "sensor_id": "SEN_DSK_000021",
  "status": "OFFLINE",
  "previous_status": "ONLINE",
  "reason": "NO_HEARTBEAT"
}
```

- Emitted by the gateway after `missed_heartbeats_threshold` (default 3) consecutive missed heartbeats, and again on recovery.

### 5.9 `AUTOMATION_ACTION`

```json
{
  "automation_event_id": "AUT-000812",
  "rule_id": "HVAC_ECO_WHEN_EMPTY",
  "trigger": {
    "condition": "zone_occupancy == 0 for 15 min",
    "observed_values": {"occupied_desks": 0, "room_occupants": 0, "minutes_empty": 15}
  },
  "action": "SET_HVAC_MODE",
  "action_params": {"mode": "ECO"},
  "previous_state": {"mode": "NORMAL"},
  "hvac_zone_id": "BLD01_F03_ZB"
}
```

- `observed_values` contains only observed sensor data, never ground truth.
- Actions: `SET_HVAC_MODE` (`ECO` | `NORMAL` | `HIGH`), `ADJUST_SETPOINT`, `INCREASE_VENTILATION`.

### 5.10 `TRUTH_STATE_TRANSITION` (simulation-internal)

```json
{
  "person_id": "EMP000042",
  "person_type": "EMPLOYEE",
  "from_state": "AT_DESK",
  "to_state": "MEETING",
  "location_type": "ROOM",
  "location_id": "ROOM_BLD01_F02_04",
  "held_workspace_id": "DESK_BLD01_F02_037",
  "reason": "SCHEDULED_MEETING",
  "meeting_id": "MTG-20260925-0142"
}
```

### 5.11 `TRUTH_DESK_SEARCH_FAILED` (simulation-internal)

```json
{
  "person_id": "EMP000042",
  "floor_id": "BLD01_F02",
  "fallback": "OVERFLOW_OTHER_FLOOR",
  "fallback_location_id": "DESK_BLD01_F03_012"
}
```

### 5.12 `SIMULATION_LIFECYCLE`

```json
{
  "lifecycle": "RUN_STARTED",
  "mode": "LIVE",
  "speed": 30,
  "seed": 12345,
  "sim_date": "2026-09-25"
}
```

- `lifecycle`: `RUN_STARTED` | `PAUSED` | `RESUMED` | `SPEED_CHANGED` | `DAY_STARTED` | `DAY_ENDED` | `RUN_STOPPED` | `RUN_FAILED`

---

## 6. Streams, Partitioning, and Ordering

### Redis Streams (local)

| Stream key | Event types | Max length (approx trim) |
|---|---|---|
| `ev.access` | ACCESS_IN, ACCESS_OUT | 1,000,000 |
| `ev.workspace` | WORKSPACE_LOGIN, WORKSPACE_LOGOUT | 1,000,000 |
| `ev.occupancy` | OCCUPANCY_CHANGED, ROOM_OCCUPANCY_CHANGED, desk/room heartbeats | 2,000,000 |
| `ev.environment` | ENVIRONMENT_READING | 2,000,000 |
| `ev.system` | SENSOR_STATUS_CHANGED, AUTOMATION_ACTION, SIMULATION_LIFECYCLE | 500,000 |
| `ev.truth` | TRUTH_* | 2,000,000 |
| `ev.deadletter` | invalid events with error | 100,000 |

- Consumer group `processor` on each operational stream. The processor also archives `ev.truth` but never applies it to current state.
- Streams are trimmed because the raw archive is the durable history.

### Azure Event Hubs (cloud)

- One hub per operational stream: `access`, `workspace`, `occupancy`, `environment`, `system`. Plus `sim-truth` (optional, archive only).
- Partition keys:
  - identified events: `entity_id` (per-person ordering)
  - desk/room/env events: `source_device_id` (per-device ordering)
  - system events: `hvac_zone_id` or `sensor_id`
- Event Hubs Capture may land to ADLS as an alternative to processor-written archives. The v1 design keeps processor-written archives so both environments behave identically.

### Ordering guarantees

- Events are published in `ingest_time` order. Late and out-of-order events are therefore delivered after later events.
- Consumers must not assume `event_time` ordering. The processor applies per-entity last-event-time guards (§7).

---

## 7. Consumer Rules (Event Processor)

- **Dedup:** skip if `(simulation_run_id, event_id)` was seen in the last `dedupe_window` (Redis set with TTL, default 24 sim hours). Always archive, even duplicates (raw is "as received").
- **Validation:** envelope + payload validated with Pydantic. Failures go to `ev.deadletter`.
- **State application:** each state field stores `last_event_time`. An event updates the field only if its `event_time >= last_event_time`. Older events are archived but do not regress current state.
- **Truth isolation:** `ev.truth` events are archived to `raw/truth/...` only. They are never applied to current state or forwarded to the live feed, except to the "Simulation Debug" channel when debug mode is enabled.
- **Live feed:** operational events are forwarded to `live.events`. State changes are forwarded to `live.state_deltas`.

---

## 8. Transactional (SaaS) Records

Pulled via REST from the mock SaaS with `GET /v1/{resource}?updated_since=...&page=...`. Each record includes `updated_at` and a `record_status` (`ACTIVE` | `CANCELLED` | `DELETED`).

| Resource | Key fields | Identity |
|---|---|---|
| `room-bookings` | booking_id, room_id, organizer_employee_id, attendee_employee_ids, start_time, end_time, expected_attendees, status | identified |
| `visitor-registrations` | visitor_id, host_employee_id, special_event_id, visitor_name, company, expected_arrival, expected_departure, badge_id | identified |
| `special-events` | special_event_id, name, date, start_time, end_time, building_id, floor_ids, expected_employees, expected_guests, rooms_reserved, desks_unavailable | none |
| `leave-records` | leave_id, employee_id, leave_date, leave_type | identified |

RAW tables store each extracted record with `_extracted_at` (wall), `_watermark`, and the full JSON record. See `data-model.md`.

---

## 9. Raw Archive Layout

```
raw/
  events/
    year=YYYY/month=MM/day=DD/hour=HH/event_type=<EVENT_TYPE>/
      part-<simulation_run_id>-<processor_instance>-<batch_seq>.jsonl
  truth/
    year=YYYY/month=MM/day=DD/hour=HH/event_type=<TRUTH_TYPE>/
      part-....jsonl
  deadletter/
    year=YYYY/month=MM/day=DD/
      part-....jsonl
```

- Partitioned by **`ingest_time`** (simulated), since raw is a landing zone ordered by arrival. Late events land in later partitions, which is realistic and exercised by the pipeline.
- One JSON envelope per line, exactly as received, plus `processed_at` and `stream_id`.
- Files are closed and become loadable every N records or M seconds (config). A `_manifest` file per closed file (row count, min/max times) supports idempotent loading.
- Batch (historical) mode writes the same layout directly from the engine.

---

## 10. Versioning and Evolution

- Payload changes that add optional fields keep the same `event_version`.
- Breaking changes increment `event_version`. Staging models handle each version explicitly.
- New event types must be added to the identity lookup table, the Pydantic payload registry, and the contract tests before they can be emitted.
- When real systems replace simulated sources, a source adapter maps vendor payloads into this envelope. Downstream consumers are unchanged.

---

## 11. End-to-End Example (SPEC §48, observed view)

| Sim time | Event | Notes |
|---|---|---|
| 08:52:04 | `ACCESS_IN` EMP000042 @ AP_BLD01_ENT01 | correlation_id = visit ID |
| 09:01:10 | `WORKSPACE_LOGIN` EMP000042 → DESK_BLD01_F02_037 | same correlation_id |
| 09:01:47 | `OCCUPANCY_CHANGED` DESK_BLD01_F02_037 → 1 | anonymous, detection lag ~37 s |
| 10:27:15 | `ROOM_OCCUPANCY_CHANGED` ROOM_BLD01_F02_04 3 → 4 | anonymous |
| 10:29:40 | `OCCUPANCY_CHANGED` DESK_BLD01_F02_037 → 0 | vacancy timeout after leaving at 10:26 |
| 11:17:30 | `ROOM_OCCUPANCY_CHANGED` ROOM_BLD01_F02_04 4 → 3 | |
| 11:19:02 | `OCCUPANCY_CHANGED` DESK_BLD01_F02_037 → 1 | login unchanged all morning |
| 13:05:50 | `OCCUPANCY_CHANGED` DESK_BLD01_F02_037 → 0 | lunch |
| 14:01:40 | `OCCUPANCY_CHANGED` DESK_BLD01_F02_037 → 1 | |
| 18:11:05 | `WORKSPACE_LOGOUT` EMP000042 (EXPLICIT) | |
| 18:13:30 | `OCCUPANCY_CHANGED` DESK_BLD01_F02_037 → 0 | |
| 18:16:12 | `ACCESS_OUT` EMP000042 | |

Throughout the meeting, workspace state shows `DESK_BLD01_F02_037 → EMP000042 (logged in)` while the sensor shows `VACANT`. Nothing links the room count change to EMP000042 in observed data. Only the internal truth stream knows.
