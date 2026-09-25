# Phase 7 — Digital twin visuals

_(Run `/clear` before pasting this. Use plan mode.)_

Read `CLAUDE.md`, then Phase 7 in `docs/implementation-plan.md` and only the doc sections it references.

**Phase-specific instructions**
- Per `visualization-spec.md` §5: isometric building, 2D floor twin with cached static layer, overlays (occupancy, temperature, HVAC, bookings), desk/room/zone panels, Simulation View dots (separate truth endpoint/channel, tweening), time scrubber on `sim.floor_snapshot` (processor writes one row per floor per sim-minute).
- Performance: ≥ 50 fps at 60x medium; dirty-flag rendering; no per-desk DOM nodes.
- Tests: desk identity only from login; truth never in Operational View; scrubber restore < 200 ms.

**Workflow**
1. Propose a plan: files to create/change, tests to write/port, anything unclear. Wait for my approval.
2. Implement in small commits. Stay inside this phase's scope.
3. Run `make test` and `make lint`; fix failures.
4. Update docs/decision log if anything deviated.
5. Report against each acceptance criterion (met / not met / how verified), then stop.
