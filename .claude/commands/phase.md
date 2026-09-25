---
description: Plan and implement one phase from docs/implementation-plan.md
argument-hint: <phase number, e.g. 3 or 8a>
---
Implement Phase $ARGUMENTS of the Smart Workplace Digital Twin.

1. Read `CLAUDE.md`, Phase $ARGUMENTS in `docs/implementation-plan.md`, and only the doc sections it references. If `prompts/phase-$ARGUMENTS.md` (zero-padded) exists, follow its phase-specific instructions too.
2. Where `reference/refsim/` already implements the behaviour, port it and its tests from `reference/tests/`.
3. Propose a plan (files, tests, open questions) and wait for my approval before writing code.
4. Implement in small commits; stay within the phase scope; no mock data outside the engine; no aggregate maths in the frontend.
5. Run tests and lint, then report against each acceptance criterion and stop.
