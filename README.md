# Smart Workplace Digital Twin

A simulated smart office: employees, desks, rooms and sensors, with a live digital twin and analytics.
Proof of value, runs locally on Windows with no Docker.

## Prerequisites
Git, [uv](https://docs.astral.sh/uv), Node.js 24 LTS. Python 3.12 is installed by uv.

## Run
```powershell
.\dev.cmd               # API on http://localhost:8000, UI on http://localhost:5173
```
`dev.cmd` reloads PATH, syncs Python dependencies and runs `uv run poe dev`. It works in a terminal
opened before uv/Node were installed and is not affected by PowerShell's script execution policy.
The first run installs frontend packages and creates `data/workplace.db`.

## Develop
```powershell
uv run poe test         # Python + frontend tests
uv run poe lint         # ruff, mypy, RNG guard, eslint, tsc
uv run poe fmt          # format Python
uv run poe doctor       # check tools and ports
```

Design docs are in [docs/](docs/). Start with [docs/infrastructure.md](docs/infrastructure.md).
