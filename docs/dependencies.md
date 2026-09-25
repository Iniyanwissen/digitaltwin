# Dependencies

> Minimum versions. Pin exact versions with lockfiles (`uv.lock`, `package-lock.json`/`pnpm-lock.yaml`). Check for newer compatible releases when you start Phase 1.

## 1. Tooling

| Tool | Version | Why |
|---|---|---|
| Python | 3.12 | all services |
| uv | latest | Python env + dependency management (workspace) |
| Node.js | 20 LTS or 22 LTS | frontend |
| Docker Desktop / Engine + Compose v2 | recent | local stack |
| make | any | task runner (use `just` or npm scripts on Windows if preferred) |
| Git | any | branches per phase |

## 2. Reference simulator (`reference/`)

```
pyyaml>=6.0
tzdata>=2024.1        # Windows needs it for zoneinfo
redis>=5.0            # optional (RedisStreamSink)
pytest>=8.0           # dev
```

## 3. Python services

| Package | Min | engine | processor | api | mock-saas | pipeline | domain |
|---|---|:-:|:-:|:-:|:-:|:-:|:-:|
| pydantic | 2.7 | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| pydantic-settings | 2.3 | ✔ | ✔ | ✔ | ✔ | ✔ | |
| pyyaml | 6.0 | ✔ | | ✔ | | ✔ | ✔ |
| tzdata | 2024.1 | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| redis (redis-py, asyncio) | 5.0 | ✔ | ✔ | ✔ | | | |
| sqlalchemy | 2.0 | ✔ | ✔ | ✔ | ✔ | ✔ | |
| psycopg[binary] | 3.2 | ✔ | ✔ | ✔ | ✔ | ✔ | |
| alembic | 1.13 | | | ✔ (owns migrations) | ✔ | | |
| fastapi | 0.115 | | | ✔ | ✔ | | |
| uvicorn[standard] | 0.30 | | | ✔ | ✔ | | |
| httpx | 0.27 | ✔ (SaasClient) | | ✔ | | ✔ | |
| orjson | 3.10 | ✔ | ✔ | ✔ | | ✔ | |
| structlog | 24.1 | ✔ | ✔ | ✔ | ✔ | ✔ | |
| duckdb | 1.1 | | | ✔ (read) | | ✔ | |
| dbt-core + dbt-duckdb | 1.8 | | | | | ✔ | |
| numpy | 2.0 | optional (vectorised env physics at large scale) | | | | | |

Dev (workspace root): `pytest>=8`, `pytest-asyncio>=0.23`, `hypothesis>=6` (property tests for invariants), `ruff>=0.5`, `mypy>=1.10`, `testcontainers[postgres,redis]` (optional integration tests).

Deferred cloud: `azure-eventhub` or `aiokafka`, `azure-storage-file-datalake`, `azure-identity`, `snowflake-connector-python`, `dbt-snowflake`.

Example `services/api/pyproject.toml` dependencies block:

```toml
[project]
name = "workplace-api"
requires-python = ">=3.12"
dependencies = [
  "workplace-domain",
  "fastapi>=0.115", "uvicorn[standard]>=0.30", "pydantic>=2.7", "pydantic-settings>=2.3",
  "sqlalchemy>=2.0", "psycopg[binary]>=3.2", "alembic>=1.13", "redis>=5.0",
  "duckdb>=1.1", "httpx>=0.27", "orjson>=3.10", "structlog>=24.1", "pyyaml>=6.0", "tzdata>=2024.1",
]
```

## 4. Frontend (`frontend/`)

```json
{
  "dependencies": {
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "react-router-dom": "^6.26.0",
    "@tanstack/react-query": "^5.50.0",
    "@tanstack/react-virtual": "^3.8.0",
    "zustand": "^4.5.0",
    "recharts": "^2.12.0",
    "d3": "^7.9.0",
    "d3-sankey": "^0.12.3",
    "date-fns": "^3.6.0",
    "clsx": "^2.1.0",
    "lucide-react": "^0.400.0"
  },
  "optionalDependencies": {
    "pixi.js": "^8.2.0"
  },
  "devDependencies": {
    "typescript": "^5.5.0",
    "vite": "^5.3.0",
    "@vitejs/plugin-react": "^4.3.0",
    "tailwindcss": "^3.4.0",
    "postcss": "^8.4.0",
    "autoprefixer": "^10.4.0",
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "@types/d3": "^7.4.0",
    "@types/d3-sankey": "^0.12.4",
    "eslint": "^9.6.0",
    "typescript-eslint": "^7.16.0",
    "vitest": "^2.0.0",
    "@testing-library/react": "^16.0.0",
    "jsdom": "^24.1.0",
    "openapi-typescript": "^7.0.0"
  }
}
```

- `openapi-typescript` generates API types from FastAPI's OpenAPI schema (no hand-written DTOs).
- shadcn/ui is optional (open question in `implementation-plan.md`); if used, components are copied into the repo, not installed as a package.
- If the existing repo already uses React 19 / Tailwind 4 / Vite 6, keep them (Phase 0 decides); nothing in the spec depends on the older majors.

## 5. Docker images

`postgres:16-alpine`, `redis:7-alpine`, `python:3.12-slim` (services), `node:20-alpine` (frontend dev).
