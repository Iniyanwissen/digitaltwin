@echo off
rem Start the digital twin (API :8000 + UI :5173).
rem Reloads PATH from the registry so newly installed tools (uv, node) are found
rem even in a terminal that was opened before they were installed.
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')"`) do set "PATH=%%P"
cd /d "%~dp0"
where uv >nul 2>nul || (echo uv not found. Install it: winget install astral-sh.uv & exit /b 1)
where node >nul 2>nul || (echo Node.js not found. Install Node.js 24 LTS. & exit /b 1)
uv sync --quiet || exit /b 1
uv run poe dev %*
