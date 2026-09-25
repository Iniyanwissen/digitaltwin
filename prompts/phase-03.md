# Phase 3 — Simulation core

_(Run `/clear` before pasting this. Use plan mode.)_

Read `CLAUDE.md`, then Phase 3 in `docs/implementation-plan.md` and only the doc sections it references.

**Phase-specific instructions**
- Port clock, scheduler (priorities + lazy token cancellation), planner (calendar, leave, team-correlated attendance with weekday calibration), person state machine, activity model, desk assignment and meeting scheduler from `reference/refsim/engine.py`.
- Clock protocol: VirtualClock (batch) and ScaledClock with night skip (see `live-streaming.md` §3).
- Redis control channel + `simulation_run` tracking + Simulation Control page (truth counters with dashed borders).
- Port tests: truth sequences, non-negative counts, reproducibility, different seeds, weekday calibration.

**Workflow**
1. Propose a plan: files to create/change, tests to write/port, anything unclear. Wait for my approval.
2. Implement in small commits. Stay inside this phase's scope.
3. Run `make test` and `make lint`; fix failures.
4. Update docs/decision log if anything deviated.
5. Report against each acceptance criterion (met / not met / how verified), then stop.
