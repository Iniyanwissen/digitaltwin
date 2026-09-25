# Live Streaming and View Updates (Local)

> Status: DRAFT v0.2. Related: `architecture.md`, `event-model.md`, `visualization-spec.md`
> Reference: `reference/refsim/server.py` (runner + SSE) and `reference/refsim/state.py` (processor). The production stack keeps the same message contracts (§4) but swaps the transport.

---

## 1. How data changes over time

Nothing is refreshed in bulk. The simulation engine advances a simulated clock and every change in the world produces events:

```
simulated clock ticks forward
  → scheduled person transitions fire (arrive, sit, meeting, lunch, leave…)
  → observers emit what devices would report (badge, login, sensor, reader, panel)
  → environment ticks every 60 s (live) and BMS rules evaluate
  → events are delivered at their ingest time
  → processor updates current state and a change log
  → UI receives deltas a few times per second and redraws what changed
```

At 60x speed one simulated minute passes per wall second. At medium scale on a working day that is roughly 20–60 observed events per wall second, plus environment readings.

---

## 2. Local topology

| Step | Reference (single process) | Production (local Docker) |
|---|---|---|
| Engine | `Engine` in a runner thread | `simulation-engine` service |
| Transport | in-process `CallbackSink` | Redis Streams `ev.*` |
| Processor | `LiveState` | `event-processor` → Redis `st:*`, `ts:*`, raw archive |
| Replay | not implemented | processor writes `sim.floor_snapshot` each sim-minute |
| UI transport | SSE `/api/stream` every 500 ms | FastAPI WebSocket `/ws/live`, flush every 500 ms |
| Control | `POST /api/control` | `POST /api/v1/simulation/commands` → Redis pub/sub `sim.control` |

Everything runs on the developer machine. Moving to Azure/Snowflake later changes only adapters (`cloud-migration.md`).

---

## 3. Clock, speed and night skip

- Scaled clock: `sim = anchor_sim + (wall − anchor_wall) × speed`. Speed changes and resume re-anchor, so time never jumps backwards.
- The runner wakes every 50 ms, advances the engine to the target sim time, then samples KPIs (one series point per sim-minute).
- **Night skip:** when nobody is truly inside and the sim hour is ≥ 20:30 or < 06:00, the clock jumps to the next 06:00. Environment ticks in between are still processed (instantly), so temperature/HVAC continuity is preserved.
- Pause freezes the anchor; reset rebuilds engine and state and starts a new run.

---

## 4. Message contracts (keep these in production)

### 4.1 `GET layout`
Buildings, floors, zones, workspaces (x, y, size), rooms (x, y, width, height, capacity, reader/panel flags), access points, sensors, department list. Static per run; cache in the client.

### 4.2 `GET snapshot`
Full current state for bootstrapping or resync:

```json
{
  "version": 184223,
  "sim_time": "2026-09-28T10:41:14.000+05:30",
  "status": "RUNNING",
  "speed": 60,
  "desks":  { "DESK_BLD01_F02_0245": [1, 1] },      // [sensor 0/1, logged_in 0/1]
  "rooms":  { "ROOM_BLD01_F02_014": 4 },            // sensor count
  "zones":  { "BLD01_F02_ZA": [23.4, 612, "NORMAL"] }, // [temp, co2, hvac]
  "positions": { "EMP000042": [51.2, 33.0, "BLD01_F02", "Engineering", "AT_DESK"] },  // Simulation View only
  "kpis": { "...": "see state.kpis()" },
  "series": [ { "m": "10:40", "inside": 512, "desks": 431, "held": 38, "rooms": 64 } ],
  "truth":  { "inside": 530, "at_desk": 402, "in_meeting": 61, "occupied_desks_truth": 440, "claimed_desks": 480 }
}
```

In production, `positions` and `truth` are served on a separate truth channel/endpoint and only when the Simulation View is on.

### 4.3 Stream frame (every 500 ms)

```json
{
  "sim_time": "…", "status": "RUNNING", "speed": 60,
  "desks": { "<id>": [sensor, logged_in] },   // only changed since `since`
  "rooms": { "<id>": count },
  "zones": { "<id>": [temp, co2, hvac] },
  "positions": { "<person>": [x, y, floor, dept, state] | null },  // null = left the building
  "feed": [ { "t": "10:41:12", "type": "ACCESS_IN", "entity": "EMP000753", "floor": "BLD01_F01", "detail": "AP_BLD01_ENT01", "identity": "IDENTIFIED" } ],
  "kpis": { … },
  "point": { "m": "10:41", "inside": 514, "desks": 433, "held": 37, "rooms": 66 },
  "truth": { … },
  "events_total": 91233,
  "automation": [ { "t": "…", "zone": "…", "rule": "HVAC_ECO_WHEN_EMPTY", "action": "SET_HVAC_MODE", "params": { "mode": "ECO" } } ]
}
```

- Deltas come from a **versioned change log** (`version`, kind, key, value). The client sends its last version (`since`); the server coalesces all changes after it (last value per key wins).
- If the client is older than the retained log, the server replies `{ "resync": true }` and the client reloads the snapshot.
- Feed is capped per frame (40) and in the client buffer.

---

## 5. Client update model

1. Load layout (once) and snapshot.
2. Open the stream with `since = snapshot.version`.
3. For each frame: merge maps into the store, append series point (reset on new day), update KPIs (throttled to 2 Hz), prepend feed rows (capped), set `dirty`.
4. `requestAnimationFrame` loop redraws the floor only when dirty or while dots are tweening.
5. Dots: each position change starts a 900 ms tween from the current drawn position to the new target.

---

## 6. Processor rules that affect the view

- Dedupe by `event_id`; per-key event-time guards (late events never regress state).
- `employees_inside` = open visits from `ACCESS_IN`/`ACCESS_OUT` (identified). At day rollover open visits are closed (inferred exits for missed badge-outs).
- Desk colour = sensor (occupied) else login (held) else vacant.
- Floor "estimated headcount" = occupied desks + room/common-area counts (anonymous).
- Truth data is applied to a separate structure (`positions`) and never mixed into observed state.

---

## 7. Production hardening checklist

- [ ] WebSocket per client with bounded send queue; drop to resync if the client falls behind.
- [ ] Separate channels: `live` (operational), `truth` (simulation view), `status` (engine), `events` (feed with server-side filters).
- [ ] Snapshot writer for `sim.floor_snapshot` (per floor per sim-minute, only non-default values).
- [ ] Back-pressure metric: engine scheduler lag and processor consumer lag exposed on Data Sources.
- [ ] Frame size budget: < 50 KB per frame at medium scale, 60x.
