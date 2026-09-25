# Smart Workplace Digital Twin: working rules

Event-driven office simulator: synthetic people move through a building; badge readers, workstations,
room panels and anonymous sensors report what they would really see; a pipeline turns events into live
state and analytics; a React digital twin shows it. Proof of value, **everything local**, native
Windows, no Docker.

## Read first (only what the current task needs)
- `docs/infrastructure.md`: **overrides** every Docker / PostgreSQL / Redis / `make` mention in other docs
- `docs/decision-log.md`: latest decisions (hybrid direction, 2026-09-26)
- `docs/architecture.md`, `docs/event-model.md`, `docs/data-model.md`: contracts
- `docs/simulation-engine.md`; **`reference/refsim/` is the working implementation to port**
- `docs/live-streaming.md`, `docs/visualization-spec.md`: live updates and screen → data mapping
- `docs/simulation-scenarios.md`, `docs/implementation-plan.md`, `docs/mock-data.md`

## Layout
- `packages/domain/workplace_domain`: config schema, enums, ids, models, RNG, event envelope + identity table, adapter Protocols
- `services/twin-server/twin_server`: `api/`, `engine/` (incl. `generators/`), `processor/`, `masterdata/`, `adapters/`, `db/` in one process
- `frontend/`: React + TS + Vite + Tailwind; sidebar sections in `src/app/navigation.ts`, pages in `src/app/pages.tsx`
- `config/`: the app's config (`simulation.yaml`, `organization.yaml`, `layout_presets.yaml`, `layouts/`)
- `reference/`: kit reference simulator + viewer (own config in `reference/config/`); port from it, never import it
- `mock-data/`: kit sample data (fixture/reference only); `prompts/`, `.claude/commands/`: kit prompts

## Commands (Windows, from repo root)
- `.\dev.cmd` (or `uv run poe dev`): server on :8000 + UI on :5173
- `uv run poe test`, `uv run poe lint`, `uv run poe fmt`, `uv run poe doctor`
- `uv run poe seed [--force]`, `uv run poe layout --preset medium`
- Schema change: edit `twin_server/db/tables.py`, then `uv run python -m twin_server revision -m "..." --rev-id 000N_name`
- Reference: `cd reference; ..\.venv\Scripts\python -m refsim serve --speed 60` (http://127.0.0.1:8765), tests: `..\.venv\Scripts\python -m pytest -q`
- Use `npm.cmd` (not `npm`) in PowerShell if script execution is restricted

## Non-negotiables
1. **Truth vs observed.** Ground truth never reaches operational views, processor state or the warehouse (except explicit truth/Simulation View paths, separately labelled).
2. **Privacy.** ANONYMOUS events never carry person identifiers or correlation ids (enforced in `EventEnvelope`). Desk identity only from workstation login.
3. **Config, not code.** No hardcoded counts, probabilities or layouts. New keys get a YAML comment.
4. **Determinism.** Same config + seed → same world. Randomness only through `RngFactory` (`poe check-rng`). Never iterate sets for decisions.
5. **Backend computes, frontend draws.** No business logic in FastAPI route handlers or React components.
6. **Docs are the contract.** Only build tables, events, endpoints and pages described in `docs/`; propose additions in `docs/decision-log.md` first.
7. **No mock data outside the engine.**
8. **Port, don't reinvent.** When `reference/refsim` covers something, port it (typed, tested) with its tests from `reference/tests/`.
9. Depend on Protocols in `workplace_domain.interfaces`; mypy strict on `workplace_domain` and `twin_server.engine`.

## Workflow per phase
Plan → approval → implement → `poe test` + `poe lint` green → update docs and `docs/decision-log.md`
→ report against acceptance criteria → commit → stop.

## UI
Directory and other pages: light theme. Live Simulation screen: dark tokens from `visualization-spec.md` §2.
