# Phase 8B — Analytics UI

_(Run `/clear` before pasting this. Use plan mode.)_

Read `CLAUDE.md`, then Phase 8B in `docs/implementation-plan.md` and only the doc sections it references.

**Phase-specific instructions**
- All marts in `data-model.md` §5.4 v0.2 incl. `MART_TEAM_COLLAB_NETWORK`, `MART_TEAM_COLOCATION`, `MART_MOVEMENT_FLOW`.
- Pages: Historical Analytics, Real Estate Analytics, Teams (N1, N2), Rooms (H2 booked-vs-used Gantt), heat maps, Data Pipeline, Data Sources; hybrid charts H2, H4–H7; movement Sankey N3.
- Metric parity test (domain vs dbt).

**Workflow**
1. Propose a plan: files to create/change, tests to write/port, anything unclear. Wait for my approval.
2. Implement in small commits. Stay inside this phase's scope.
3. Run `make test` and `make lint`; fix failures.
4. Update docs/decision log if anything deviated.
5. Report against each acceptance criterion (met / not met / how verified), then stop.
