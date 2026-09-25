"""Live demo server (stdlib only): runs the engine on a scaled clock and streams deltas to the browser via SSE.

This is a REFERENCE for the streaming/view-update model. The production stack replaces it with:
engine → Redis Streams → event-processor (Redis state) → FastAPI WebSocket → React.
The message shapes (/api/layout, /api/snapshot, stream frames) are the contract to keep.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .engine import Engine
from .sinks import CallbackSink
from .state import LiveState

VIEWER = Path(__file__).parent / "viewer" / "index.html"
SPEEDS = (1, 5, 10, 30, 60, 120, 300)


class Runner:
    def __init__(self, cfg, layout, master, start_date: date, speed: int):
        self.cfg, self.layout, self.master, self.start_date = cfg, layout, master, start_date
        self.speed = speed
        self.lock = threading.RLock()
        self.reset()
        threading.Thread(target=self._loop, daemon=True).start()

    def reset(self):
        with self.lock:
            self.state = LiveState(self.layout)
            self.engine = Engine(self.cfg, self.layout, self.master, self.start_date,
                                 CallbackSink(self.state.apply), CallbackSink(self.state.apply_truth), mode="LIVE")
            self.engine.start(days=None)
            self.status = "STOPPED"
            self.sim_t = 0.0
            self.anchor_wall = time.monotonic()
            self.anchor_sim = 0.0
            self.state.sample(self.engine.st.iso(0))

    def control(self, cmd: str, speed: int | None = None):
        with self.lock:
            now = time.monotonic()
            if cmd in ("start", "resume") and self.status != "RUNNING":
                self.status, self.anchor_wall, self.anchor_sim = "RUNNING", now, self.sim_t
            elif cmd == "pause" and self.status == "RUNNING":
                self.status = "PAUSED"
            elif cmd == "stop":
                self.status = "STOPPED"
            elif cmd == "reset":
                self.reset()
            elif cmd == "speed" and speed in SPEEDS:
                self.anchor_wall, self.anchor_sim, self.speed = now, self.sim_t, speed

    def _loop(self):
        skip = self.cfg["simulation"]["skip_night"]
        while True:
            time.sleep(0.05)
            with self.lock:
                if self.status != "RUNNING":
                    continue
                target = self.anchor_sim + (time.monotonic() - self.anchor_wall) * self.speed
                h = (target % 86400) / 3600
                if skip and not self.engine.truth_summary()["inside"] and (h >= 20.5 or h < 6):
                    day0 = target - (target % 86400)
                    target = day0 + (6 * 3600 if h < 6 else 86400 + 6 * 3600)
                    self.anchor_wall, self.anchor_sim = time.monotonic(), target
                self.engine.step_until(target)
                self.sim_t = target
                self.state.sample(self.engine.st.iso(target))

    def snapshot(self) -> dict:
        with self.lock:
            s = self.state
            return {"version": s.version, "sim_time": s.sim_iso, "status": self.status, "speed": self.speed,
                    "desks": {d: [s.desk_sensor.get(d, 0), 1 if d in s.desk_login else 0] for d in s.desks},
                    "rooms": dict(s.room_count), "positions": dict(s.positions),
                    "zones": {z: [e.get("TEMPERATURE"), e.get("CO2"), s.hvac.get(z, "NORMAL")] for z, e in s.env.items()},
                    "kpis": s.kpis(), "series": s.series, "truth": self.engine.truth_summary()}

    def frame(self, since: int) -> tuple[dict, int]:
        with self.lock:
            s = self.state
            oldest = s.log[0][0] if s.log else s.version + 1
            if since and since < oldest - 1:
                return {"resync": True}, s.version
            d, r, p, z = {}, {}, {}, {}
            for ver, kind, key, val in s.log:
                if ver <= since:
                    continue
                {"d": d, "r": r, "p": p, "z": z}[kind][key] = val
            feed = [f for v, f in s.feed if v > since][-40:]
            return {"sim_time": s.sim_iso, "status": self.status, "speed": self.speed, "desks": d, "rooms": r,
                    "positions": p, "zones": z, "feed": feed, "kpis": s.kpis(),
                    "point": s.series[-1] if s.series else None, "truth": self.engine.truth_summary(),
                    "events_total": sum(s.event_counts.values()),
                    "automation": list(s.automation_log)[-5:]}, s.version

    def desk_detail(self, desk: str) -> dict:
        with self.lock:
            s = self.state
            w = s.desks[desk]
            return {"workspace_id": desk, "zone_id": w["zone_id"], "floor_id": w["floor_id"],
                    "sensor_status": "OCCUPIED" if s.desk_sensor.get(desk) else "VACANT",
                    "last_sensor_change": s.desk_changed.get(desk),
                    # identity ONLY from workstation login, never from the anonymous sensor
                    "logged_in_employee": s.desk_login.get(desk)}


def make_handler(runner: Runner):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, obj, code=200):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                body = VIEWER.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/api/layout":
                depts = [d["name"] for d in runner.master["departments"]]
                self._json({**runner.layout, "departments": depts})
            elif self.path == "/api/snapshot":
                self._json(runner.snapshot())
            elif self.path.startswith("/api/desk/"):
                self._json(runner.desk_detail(self.path.rsplit("/", 1)[1]))
            elif self.path.startswith("/api/stream"):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                since = int(self.path.split("since=")[1]) if "since=" in self.path else 0
                try:
                    while True:
                        frame, since = runner.frame(since)
                        self.wfile.write(b"data: " + json.dumps(frame, separators=(",", ":")).encode() + b"\n\n")
                        self.wfile.flush()
                        time.sleep(0.5)
                except (BrokenPipeError, ConnectionResetError):
                    return
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self):
            if self.path == "/api/control":
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n) or b"{}")
                runner.control(body.get("cmd", ""), body.get("speed"))
                self._json({"ok": True, "status": runner.status, "speed": runner.speed})
            else:
                self._json({"error": "not found"}, 404)

    return H


def serve(cfg, layout, master, start_date: date, speed: int, port: int):
    runner = Runner(cfg, layout, master, start_date, speed)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(runner))
    print(f"Digital Twin reference viewer → http://127.0.0.1:{port}  (Ctrl+C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
