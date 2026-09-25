# Prompt 01 — Cleanup execution

`docs/cleanup-report.md` is approved (I may have edited decisions — follow the file, not your earlier suggestions).

Execute it in the order of `docs/cleanup-guide.md` §4, **one commit per step** (`cleanup: <step>`):
1. Frontend: remove mock files, random generators, hard-coded arrays; empty states instead.
2. Frontend: routes/navigation exactly per `visualization-spec.md` §3; delete unmapped pages; design tokens from §2 into Tailwind config/CSS variables; restyle kept primitives.
3. API: remove mock endpoints; add `501` stubs only where a kept page needs one.
4. Database: remove old ORM models, migrations and DB views. Don't create the new schema yet (Phase 1/2 does). Tell me to run `docker compose down -v`.
5. Remove seed/mock scripts. 6. Align compose services with `architecture.md` §9 (placeholders are fine). 7. Remove tests for deleted code.

After each step: build passes and `docker compose up` still starts. At the end run the verification checklist in guide §6, update `docs/cleanup-report.md` with the final status, record approved additions in `docs/decision-log.md`, and give me a short summary. Do not start Phase 1.
