# Reference Simulator (`refsim`)

A small, working implementation of the simulation engine, event processor and live viewer. It is the **behaviour oracle** for the production services: port its logic and tests; don't import it from production code.

```bash
pip install -r requirements.txt
python -m refsim serve --speed 60            # http://127.0.0.1:8765 → ▶ Start
python -m refsim history --days 7 --out ../mock-data-7d
python -m refsim stream --speed 60 --hours 10 | head
python -m pytest -q                          # 10 behaviour tests
```

| Module | Implements | Doc |
|---|---|---|
| `common.py` | config, named RNG streams, time, envelope, identity table, privacy validator | event-model §2–4 |
| `layout.py` | building/floors/zones/desks/rooms/common areas/readers/sensors with coordinates | data-model §2 |
| `master.py` | departments, teams, floor/zone placement, restricted zones, employees, work patterns, assigned desks | SPEC §5, data-model §2 |
| `engine.py` | scheduler, planner, attendance calibration, person state machine, desk assignment, meetings, observers (access, area readers, room panel, workstation, desk/room sensors), environment physics, BMS, delivery/anomalies | simulation-engine |
| `sinks.py` | raw archive (partitioned JSONL + manifests), stdout, callback, Redis Streams | event-model §6, §9 |
| `state.py` | processor: dedupe, event-time guards, current state, KPIs, change log, truth positions | data-model §4, live-streaming §6 |
| `server.py` | scaled clock + night skip, control, snapshot/stream contracts (SSE) | live-streaming |
| `viewer/index.html` | isometric building, 2D floor twin, overlays, Simulation View dots, hybrid chart, live feed | visualization-spec |

Viewer controls: ▶ Start / Pause / Reset, speed, Operational vs Simulation (truth) view, overlay (occupancy, temperature, HVAC). Click a desk or room for details (desk identity comes only from workstation login). Click a floor in the isometric stack.
