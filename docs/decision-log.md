# Decision Log

Newest first. Each entry: date, decision, reason, docs affected.

---

## 2026-09-25: Lightweight native-Windows infrastructure

**Decisions**
1. Develop natively on Windows in `D:\DT` (no WSL).
2. No Docker. PostgreSQL → SQLite (two files, keeping master and SaaS separate); Redis streams/state/pub-sub → in-process implementations behind the existing adapter interfaces.
3. Engine, event processor, API and pipeline trigger run in one `twin-server` process; mock-saas stays a separate process.
4. Local compute only. Snowflake/Azure (Phases 10–11) become optional.
5. uv workspace with a single lockfile; poethepoet replaces `make`.
6. Node 24 LTS instead of Node 20 (end-of-life April 2026).
7. GitHub for hosting and CI (Actions on ubuntu-latest); GitHub CLI optional.

**Reason:** the project is a proof-of-value simulation; the machine has IT restrictions on installing software; embedded components keep setup to a few user-level tools.

**Docs affected:** new `infrastructure.md`; overrides infrastructure sections of `architecture.md` and Docker/Makefile items in `implementation-plan.md`.
