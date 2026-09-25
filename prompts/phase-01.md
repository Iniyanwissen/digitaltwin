# Phase 1 — Foundation

_(Run `/clear` before pasting this. Use plan mode.)_

Read `CLAUDE.md`, then Phase 1 in `docs/implementation-plan.md` and only the doc sections it references.

**Phase-specific instructions**
- Follow Phase 1 in `docs/implementation-plan.md` and the repo layout in `docs/architecture.md` §10.
- `packages/domain`: Pydantic config schema for **all** of `config/simulation.yaml` (fail fast with readable errors), enums, event envelope + `IDENTITY_CLASS`/`SOURCE` tables and the privacy validator (port from `reference/refsim/common.py`), adapter Protocols.
- Frontend shell: navigation exactly as `visualization-spec.md` §3, tokens from §2, typed API client generated from OpenAPI (`openapi-typescript`), health indicator. Pages are empty states.
- Dependencies per `docs/dependencies.md`.

**Workflow**
1. Propose a plan: files to create/change, tests to write/port, anything unclear. Wait for my approval.
2. Implement in small commits. Stay inside this phase's scope.
3. Run `make test` and `make lint`; fix failures.
4. Update docs/decision log if anything deviated.
5. Report against each acceptance criterion (met / not met / how verified), then stop.
