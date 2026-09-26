"""Crowd-driven environment physics and energy accounting for v2 (environment-and-esg.md §2-3).

Pure functions so the physics can be tested without running the engine. Physics uses ground
truth (the room really heats up); only the BMS rules are limited to observed sensor values.

Repo deviations (decision log 2026-09-27): CO2 is a mass balance on the area's air volume
(people x co2_lpm_per_person / volume) instead of `co2_gen_ppm_per_min x load`, and the
occupancy heat default is 1.8 C; with the pack's formula and defaults a crowded 4-seat room
could not exceed 1,000 ppm or 25.5 C, which the pack's own demo relies on.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from workplace_domain.config.v2 import V2Energy, V2Environment
from workplace_domain.rng import PyRandom


@dataclass
class AreaEnv:
    """Physical and control state of one environment area (zone or room)."""

    temp: float
    co2: float
    mode: str = "ECO"
    adj: float = 0.0  # setpoint adjustment from COOL_WHEN_WARM (negative)
    boost: bool = False
    light: int = 0  # lighting level %
    # observed (last reported) values: the only inputs the BMS may read
    obs_temp: float = 0.0
    obs_co2: float = 0.0
    # rule timers and cooldowns
    empty_since: float | None = None
    oversize_since: float | None = None
    over_since: float | None = None
    last_rule: dict[str, float] = field(default_factory=dict)


@dataclass
class EnergyAcc:
    kwh_hvac: float = 0.0
    kwh_lighting: float = 0.0
    kwh_baseline: float = 0.0
    occupied_minutes: float = 0.0
    comfort_ok_minutes: float = 0.0
    light_level_sum: float = 0.0
    ticks: int = 0


def daylight(hour: float, cfg: V2Environment) -> float:
    """0..1 sine curve between start and end hour, peaking at peak_h (config)."""
    d = cfg.daylight
    if not d.start_h <= hour <= d.end_h:
        return 0.0
    if hour <= d.peak_h:
        return math.sin(math.pi / 2 * (hour - d.start_h) / (d.peak_h - d.start_h))
    return math.sin(math.pi / 2 * (d.end_h - hour) / (d.end_h - d.peak_h))


def setpoint(env: AreaEnv, cfg: V2Environment) -> float:
    return cfg.setpoint_c[env.mode] + env.adj


def step_physics(
    env: AreaEnv,
    people: int,
    capacity: int,
    area_m2: float,
    facade: str | None,
    hour: float,
    dt_min: float,
    cfg: V2Environment,
    rng: PyRandom,
) -> None:
    """Advance temperature and CO2 of one area by dt_min minutes (first-order responses)."""
    load = min(cfg.max_load, people / max(1, capacity))
    solar = cfg.solar_gain_c.get(facade, 0.0) * daylight(hour, cfg) if facade else 0.0  # type: ignore[call-overload]
    target = setpoint(env, cfg) + cfg.occupancy_heat_c * load + solar
    k = math.exp(-cfg.mean_reversion_per_min[env.mode] * dt_min)
    noise = rng.gauss(0, cfg.temperature_noise_c * math.sqrt(dt_min))
    env.temp = target + (env.temp - target) * k + noise

    volume_l = max(1.0, area_m2 * cfg.ceiling_height_m) * 1000
    gen_ppm_per_min = people * cfg.co2_lpm_per_person / volume_l * 1_000_000
    vent = cfg.ventilation_per_min["BOOST" if env.boost else env.mode]
    steady = cfg.outdoor_co2_ppm + gen_ppm_per_min / vent
    env.co2 = steady + (env.co2 - steady) * math.exp(-vent * dt_min)
    env.co2 = max(cfg.outdoor_co2_ppm, env.co2 + rng.gauss(0, cfg.co2_noise_ppm))


def light_lux(env: AreaEnv, facade: str | None, hour: float, cfg: V2Environment) -> float:
    lux = cfg.lux_full * env.light / 100
    if facade:
        lux += cfg.daylight_lux * daylight(hour, cfg)
    return lux


def accumulate_energy(
    acc: EnergyAcc,
    env: AreaEnv,
    area_m2: float,
    people: int,
    hour: float,
    dt_min: float,
    energy: V2Energy,
) -> None:
    """Actual vs shadow-baseline kWh, occupied and comfort-ok minutes for one tick."""
    dt_h = dt_min / 60
    start, end = energy.operating_hours
    operating = start <= hour < end
    if operating:
        hvac_w = energy.hvac_w_per_m2[env.mode] + (energy.boost_w_per_m2 if env.boost else 0.0)
        baseline_w = energy.hvac_w_per_m2["NORMAL"] + energy.lighting_w_per_m2
    else:  # night setback applies to the building and to the baseline alike
        hvac_w = energy.night_baseline_w_per_m2
        baseline_w = energy.night_baseline_w_per_m2
    light_w = energy.lighting_w_per_m2 * env.light / 100
    acc.kwh_hvac += area_m2 * hvac_w / 1000 * dt_h
    acc.kwh_lighting += area_m2 * light_w / 1000 * dt_h
    acc.kwh_baseline += area_m2 * baseline_w / 1000 * dt_h
    acc.light_level_sum += env.light
    acc.ticks += 1
    if people > 0:
        acc.occupied_minutes += dt_min
        low, high = energy.comfort_band_c
        if low <= env.temp <= high and env.co2 < energy.comfort_co2_ppm:
            acc.comfort_ok_minutes += dt_min
