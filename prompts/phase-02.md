# Phase 2 — Master data

_(Run `/clear` before pasting this. Use plan mode.)_

Read `CLAUDE.md`, then Phase 2 in `docs/implementation-plan.md` and only the doc sections it references.

**Phase-specific instructions**
- Port `reference/refsim/layout.py` and `master.py` into `services/simulation-engine/engine/generators/` with types and Pydantic models. Keep IDs and ordering identical.
- Alembic baseline for `master`, `config`, `sim`, `ops` per `data-model.md` v0.2 (reader types, restricted zones + `zone_access_rule`, room reader/panel flags, device types, `sim.floor_snapshot`).
- `make seed`; a test that regenerated CSVs equal `mock-data/master/*.csv` byte-for-byte for the default config.
- API read endpoints + pages: Employees, Teams, Rooms, Workspaces, Building View (static capacity).

**Workflow**
1. Propose a plan: files to create/change, tests to write/port, anything unclear. Wait for my approval.
2. Implement in small commits. Stay inside this phase's scope.
3. Run `make test` and `make lint`; fix failures.
4. Update docs/decision log if anything deviated.
5. Report against each acceptance criterion (met / not met / how verified), then stop.
