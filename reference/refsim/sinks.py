"""Event sinks. The engine only knows `.write(envelope)`; swap sinks to change the destination.

- ArchiveSink: raw archive layout partitioned by ingest_time (docs/event-model.md §9)
- StdoutSink:  JSON lines on stdout (pipe into anything)
- CallbackSink: in-process consumer (live server, tests)
- RedisStreamSink: optional, publishes to Redis Streams (pip install redis)
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path


class ArchiveSink:
    def __init__(self, root: Path, area: str = "events", run_id: str = "run", max_rows: int = 5000):
        self.root, self.area, self.run_id, self.max_rows = Path(root), area, run_id, max_rows
        self.buffers: dict[Path, list[str]] = defaultdict(list)
        self.part = defaultdict(int)
        self.rows = 0

    def write(self, env: dict):
        ts = env.get("ingest_time") or env["event_time"]
        y, m, d, h = ts[0:4], ts[5:7], ts[8:10], ts[11:13]
        folder = self.root / self.area / f"year={y}" / f"month={m}" / f"day={d}" / f"hour={h}" / f"event_type={env['event_type']}"
        self.buffers[folder].append(json.dumps(env, separators=(",", ":")))
        self.rows += 1
        if len(self.buffers[folder]) >= self.max_rows:
            self._flush(folder)

    def _flush(self, folder: Path):
        rows = self.buffers.pop(folder, [])
        if not rows:
            return
        folder.mkdir(parents=True, exist_ok=True)
        self.part[folder] += 1
        name = f"part-{self.run_id[:8]}-{self.part[folder]:05d}.jsonl"
        (folder / name).write_text("\n".join(rows) + "\n", encoding="utf-8")
        (folder / f"_manifest-{name}.json").write_text(json.dumps({"file": name, "rows": len(rows)}))

    def close(self):
        for folder in list(self.buffers):
            self._flush(folder)


class StdoutSink:
    def write(self, env: dict):
        sys.stdout.write(json.dumps(env, separators=(",", ":")) + "\n")

    def close(self):
        sys.stdout.flush()


class CallbackSink:
    def __init__(self, fn):
        self.fn = fn

    def write(self, env: dict):
        self.fn(env)

    def close(self):
        pass


class RedisStreamSink:
    """Stream key per event group, matching docs/event-model.md §6."""
    GROUP = {"ACCESS_IN": "ev.access", "ACCESS_OUT": "ev.access", "AREA_ACCESS": "ev.access",
             "ROOM_CHECK_IN": "ev.access", "WORKSPACE_LOGIN": "ev.workspace", "WORKSPACE_LOGOUT": "ev.workspace",
             "OCCUPANCY_CHANGED": "ev.occupancy", "ROOM_OCCUPANCY_CHANGED": "ev.occupancy",
             "SENSOR_HEARTBEAT": "ev.occupancy", "ENVIRONMENT_READING": "ev.environment"}

    def __init__(self, url: str = "redis://localhost:6379/0"):
        import redis  # optional dependency
        self.r = redis.Redis.from_url(url)

    def write(self, env: dict):
        key = self.GROUP.get(env["event_type"], "ev.truth" if env["event_type"].startswith("TRUTH") else "ev.system")
        self.r.xadd(key, {"data": json.dumps(env)}, maxlen=1_000_000, approximate=True)

    def close(self):
        pass
