# Phase 6 — Live dashboard

_(Run `/clear` before pasting this. Use plan mode.)_

Read `CLAUDE.md`, then Phase 6 in `docs/implementation-plan.md` and only the doc sections it references.

**Phase-specific instructions**
- WebSocket `/ws/live` implementing the frame contract in `live-streaming.md` §4 (versioned change log, 500 ms flush, resync, bounded queue).
- Pages: Overview, Live Workplace, Building View (live), Live Events (virtualised, filters, identity colours), Environmental Monitoring, Simulation Control — per `visualization-spec.md` §3–4.
- Hybrid charts H1 and H3. Use `reference/refsim/viewer/index.html` as the behavioural and visual reference.
- Test: KPI parity UI/API/Redis; no aggregate maths in components.

**Workflow**
1. Propose a plan: files to create/change, tests to write/port, anything unclear. Wait for my approval.
2. Implement in small commits. Stay inside this phase's scope.
3. Run `make test` and `make lint`; fix failures.
4. Update docs/decision log if anything deviated.
5. Report against each acceptance criterion (met / not met / how verified), then stop.
