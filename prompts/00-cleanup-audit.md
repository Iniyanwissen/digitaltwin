# Prompt 00 — Cleanup audit (read-only)

We're aligning this repo with the v0.2 design. Earlier sessions generated a data schema, mock data and UI views that don't follow the new docs.

Read `CLAUDE.md`, `docs/cleanup-guide.md`, then skim `docs/data-model.md`, `docs/event-model.md`, `docs/visualization-spec.md` §1–3 and `docs/architecture.md` §9 and §10.

Then **audit without changing any code**:
1. Inventory everything under the repo except `docs/`, `reference/`, `mock-data/`, `prompts/`, `.claude/`, `config/simulation.yaml`: database models, migrations, raw SQL, DB views, seed/mock scripts, JSON fixtures, API routes/schemas/services, frontend pages/components/charts/stores/mock files, docker/env files, tests.
2. For each item decide KEEP / ADAPT / REPLACE / DELETE using the decision rules in `docs/cleanup-guide.md` §3. Cite the doc section it conflicts with.
3. Map every existing frontend page to a nav item in `visualization-spec.md` §3 (or mark DELETE). Note which generic components (layout shell, cards, tables, theme) are worth keeping.
4. List terminology fixes needed (guide §5) with file references.
5. List any existing table/field/page you think the new docs are **missing** and should be added — with a reason. Don't add them; just propose.
6. Propose the commit sequence for execution (guide §4).

Write all of this to `docs/cleanup-report.md` using the table format in the guide. Then stop and summarise the top decisions and anything you're unsure about. Do not delete or edit other files.
