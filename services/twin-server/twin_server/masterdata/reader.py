"""Read queries over master data for the API."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from sqlalchemy import ColumnElement, Engine, Select, and_, func, or_, select

from twin_server.db import tables as t

Row = dict[str, Any]


@dataclass(frozen=True)
class EmployeeFilters:
    search: str | None = None
    department_id: str | None = None
    team_id: str | None = None
    floor_id: str | None = None
    work_mode: str | None = None
    behavior_profile: str | None = None


class MasterDataReader:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    # ------------------------------------------------------------------ helpers
    def _all(self, query: Select[Any]) -> list[Row]:
        with self._engine.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(query)]

    def _page(
        self, query: Select[Any], order: Any, page: int, page_size: int
    ) -> tuple[list[Row], int]:
        with self._engine.connect() as conn:
            total = conn.execute(select(func.count()).select_from(query.subquery())).scalar_one()
            rows = conn.execute(
                query.order_by(order).limit(page_size).offset((page - 1) * page_size)
            )
            return [dict(r._mapping) for r in rows], total

    def _grouped(self, query: Select[Any]) -> dict[Any, Any]:
        with self._engine.connect() as conn:
            return {r[0]: r[1] for r in conn.execute(query)}

    # ------------------------------------------------------------------ spaces
    def floors(self, building_id: str | None = None) -> list[Row]:
        f, w, r, z, s, e, tm = t.floor, t.workspace, t.room, t.zone, t.sensor, t.employee, t.team
        query = select(f).order_by(f.c.building_id, f.c.floor_number)
        if building_id:
            query = query.where(f.c.building_id == building_id)
        floors = self._all(query)

        def count(
            col: Any, where: ColumnElement[bool] | None = None, agg: Any = None
        ) -> dict[Any, Any]:
            q = select(col, agg if agg is not None else func.count()).group_by(col)
            return self._grouped(q.where(where) if where is not None else q)

        desks = count(w.c.floor_id, w.c.workspace_type == "DESK")
        cabins = count(w.c.floor_id, w.c.workspace_type == "CABIN")
        is_room = r.c.room_type != "COMMON_AREA"
        rooms = count(r.c.floor_id, is_room)
        seats = count(r.c.floor_id, is_room, func.sum(r.c.capacity))
        areas = count(r.c.floor_id, ~is_room)
        area_cap = count(r.c.floor_id, ~is_room, func.sum(r.c.capacity))
        zones = count(z.c.floor_id)
        sensors = count(s.c.floor_id)
        people = count(e.c.home_floor_id)
        teams = count(tm.c.home_floor_id)
        for fl in floors:
            fid = fl["floor_id"]
            fl |= {
                "desks": desks.get(fid, 0),
                "cabins": cabins.get(fid, 0),
                "rooms": rooms.get(fid, 0),
                "room_seats": seats.get(fid, 0) or 0,
                "common_areas": areas.get(fid, 0),
                "common_area_capacity": area_cap.get(fid, 0) or 0,
                "zones": zones.get(fid, 0),
                "sensors": sensors.get(fid, 0),
                "home_employees": people.get(fid, 0),
                "home_teams": teams.get(fid, 0),
            }
            fl["workspaces"] = fl["desks"] + fl["cabins"]
            fl["employees_per_workspace"] = (
                round(fl["home_employees"] / fl["workspaces"], 2) if fl["workspaces"] else 0.0
            )
        return floors

    def buildings(self) -> list[Row]:
        buildings = self._all(select(t.building).order_by(t.building.c.building_id))
        floors = self.floors()
        for b in buildings:
            b["floors"] = [f for f in floors if f["building_id"] == b["building_id"]]
            b["access_points"] = self._all(
                select(t.access_point).where(t.access_point.c.building_id == b["building_id"])
            )
        return buildings

    def floor_layout(self, floor_id: str) -> Row | None:
        floors = self._all(select(t.floor).where(t.floor.c.floor_id == floor_id))
        if not floors:
            return None
        layout = floors[0]
        layout["zones"] = self._all(
            select(t.zone).where(t.zone.c.floor_id == floor_id).order_by(t.zone.c.zone_id)
        )
        layout["workspaces"] = self._all(
            select(t.workspace)
            .where(t.workspace.c.floor_id == floor_id)
            .order_by(t.workspace.c.workspace_id)
        )
        layout["rooms"] = self._all(
            select(t.room).where(t.room.c.floor_id == floor_id).order_by(t.room.c.room_id)
        )
        layout["access_points"] = self._all(
            select(t.access_point).where(t.access_point.c.floor_id == floor_id)
        )
        return layout

    def zones(self, floor_id: str | None = None) -> list[Row]:
        z, w = t.zone, t.workspace
        desk_counts = (
            select(w.c.zone_id, func.count().label("workspaces")).group_by(w.c.zone_id).subquery()
        )
        query = (
            select(z, func.coalesce(desk_counts.c.workspaces, 0).label("workspaces"))
            .outerjoin(desk_counts, desk_counts.c.zone_id == z.c.zone_id)
            .order_by(z.c.zone_id)
        )
        if floor_id:
            query = query.where(z.c.floor_id == floor_id)
        return self._all(query)

    def rooms(self, floor_id: str | None = None, room_type: str | None = None) -> list[Row]:
        r, z = t.room, t.zone
        query = select(r, z.c.name.label("zone_name")).join(z, z.c.zone_id == r.c.zone_id)
        if floor_id:
            query = query.where(r.c.floor_id == floor_id)
        if room_type:
            query = query.where(r.c.room_type == room_type)
        return self._all(query.order_by(r.c.room_id))

    def workspaces(
        self,
        floor_id: str | None,
        zone_id: str | None,
        workspace_type: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Row], int]:
        w = t.workspace
        conditions = [
            c
            for c in (
                w.c.floor_id == floor_id if floor_id else None,
                w.c.zone_id == zone_id if zone_id else None,
                w.c.workspace_type == workspace_type if workspace_type else None,
            )
            if c is not None
        ]
        query = select(w).where(and_(*conditions)) if conditions else select(w)
        return self._page(query, w.c.workspace_id, page, page_size)

    def sensors(
        self, sensor_type: str | None, floor_id: str | None, page: int, page_size: int
    ) -> tuple[list[Row], int]:
        s = t.sensor
        query = select(s)
        if sensor_type:
            query = query.where(s.c.sensor_type == sensor_type)
        if floor_id:
            query = query.where(s.c.floor_id == floor_id)
        return self._page(query, s.c.sensor_id, page, page_size)

    # ------------------------------------------------------------------ people
    def departments(self) -> list[Row]:
        d, e, tm = t.department, t.employee, t.team
        people = self._grouped(select(e.c.department_id, func.count()).group_by(e.c.department_id))
        teams = self._grouped(select(tm.c.department_id, func.count()).group_by(tm.c.department_id))
        rows = self._all(select(d).order_by(d.c.department_id))
        for row in rows:
            row["employees"] = people.get(row["department_id"], 0)
            row["teams"] = teams.get(row["department_id"], 0)
        return rows

    def teams(self, department_id: str | None = None, floor_id: str | None = None) -> list[Row]:
        tm, d, f, e = t.team, t.department, t.floor, t.employee
        members = (
            select(e.c.team_id, func.count().label("members")).group_by(e.c.team_id).subquery()
        )
        query = (
            select(
                tm,
                d.c.name.label("department_name"),
                f.c.name.label("home_floor_name"),
                func.coalesce(members.c.members, 0).label("members"),
            )
            .join(d, d.c.department_id == tm.c.department_id)
            .join(f, f.c.floor_id == tm.c.home_floor_id)
            .outerjoin(members, members.c.team_id == tm.c.team_id)
            .order_by(tm.c.team_id)
        )
        if department_id:
            query = query.where(tm.c.department_id == department_id)
        if floor_id:
            query = query.where(tm.c.home_floor_id == floor_id)
        rows = self._all(query)

        a, z = t.team_zone_allocation, t.zone
        allocations: dict[str, list[Row]] = defaultdict(list)
        for alloc in self._all(
            select(a.c.team_id, a.c.zone_id, a.c.share, z.c.name.label("zone_name"))
            .join(z, z.c.zone_id == a.c.zone_id)
            .order_by(a.c.team_id, a.c.share.desc())
        ):
            allocations[alloc.pop("team_id")].append(alloc)
        for row in rows:
            row["zone_allocations"] = allocations[row["team_id"]]
        return rows

    def employees(
        self, filters: EmployeeFilters, page: int, page_size: int
    ) -> tuple[list[Row], int]:
        e, tm, d, f, wa = t.employee, t.team, t.department, t.floor, t.workspace_assignment
        query = (
            select(
                e.c.employee_id,
                e.c.employee_name,
                e.c.email,
                e.c.job_role,
                e.c.team_id,
                tm.c.name.label("team_name"),
                e.c.department_id,
                d.c.name.label("department_name"),
                e.c.home_floor_id,
                f.c.name.label("home_floor_name"),
                e.c.preferred_zone_id,
                e.c.manager_id,
                e.c.employment_type,
                e.c.work_mode,
                e.c.behavior_profile,
                e.c.hire_date,
                wa.c.workspace_id.label("assigned_workspace_id"),
            )
            .join(tm, tm.c.team_id == e.c.team_id)
            .join(d, d.c.department_id == e.c.department_id)
            .join(f, f.c.floor_id == e.c.home_floor_id)
            .outerjoin(wa, and_(wa.c.employee_id == e.c.employee_id, wa.c.valid_to.is_(None)))
        )
        if filters.search:
            like = f"%{filters.search.strip()}%"
            query = query.where(
                or_(
                    e.c.employee_name.ilike(like),
                    e.c.employee_id.ilike(like),
                    e.c.email.ilike(like),
                    e.c.job_role.ilike(like),
                )
            )
        exact = {
            e.c.department_id: filters.department_id,
            e.c.team_id: filters.team_id,
            e.c.home_floor_id: filters.floor_id,
            e.c.work_mode: filters.work_mode,
            e.c.behavior_profile: filters.behavior_profile,
        }
        for column, value in exact.items():
            if value:
                query = query.where(column == value)
        return self._page(query, e.c.employee_id, page, page_size)

    def employee_facets(self) -> dict[str, list[Row]]:
        e = t.employee
        facets: dict[str, list[Row]] = {}
        for column in (e.c.work_mode, e.c.behavior_profile, e.c.employment_type):
            counts = self._grouped(select(column, func.count()).group_by(column).order_by(column))
            facets[column.name] = [{"value": v, "count": c} for v, c in counts.items()]
        return facets
