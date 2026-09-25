# Infrastructure

> Status: DRAFT v0.1. Overrides the infrastructure parts of `architecture.md` (§3 Sources/Processing boxes, §6 local implementations, §7, §8.3, §9) and the Docker/Makefile items in `implementation-plan.md` §1 and Phase 1.
> Rationale: this project is a proof-of-value simulation, not a production system. See `decision-log.md`.

---

## 1. Principles

- **Native Windows, no Docker.** Everything runs as plain processes on the developer machine in `D:\DT`.
- **Embedded over server infrastructure.** SQLite, DuckDB and in-process queues replace PostgreSQL and Redis.
- **Adapter interfaces are kept.** Every replaced component sits behind the Protocols in `architecture.md` §6, so PostgreSQL, Redis, Event Hubs, ADLS or Snowflake adapters can be added later without changing callers.
- **Local compute only.** Cloud adapters (Phases 10–11) are optional add-ons.
- **No admin rights needed at runtime.** Tools are installed per user; the app binds only to localhost ports.

---

## 2. Component Mapping

| Architecture doc | Light implementation | Notes |
|---|---|---|
| PostgreSQL `workplace` (master, config, sim, ops) | SQLite `data/workplace.db` | SQLAlchemy 2 + Alembic (batch mode for ALTERs). `jsonb` → JSON, `text[]`/`smallint[]` → JSON arrays. |
| PostgreSQL `workplace_saas` | SQLite `data/saas.db` | Owned only by mock-saas. Reached only via its REST API (§8.4 preserved). |
| Redis Streams (event bus) | `InMemoryPublisher` / `InMemoryConsumer` (asyncio queues per stream) | Same stream names as `event-model.md` §6. |
| Redis current state | `InMemoryStateStore` | Same key/field model as `data-model.md` §4. |
| Redis pub/sub (control, status, live feed) | In-process calls + async broadcast to WebSocket clients | |
| Raw archive | `LocalFileRawArchive` → `data/raw/` | Unchanged layout (`event-model.md` §9). |
| Warehouse | DuckDB `data/warehouse/warehouse.duckdb` + dbt-duckdb | Unchanged. |
| Docker Compose / Makefile | `uv run poe <task>` | poethepoet task runner, cross-platform. |

---

## 3. Runtime Topology

```
uv run poe dev   → starts:
  twin-server   FastAPI  :8000   api + simulation engine + event processor + pipeline trigger
  mock-saas     FastAPI  :8100   HR / bookings / visitors / special events (own SQLite)
  frontend      Vite     :5173   React UI
```

- Module boundaries stay as designed (`engine/`, `processor/`, `api/`, `pipeline/`); they communicate only through the adapter interfaces, in one process.
- mock-saas stays a separate process so it behaves like a genuinely external HTTP system.
- Historical generation uses `ProcessPoolExecutor` day workers writing directly to the raw archive.
- **DuckDB swap on Windows:** Windows cannot rename over an open file. The pipeline builds `warehouse_build.duckdb` (dbt subprocess), then the server takes a lock, closes its read connections, `os.replace`s the file, and reopens.
- **State recovery (optional):** on startup, current state can be rebuilt by replaying today's raw archive for the active run. This replaces the Redis consumer-group restart test.
- Accepted trade-offs: no crash durability for in-flight events; no process isolation between engine, processor and API.

---

## 4. Repository Layout Changes

```
D:\DT\
├── pyproject.toml          # uv workspace root + poe tasks
├── uv.lock                 # single lockfile for all Python members
├── .gitattributes          # * text=auto eol=lf
├── packages/domain/        # workplace_domain (unchanged)
├── services/
│   ├── twin-server/        # api + engine + processor + pipeline packages
│   └── mock-saas/
├── frontend/
├── config/                 # unchanged
├── data/                   # gitignored: workplace.db, saas.db, raw/, warehouse/
└── docs/
```

`services/api`, `services/simulation-engine`, `services/event-processor` and `services/pipeline-runner` from `architecture.md` §10 become packages inside `twin-server`.

---

## 5. Toolchain

| Tool | Version | Purpose |
|---|---|---|
| Git for Windows | 2.5x | version control; bundled Git Credential Manager handles GitHub login |
| uv | ≥ 0.12 | Python version + dependency management, workspace, task running |
| Python | 3.12 (via uv) | backend |
| Node.js | 24 LTS | frontend (Node 20 is end-of-life since April 2026) |
| GitHub CLI | optional | convenience only |

Python dependencies (installed by uv into the project venv, not system-wide): fastapi, uvicorn, pydantic, sqlalchemy, alembic, httpx, numpy, xxhash, structlog, duckdb, dbt-duckdb, pyyaml, pytest, ruff, mypy, poethepoet.
Frontend dependencies (npm, project-local): react, vite, typescript, tailwindcss, recharts, eslint, vitest.

---

## 6. Poe Tasks (replace Makefile targets)

| Task | Does |
|---|---|
| `dev` | start all three processes |
| `test` / `lint` / `fmt` | pytest + vitest / ruff + mypy + eslint + tsc / formatters |
| `migrate` | Alembic upgrade for both SQLite databases |
| `seed` | generate master data from config + seed |
| `generate-history` | batch-generate N days (`--days 30`) |
| `dbt-build` | load RAW + dbt build + swap |
| `reset` | delete `data/` runtime files |
| `doctor` | check tool versions, free ports (8000, 8100, 5173), writable `data/` |

---

## 7. CI (GitHub Actions)

One workflow on `ubuntu-latest` (free minutes, and it catches Windows-only path assumptions):
- Python: `uv sync --frozen`, ruff, mypy, pytest
- Frontend: `npm ci`, eslint, tsc, vitest
- RNG guard: fail on `random` / `numpy.random` use outside `RngFactory`

---

## 8. Resource Notes

- Expected footprint: ~1–1.5 GB RAM for the three processes at medium scale, plus up to ~3 GB for DuckDB during pipeline builds (`memory_limit=3GB`).
- In-memory streams are bounded (default 200k entries per stream, configurable); the raw archive is the durable history.
