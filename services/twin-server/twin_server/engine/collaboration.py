"""Hidden cross-team collaboration pairs: simulation ground truth.

Pairs make meetings draw participants from partner teams (`meetings.partner_share`), so shared
meetings and cross-floor movement appear in observed data. The Team Collaboration analysis must
rediscover these pairs from bookings and badge reads alone; the pairs themselves are only exposed
through the Simulation Debug / truth endpoints.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from workplace_domain.config.schema import CollaborationConfig
from workplace_domain.models import Team
from workplace_domain.rng import RngFactory


@dataclass(frozen=True, slots=True)
class CollaborationPair:
    team_a: str
    team_b: str
    cross_floor: bool


def generate_pairs(
    teams: list[Team], cfg: CollaborationConfig, rng: RngFactory
) -> list[CollaborationPair]:
    """Pick `pair_count` disjoint team pairs; `cross_floor_share` of them on different floors."""
    r = rng.py_stream("collaboration")
    ordered = sorted(teams, key=lambda t: t.team_id)
    cross = [
        (a, b)
        for i, a in enumerate(ordered)
        for b in ordered[i + 1 :]
        if a.home_floor_id != b.home_floor_id
    ]
    same = [
        (a, b)
        for i, a in enumerate(ordered)
        for b in ordered[i + 1 :]
        if a.home_floor_id == b.home_floor_id
    ]
    r.shuffle(cross)
    r.shuffle(same)
    n_cross = round(cfg.pair_count * cfg.cross_floor_share)
    used: set[str] = set()
    pairs: list[CollaborationPair] = []

    def take(candidates: list[tuple[Team, Team]], limit: int, is_cross: bool) -> None:
        taken = 0
        for a, b in candidates:
            if taken >= limit:
                return
            if a.team_id in used or b.team_id in used:
                continue
            used.update((a.team_id, b.team_id))
            pairs.append(CollaborationPair(a.team_id, b.team_id, is_cross))
            taken += 1

    take(cross, n_cross, True)
    take(same, cfg.pair_count - len(pairs), False)
    return sorted(pairs, key=lambda p: (p.team_a, p.team_b))


def partners_by_team(pairs: list[CollaborationPair]) -> dict[str, list[str]]:
    partners: dict[str, list[str]] = defaultdict(list)
    for p in pairs:
        partners[p.team_a].append(p.team_b)
        partners[p.team_b].append(p.team_a)
    return {team: sorted(ids) for team, ids in partners.items()}
