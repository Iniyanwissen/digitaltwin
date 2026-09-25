"""Reference simulator CLI.

  python -m refsim master  [--preset medium] [--out mock-data/master]
  python -m refsim history [--days 7] [--start 2026-09-21] [--out mock-data]
  python -m refsim stream  [--speed 60] [--date 2026-09-28] [--hours 2]      # JSON lines on stdout
  python -m refsim serve   [--speed 60] [--date 2026-09-28] [--port 8765]    # live viewer
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import date
from pathlib import Path

from .common import REPO_ROOT, load_config
from .engine import Engine
from .layout import generate_layout
from .master import generate_master, write_master
from .sinks import ArchiveSink, StdoutSink


def build(args):
    cfg = load_config(args.config, args.preset)
    layout = generate_layout(cfg)
    master = generate_master(cfg, layout)
    return cfg, layout, master


def main():
    ap = argparse.ArgumentParser(prog="refsim")
    ap.add_argument("command", choices=["master", "history", "stream", "serve"])
    ap.add_argument("--config", default=None)
    ap.add_argument("--preset", default=None, choices=["small", "medium", "large"])
    ap.add_argument("--out", default=None)
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--start", default="2026-09-21")
    ap.add_argument("--date", default="2026-09-28")
    ap.add_argument("--speed", type=int, default=None)
    ap.add_argument("--hours", type=float, default=24)
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    cfg, layout, master = build(args)

    if args.command == "master":
        out = Path(args.out or REPO_ROOT / "mock-data" / "master")
        write_master(out, layout, master)
        print(f"master data → {out} ({len(master['employees'])} employees, {len(layout['workspaces'])} desks, "
              f"{len(layout['rooms'])} rooms/areas, {len(layout['sensors'])} sensors)")

    elif args.command == "history":
        out = Path(args.out or REPO_ROOT / "mock-data")
        write_master(out / "master", layout, master)
        start = date.fromisoformat(args.start)
        events = ArchiveSink(out / "raw", "events")
        truth = ArchiveSink(out / "raw", "truth")
        eng = Engine(cfg, layout, master, start, events, truth, mode="BATCH")
        events.run_id = truth.run_id = eng.run_id
        t0 = time.time()
        eng.start(days=args.days)
        eng.step_until(args.days * 86400.0 + 3600)
        events.close()
        truth.close()
        saas = out / "saas"
        saas.mkdir(parents=True, exist_ok=True)
        for name, rows in eng.saas.items():
            (saas / f"{name}.json").write_text(json.dumps(rows, indent=1))
        summary = {"simulation_run_id": eng.run_id, "mode": "BATCH", "seed": cfg["seed"], "preset": cfg["scale_preset"],
                   "start_date": args.start, "days": args.days, "wall_seconds": round(time.time() - t0, 1),
                   "events_by_type": dict(sorted(eng.counters.items()))}
        (out / "run-summary.json").write_text(json.dumps(summary, indent=1))
        print(json.dumps(summary, indent=1))

    elif args.command == "stream":
        eng = Engine(cfg, layout, master, date.fromisoformat(args.date), StdoutSink(), None, mode="LIVE")
        eng.start(days=None)
        speed = args.speed or cfg["simulation"]["speed"]
        end = args.hours * 3600
        wall0, sim0 = time.monotonic(), 6 * 3600.0
        eng.step_until(sim0)
        while eng.t < end:
            time.sleep(0.1)
            eng.step_until(min(end, sim0 + (time.monotonic() - wall0) * speed))

    elif args.command == "serve":
        from .server import serve
        serve(cfg, layout, master, date.fromisoformat(args.date), args.speed or cfg["simulation"]["speed"], args.port)


if __name__ == "__main__":
    main()
