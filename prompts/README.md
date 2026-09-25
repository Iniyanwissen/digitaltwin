# Prompts for Claude Code (VS Code)

Use them **in order**, one per session. Start each with `/clear`, use **plan mode** (Shift+Tab) for anything that changes code, and approve the plan before implementation.

| Step | File | When |
|---|---|---|
| 1 | `00-cleanup-audit.md` | After copying the kit into the repo. Produces `docs/cleanup-report.md`. **Review it.** |
| 2 | `01-cleanup-execute.md` | After you've approved/edited the report. |
| 3 | `02-docs-review.md` | Claude checks the docs for gaps/contradictions and asks the open questions. |
| 4 | `phase-01.md` … `phase-10.md` | One phase per session. Tag `phase-N` after each. |
| any | `/verify` (slash command) | End of every phase. |

Shortcut: `/phase 3` runs the generic phase workflow from `.claude/commands/phase.md`; the phase files add phase-specific instructions — paste them when you want more control.

Tips
- If a session gets long, ask Claude to write progress into `docs/progress.md`, then `/clear` and continue from it.
- When Claude proposes something not in the docs, ask it to add a decision-log entry first.
- Keep `reference/` untouched; it's the behaviour oracle.
