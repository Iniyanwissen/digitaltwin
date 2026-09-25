"""Shared utilities: config loading, seeded RNG streams, time helpers, event envelope."""
from __future__ import annotations

import hashlib
import math
import random
import uuid
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
# Local change: the kit config lives next to the reference (the app uses its own split config).
DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "simulation.yaml"


# ------------------------------------------------------------------ config
def load_config(path: str | Path | None = None, preset: str | None = None) -> dict:
    with open(path or DEFAULT_CONFIG, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if preset:
        cfg["scale_preset"] = preset
    if cfg["scale_preset"] not in cfg["presets"]:
        raise ValueError(f"unknown scale_preset {cfg['scale_preset']!r}")
    cfg["scale"] = cfg["presets"][cfg["scale_preset"]]
    return cfg


# ------------------------------------------------------------------ randomness
class RngFactory:
    """All randomness comes from named, derived streams. Never use the global `random`."""

    def __init__(self, seed: int):
        self.seed = int(seed)

    def stream(self, *keys) -> random.Random:
        material = "|".join([str(self.seed), *map(str, keys)]).encode()
        h = hashlib.blake2b(material, digest_size=8).digest()
        return random.Random(int.from_bytes(h, "big"))


def lognormal_from_median_p90(rng: random.Random, median: float, p90: float) -> float:
    mu = math.log(median)
    sigma = (math.log(p90) - mu) / 1.2816
    return rng.lognormvariate(mu, sigma)


def weighted_choice(rng: random.Random, weights: dict):
    keys = list(weights)
    return rng.choices(keys, weights=[weights[k] for k in keys], k=1)[0]


def stable_jitter(key: str, span: float = 1.0) -> tuple[float, float]:
    h = hashlib.blake2b(key.encode(), digest_size=4).digest()
    return (h[0] / 255 - 0.5) * span, (h[1] / 255 - 0.5) * span


# ------------------------------------------------------------------ time
class SimTime:
    """Sim time is float seconds since midnight of the run's start date (building timezone)."""

    def __init__(self, start_date: date, tz: str):
        self.start_date = start_date
        self.tz = ZoneInfo(tz)
        self.base = datetime.combine(start_date, time(0), tzinfo=self.tz)

    def dt(self, t: float) -> datetime:
        return self.base + timedelta(seconds=t)

    def iso(self, t: float) -> str:
        return self.dt(t).isoformat(timespec="milliseconds")

    def day_date(self, day: int) -> date:
        return self.start_date + timedelta(days=day)

    @staticmethod
    def hour_of(t: float) -> float:
        return (t % 86400) / 3600.0


# ------------------------------------------------------------------ events
IDENTITY_CLASS = {
    "ACCESS_IN": "IDENTIFIED",
    "ACCESS_OUT": "IDENTIFIED",
    "AREA_ACCESS": "IDENTIFIED",
    "ROOM_CHECK_IN": "IDENTIFIED",
    "WORKSPACE_LOGIN": "IDENTIFIED",
    "WORKSPACE_LOGOUT": "IDENTIFIED",
    "OCCUPANCY_CHANGED": "ANONYMOUS",
    "ROOM_OCCUPANCY_CHANGED": "ANONYMOUS",
    "SENSOR_HEARTBEAT": "ANONYMOUS",
    "ENVIRONMENT_READING": "ANONYMOUS",
    "SENSOR_STATUS_CHANGED": "SYSTEM",
    "AUTOMATION_ACTION": "SYSTEM",
    "SIMULATION_LIFECYCLE": "SYSTEM",
}
SOURCE = {
    "ACCESS_IN": "ACCESS_CONTROL", "ACCESS_OUT": "ACCESS_CONTROL", "AREA_ACCESS": "ACCESS_CONTROL",
    "ROOM_CHECK_IN": "ROOM_PANEL",
    "WORKSPACE_LOGIN": "WORKSTATION", "WORKSPACE_LOGOUT": "WORKSTATION",
    "OCCUPANCY_CHANGED": "DESK_SENSOR", "ROOM_OCCUPANCY_CHANGED": "ROOM_SENSOR",
    "SENSOR_HEARTBEAT": "SENSOR_GATEWAY", "ENVIRONMENT_READING": "ENV_SENSOR",
    "SENSOR_STATUS_CHANGED": "SENSOR_GATEWAY", "AUTOMATION_ACTION": "BMS",
    "SIMULATION_LIFECYCLE": "SIMULATION",
}
PII_KEYS = {"employee_id", "visitor_id", "person_id", "email", "name", "employee_name"}


def make_event_id(run_id: str, seq: int) -> str:
    return str(uuid.uuid5(uuid.UUID(run_id), str(seq)))


def validate_envelope(env: dict) -> None:
    """Privacy guard: anonymous events must never carry identity."""
    if env["identity_class"] == "ANONYMOUS":
        if env["entity_type"] in ("EMPLOYEE", "VISITOR"):
            raise ValueError(f"anonymous event with person entity: {env['event_type']}")
        if env.get("correlation_id"):
            raise ValueError("anonymous event with correlation_id")
        if PII_KEYS & set(env.get("payload", {})):
            raise ValueError("anonymous event payload contains identity keys")
