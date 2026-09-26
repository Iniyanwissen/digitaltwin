# v0.3 prompt pack — light theme, real floor plan, crowd-driven ESG

Copy the pack into the repo root first:

| Pack path | Repo path |
|---|---|
| `docs/floor-twin-design-v2.md`, `docs/environment-and-esg.md` | `docs/` |
| `design/floor-plan-v2.json`, `design/floor-twin-design.html` | `design/` |
| `config/esg-additions.yaml` | `config/` (merged in step 1) |
| `prompts/v03-*.md` | `prompts/` |

Run in order, one session each (`/clear` between), plan mode on, approve each plan, `/verify` at the end:

| # | Prompt | Outcome |
|---|---|---|
| 1 | `v03-00-docs-merge.md` | Existing docs, config and decision log updated to v0.3; nothing else changes |
| 2 | `v03-01-light-theme.md` | Token-based light/dark theme, light default, toggle persisted |
| 3 | `v03-02-floor-plan.md` | Layout from `floor-plan-v2.json` (metres), new twin renderer, decluttered layers |
| 4 | `v03-03-crowd-environment-data.md` | Crowd-driven temperature/CO₂ per area, trend, energy intervals, regenerated mock data |
| 5 | `v03-04-esg-automation-kpis.md` | Lighting + meeting-room automation, ESG KPIs, sustainability panel, automation log, marts |

Demo check after step 5: run at 60×, open Floor 2, switch to Temperature, watch a crowded small room turn orange with ▲, then a "Cooling increased" / "ventilation boosted" action and ▼ within ~15 sim-minutes; the sustainability panel updates.
