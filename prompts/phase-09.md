# Phase 9 — Data quality + realism

_(Run `/clear` before pasting this. Use plan mode.)_

Read `CLAUDE.md`, then Phase 9 in `docs/implementation-plan.md` and only the doc sections it references.

**Phase-specific instructions**
- Enable anomalies, sensor failures, env nulls, `ACCESS_DENIED`, desk-sensor flicker, walk-in meetings, late joiners (config-driven, default off except in DQ runs).
- `DQ_EVENT_QUALITY`, `MART_DATA_QUALITY`, `MART_SENSOR_ACCURACY`; DQ panel; Simulation Debug page. Scenarios S6/S7 from `simulation-scenarios.md`.

**Workflow**
1. Propose a plan: files to create/change, tests to write/port, anything unclear. Wait for my approval.
2. Implement in small commits. Stay inside this phase's scope.
3. Run `make test` and `make lint`; fix failures.
4. Update docs/decision log if anything deviated.
5. Report against each acceptance criterion (met / not met / how verified), then stop.
