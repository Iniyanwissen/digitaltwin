# Phase 8A — History + warehouse core

_(Run `/clear` before pasting this. Use plan mode.)_

Read `CLAUDE.md`, then Phase 8A in `docs/implementation-plan.md` and only the doc sections it references.

**Phase-specific instructions**
- Engine BATCH mode with parallel day workers, `GENERATE_HISTORY`, BatchSink; pipeline-runner (archive loader, master snapshots, SaaS incremental loader, DuckDB build-and-swap, `ops` tables).
- dbt-duckdb RAW → STAGING → CORE, including `FACT_AREA_ACCESS`, `FACT_ROOM_CHECK_IN`, interval facts, `FACT_SPACE_UTILIZATION_15MIN`. `mock-data/raw` must load unchanged as the first fixture.
- Reconciliation + idempotency tests.

**Workflow**
1. Propose a plan: files to create/change, tests to write/port, anything unclear. Wait for my approval.
2. Implement in small commits. Stay inside this phase's scope.
3. Run `make test` and `make lint`; fix failures.
4. Update docs/decision log if anything deviated.
5. Report against each acceptance criterion (met / not met / how verified), then stop.
