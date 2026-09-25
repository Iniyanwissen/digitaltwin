# Phase 10 — Scenario simulations

_(Run `/clear` before pasting this. Use plan mode.)_

Read `CLAUDE.md`, then Phase 10 in `docs/implementation-plan.md` and only the doc sections it references.

**Phase-specific instructions**
- Implement `simulation-scenarios.md` S1–S5: config overlays + baseline cache (same seed), `simulation_run` scenario columns, comparison endpoint, Scenario Simulator and Capacity Planning pages (H7 bullet charts), evacuation replay in Simulation View.
- Test: SPEC §3 example explained per floor; scenario runs reproducible by seed.

**Workflow**
1. Propose a plan: files to create/change, tests to write/port, anything unclear. Wait for my approval.
2. Implement in small commits. Stay inside this phase's scope.
3. Run `make test` and `make lint`; fix failures.
4. Update docs/decision log if anything deviated.
5. Report against each acceptance criterion (met / not met / how verified), then stop.
