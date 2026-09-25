# Phase 5 — Sensors, environment, BMS, mock SaaS

_(Run `/clear` before pasting this. Use plan mode.)_

Read `CLAUDE.md`, then Phase 5 in `docs/implementation-plan.md` and only the doc sections it references.

**Phase-specific instructions**
- Port desk sensor (detection delay, vacancy hold), room count sensor (lag, noise), heartbeats, environment physics and BMS rules (observed values only), with the separate `environment` RNG stream.
- `mock-saas` service + `workplace_saas` DB; engine writes bookings/leave via `SaasClient`; `updated_since` pagination.
- Processor state for desks, rooms, floors, zones, HVAC. Port the sensor-lag/held-desk and live-vs-batch tests; add the SPEC §48 scripted flow test.

**Workflow**
1. Propose a plan: files to create/change, tests to write/port, anything unclear. Wait for my approval.
2. Implement in small commits. Stay inside this phase's scope.
3. Run `make test` and `make lint`; fix failures.
4. Update docs/decision log if anything deviated.
5. Report against each acceptance criterion (met / not met / how verified), then stop.
