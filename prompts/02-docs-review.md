# Prompt 02 — Docs review (read-only)

Read all files in `docs/` and `CLAUDE.md`. Also run the reference tests (`cd reference && python -m pytest -q`) and skim `reference/refsim/engine.py` to understand the implemented algorithm.

Report, without changing code:
1. Contradictions between docs (cite file + section), and between docs and the reference implementation.
2. Anything Phase 1–3 needs that is underspecified.
3. Your answers/recommendations for the open questions in `implementation-plan.md` §5 — I'll confirm.
4. Risks you see for running everything locally on a laptop (resources, ports, Windows specifics).

Keep it concise with labeled sections. Then stop.
