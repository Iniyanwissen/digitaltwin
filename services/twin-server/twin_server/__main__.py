"""CLI: `python -m twin_server [serve|migrate] [--reload]`."""

from __future__ import annotations

import argparse
import sys

import uvicorn

from twin_server.db import run_migrations
from twin_server.settings import Settings
from workplace_domain.config import ConfigError, load_simulation_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="twin-server")
    parser.add_argument("command", nargs="?", default="serve", choices=["serve", "migrate"])
    parser.add_argument("--reload", action="store_true", help="auto-reload on code changes")
    args = parser.parse_args(argv)

    settings = Settings()
    try:
        load_simulation_config(settings.config_dir)
    except ConfigError as exc:
        print(f"\nConfiguration error - twin-server not started.\n\n{exc}\n", file=sys.stderr)
        return 2

    run_migrations(settings.resolved_database_url)
    if args.command == "migrate":
        print("Database is up to date.")
        return 0

    uvicorn.run(
        "twin_server.api:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        reload=args.reload,
        reload_dirs=["services/twin-server/twin_server", "packages/domain/workplace_domain"]
        if args.reload
        else None,
        log_level=settings.log_level.lower(),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
