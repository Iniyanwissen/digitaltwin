# Cleanup Guide: Aligning the Existing Repo with v0.2

> Purpose: the repo already contains schema, mock data and UI views generated earlier by Claude Code in VS Code that don't follow these docs. This guide removes or remaps them **safely and with your approval**, before Phase 1.
> Prompts: `prompts/00-cleanup-audit.md` → review → `prompts/01-cleanup-execute.md`.

---

## 1. Rules

1. **Docs win.** `data-model.md`, `event-model.md`, `visualization-spec.md` and `architecture.md` are the target. Existing code that contradicts them is adapted or removed, not "kept for later".
2. **Audit first, delete later.** Nothing is deleted until `docs/cleanup-report.md` is approved.
3. **No mock data outside the engine.** Random/faker/hard-coded data in the API or frontend is deleted. The only data sources are the simulation engine, the generated master data and the mock SaaS.
4. **Keep generic, replace specific.** Generic UI building blocks (layout shell, buttons, cards, tables, modal, theme setup) are usually worth keeping. Pages, charts and schemas tied to the old data shape are replaced.
5. **One commit per cleanup step**, on a dedicated branch.

---

## 2. Before you start (manual, 5 minutes)

```bash
git checkout -b cleanup/align-v02
git tag pre-cleanup                      # easy way back
docker compose down                      # if running
# optional: keep old data for reference
docker compose run --rm postgres pg_dump ... > backups/pre-cleanup.sql
```

Copy the kit into the repo root (merge; kit files overwrite same-named files):

| Kit folder/file | Repo location |
|---|---|
| `CLAUDE.md` | `CLAUDE.md` (replace; re-add anything project-specific you had) |
| `docs/*` | `docs/` (keep your `SPEC.md`) |
| `config/simulation.yaml` | `config/simulation.yaml` |
| `reference/` | `reference/` |
| `mock-data/` | `mock-data/` (add `mock-data/raw/` to `.gitignore` if you don't want 26 MB in git; regenerate with the CLI) |
| `prompts/` | `prompts/` |
| `.claude/commands/` | `.claude/commands/` |

Then check the reference runs: `cd reference && pip install -r requirements.txt && python -m refsim serve` → http://127.0.0.1:8765.

---

## 3. Audit (prompt 00)

Claude Code inventories everything and writes `docs/cleanup-report.md` with this table per area:

| Path / object | Kind | What it does now | Conflicts with (doc §) | Decision | Target / notes |
|---|---|---|---|---|---|

**Areas:** database (ORM models, migrations, raw SQL, views), seed/mock scripts and JSON fixtures, backend routes/schemas/services, frontend pages/components/charts/stores/mock files, config/env/docker, tests.

**Decision rules:**

| Found | Decision |
|---|---|
| Table/model matching a `data-model.md` table with compatible columns | **ADAPT** (rename/add columns in the new baseline) |
| Table/model not in `data-model.md` | **DELETE** (or propose it as an addition in the report, with a reason) |
| Existing Alembic/SQL migrations | **REPLACE** with one new baseline migration (no production data exists) |
| DB views/materialised views for dashboards | **DELETE** — aggregates come from the processor (live) and dbt marts (history) |
| Faker/random seed scripts, mock JSON | **DELETE** — replaced by `refsim`-ported generators and `mock-data/` |
| API endpoints returning generated/random data | **DELETE**, or **ADAPT** to the endpoint list in `visualization-spec.md` §3 returning `501 Not Implemented` until their phase |
| Frontend page matching a nav item in `visualization-spec.md` §3 | **ADAPT** (keep layout, remove local data, wire to typed API client later) |
| Frontend page not in the nav | **DELETE** |
| Chart/widget computing aggregates in the browser | **REPLACE** (backend computes) |
| Hard-coded arrays of employees/rooms/desks in components | **DELETE** |
| Generic UI primitives, theme, routing, layout shell | **KEEP** (restyle to tokens) |
| Docker/compose services not in `architecture.md` §9 | **DELETE** or **ADAPT** |

The report also lists **terminology fixes** (see §5) and ends with the proposed commit sequence. **Stop and review it.** Edit decisions directly in the file if you disagree.

---

## 4. Execute (prompt 01)

Order matters so the app keeps starting between commits:

1. **Frontend data removal**: delete mock files, random generators and hard-coded arrays; pages show an empty state ("Waiting for simulation data").
2. **Frontend structure**: routes/nav exactly as `visualization-spec.md` §3; delete unmapped pages; move design tokens into Tailwind config / CSS variables (§2 of that doc).
3. **API**: remove mock endpoints; add stubs (`501`) for mapped endpoints only where a page needs one to render.
4. **Database**:
   ```bash
   docker compose down -v                       # drops old volumes (data is synthetic)
   rm services/*/alembic/versions/*.py          # or wherever migrations live
   # new baseline created in Phase 1/2 from data-model.md
   ```
   Delete old ORM models and DB views. Leave an empty `master/config/sim/ops` schema plan to Phase 2.
5. **Seed/mock scripts**: delete; `make seed` is recreated in Phase 2.
6. **Config/infra**: compose services per `architecture.md` §9; `.env.example` updated.
7. **Tests**: delete tests for removed code; keep tests for kept primitives.

After each step: app builds, `docker compose up` works, commit with message `cleanup: <step>`.

---

## 5. Terminology alignment (UI labels and code names)

Old generated UIs usually blur these. Use the new names everywhere:

| Old / ambiguous | Use instead | Source |
|---|---|---|
| "occupancy" (one number) | **Employees inside** (badge) · **Desk occupancy** (sensor) · **Estimated headcount** (sensors) | ACCESS_* · OCCUPANCY_CHANGED · desks + room counts |
| "attendance" | **Daily attendance** = unique employees with ACCESS_IN per day | ACCESS_IN |
| "check-in" | **Building entry** (ACCESS_IN) or **Room check-in** (panel) | ACCESS_IN / ROOM_CHECK_IN |
| "users" / "staff" | **Employees** (and later **Visitors**) | master.employee |
| "seats" / "spots" | **Workspaces / desks** | master.workspace |
| "available desk" = not occupied | **Available** = not occupied **and** not held (not logged in) | sensor + login |
| "space" | **Zone**, **Room**, or **Common area** (be specific) | master.zone / room |
| "booking used" | **Booked**, **Checked-in**, **Sensor-occupied** (three separate facts) | SaaS / panel / sensor |
| "utilisation %" without denominator | say which: desk util (÷ desks), room util (÷ bookable hours), building util (÷ max occupancy) | marts |
| person shown on desk from sensor | **never** — identity on a desk only from workstation login | privacy rule |

---

## 6. Verification checklist

```bash
rg -n "Math.random|faker|Faker|mockData|dummy|lorem" frontend/src services packages   # expect no hits outside tests/reference
rg -n "<old table names from the report>" .                                           # expect no hits
docker compose up --build                                                             # all services healthy
```

- [ ] `docs/cleanup-report.md` committed with final decisions.
- [ ] Navigation matches `visualization-spec.md` §3 exactly.
- [ ] No DB views/tables outside `data-model.md` (or approved additions recorded in `docs/decision-log.md`).
- [ ] No aggregates computed in React components.
- [ ] Old migrations removed; volumes recreated.
- [ ] `git diff pre-cleanup --stat` reviewed.
- [ ] Merge branch, tag `phase-0`.
