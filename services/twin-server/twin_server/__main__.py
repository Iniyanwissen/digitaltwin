"""CLI: python -m twin_server [serve|migrate|seed|layout|revision]."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import uvicorn

from twin_server.db import create_db_engine, create_revision, run_migrations
from twin_server.settings import Settings
from workplace_domain.config import (
    ConfigError,
    WorkplaceConfig,
    load_layout_presets,
    load_workplace_config,
)


def _serve(settings: Settings, reload: bool) -> int:
    uvicorn.run(
        "twin_server.api:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        reload=reload,
        reload_dirs=["services/twin-server/twin_server", "packages/domain/workplace_domain"]
        if reload
        else None,
        reload_includes=["*.py", "*.yaml"] if reload else None,
        log_level=settings.log_level.lower(),
        # Don't let keep-alive/WebSocket clients block shutdown and auto-reload.
        timeout_graceful_shutdown=settings.shutdown_timeout_s,
    )
    return 0


def _seed(settings: Settings, config: WorkplaceConfig, force: bool) -> int:
    from twin_server.masterdata.service import MasterDataService

    engine = create_db_engine(settings.resolved_database_url)
    try:
        result = MasterDataService(engine, config).ensure(force=force)
    finally:
        engine.dispose()
    if not result.generated:
        print("Master data is already current for this config and seed (use --force).")
        return 0
    print(f"Generated master data version {result.version_id}:")
    for name, count in result.counts.items():
        print(f"  {name:<22} {count:>6}")
    return 0


def _layout(settings: Settings, preset_name: str, out: Path | None) -> int:
    from twin_server.engine.generators.layout_generator import generate_layout
    from twin_server.layout_yaml import dump_layout

    presets = load_layout_presets(settings.config_dir)
    if preset_name not in presets.presets:
        print(f"Unknown preset {preset_name!r}; choose from {sorted(presets.presets)}")
        return 2
    layout = generate_layout(presets.presets[preset_name], presets)
    target = out or settings.config_dir / "layouts" / "building_a.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    header = (
        f"# Generated from preset '{preset_name}' (config/layout_presets.yaml).\n"
        "# Safe to edit by hand. Units are metres. Desk blocks expand into individual desks.\n"
    )
    target.write_text(header + dump_layout(layout), encoding="utf-8")
    print(f"Wrote {target} ({len(layout.building.floors)} floors)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="twin-server")
    sub = parser.add_subparsers(dest="command")
    serve = sub.add_parser("serve", help="run the API server (default)")
    serve.add_argument("--reload", action="store_true", help="auto-reload on code changes")
    sub.add_parser("migrate", help="apply database migrations")
    seed = sub.add_parser("seed", help="generate master data from config")
    seed.add_argument("--force", action="store_true", help="regenerate even if current")
    layout = sub.add_parser("layout", help="write a layout file from a preset")
    layout.add_argument("--preset", default="medium")
    layout.add_argument("--out", type=Path)
    revision = sub.add_parser("revision", help="autogenerate a migration from db/tables.py")
    revision.add_argument("-m", "--message", required=True)
    revision.add_argument("--rev-id", help="revision id, e.g. 0003_add_x")
    args = parser.parse_args(argv)
    command = args.command or "serve"

    settings = Settings()
    if command == "layout":
        try:
            return _layout(settings, args.preset, args.out)
        except ConfigError as exc:
            print(f"\n{exc}\n", file=sys.stderr)
            return 2
    try:
        config = load_workplace_config(settings.config_dir)
    except ConfigError as exc:
        print(f"\nConfiguration error - twin-server not started.\n\n{exc}\n", file=sys.stderr)
        return 2

    if command == "revision":
        create_revision(settings.resolved_database_url, args.message, args.rev_id)
        return 0
    run_migrations(settings.resolved_database_url)
    if command == "migrate":
        print("Database is up to date.")
        return 0
    if command == "seed":
        return _seed(settings, config, args.force)
    return _serve(settings, getattr(args, "reload", False))


if __name__ == "__main__":
    sys.exit(main())
