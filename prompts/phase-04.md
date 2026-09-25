# Phase 4 — Identity events and processing

_(Run `/clear` before pasting this. Use plan mode.)_

Read `CLAUDE.md`, then Phase 4 in `docs/implementation-plan.md` and only the doc sections it references.

**Phase-specific instructions**
- Port access observer (entrance, floor-lobby, secure-zone, room-door readers; tailgating, missed badge-out, internal badge compliance), room-panel check-in, workstation observer, delivery layer (anomalies at 0).
- `RedisStreamPublisher/Consumer`; event-processor logic mirroring `reference/refsim/state.py` (dedupe, event-time guards, person/floor/login state), raw archive identical in layout to `mock-data/raw`, source metrics, live pub/sub.
- Port privacy + login-after-arrival tests. Add a processor restart test.

**Workflow**
1. Propose a plan: files to create/change, tests to write/port, anything unclear. Wait for my approval.
2. Implement in small commits. Stay inside this phase's scope.
3. Run `make test` and `make lint`; fix failures.
4. Update docs/decision log if anything deviated.
5. Report against each acceptance criterion (met / not met / how verified), then stop.
