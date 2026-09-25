# Smart Workplace Digital Twin: working rules

Proof-of-value office digital twin. A seeded discrete-event simulation produces ground truth; simulated
data sources observe it; everything downstream consumes only observed events.

## Read first
- `docs/infrastructure.md` (overrides infra parts of the other docs), `docs/decision-log.md`
- `docs/architecture.md`, `docs/event-model.md`, `docs/data-model.md`, `docs/simulation-engine.md`
- `docs/implementation-plan.md`: phases and acceptance criteria

## Layout
- `packages/domain/workplace_domain`: config schema, enums, event envelope + identity table, adapter Protocols
- `services/twin-server/twin_server`: `api/`, `engine/`, `processor/`, `adapters/`, `db/` in one process
- `frontend/`: React + TS + Vite + Tailwind; sidebar sections defined in `src/app/navigation.ts`
- `config/*.yaml`: all business numbers (`simulation.yaml`, `organization.yaml`, `layout_presets.yaml`, `layouts/`)
- `twin_server/engine/generators/`: master data generators; `twin_server/masterdata/`: store, reader, service

## Commands (Windows, from repo root)
- `uv run poe dev`: server on :8000 + UI on :5173
- `uv run poe test`, `uv run poe lint`, `uv run poe fmt`, `uv run poe doctor`
- `uv run poe seed [--force]`: regenerate master data; `uv run poe layout --preset medium`: rewrite the layout file
- Schema change: edit `twin_server/db/tables.py`, then `uv run python -m twin_server revision -m "..." --rev-id 000N_name`
- Use `npm.cmd` (not `npm`) in PowerShell if script execution is restricted

## Rules
- Randomness only through `RngFactory` (named seeded streams). `poe check-rng` enforces this.
- No hardcoded counts, probabilities or layouts: read from `config/`. New keys get a YAML comment.
- Identity rule: ANONYMOUS events never carry person identifiers or correlation ids (enforced in
  `EventEnvelope`). Truth events never reach operational state or UI (except Simulation Debug).
- Sim time for business timestamps; wall time only for ops metrics.
- No business logic in FastAPI route handlers (use `api/services.py` or domain services) or in
  React components (derived numbers come from the API; the UI formats and renders).
- Depend on Protocols in `workplace_domain.interfaces`, not concrete adapters.
- mypy strict on `workplace_domain` and `twin_server.engine`.
- Per phase: plan → approval → implement → `poe test` + `poe lint` green → update docs and
  `docs/decision-log.md` → summarize.
