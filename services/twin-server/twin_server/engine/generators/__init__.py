"""Master data generation (docs/simulation-engine.md §13). Pure functions of config + seed."""

from __future__ import annotations

from twin_server.engine.generators.layout_loader import load_layout
from twin_server.engine.generators.organization import generate_organization
from workplace_domain.config import WorkplaceConfig
from workplace_domain.models import MasterData
from workplace_domain.rng import RngFactory


def generate_master_data(config: WorkplaceConfig) -> MasterData:
    rng = RngFactory(config.simulation.seed)
    layout = load_layout(config, rng)
    org = generate_organization(config, layout, rng)
    return MasterData(
        layout=layout,
        departments=org.departments,
        teams=org.teams,
        team_zone_allocations=org.team_zone_allocations,
        zone_access_rules=org.zone_access_rules,
        employees=org.employees,
        work_patterns=org.work_patterns,
        assignments=org.assignments,
    )


__all__ = ["generate_master_data"]
