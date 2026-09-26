"""Human-readable people activity for the Live Simulation "People activity" panel.

Two sources, never mixed:
- observed: built ONLY from IDENTIFIED events (badge readers, workstation logins, room panels) -
  what the building's systems actually know about a person
- truth: built from ground-truth transitions - what the person is really doing (Simulation View)
Anonymous sensor events never produce people activity.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, ClassVar

from twin_server.engine.simulation import TruthTransition
from workplace_domain.enums import EventType, PersonState
from workplace_domain.events import EventEnvelope
from workplace_domain.models import MasterData


def short_code(employee_id: str) -> str:
    """EMP000283 -> E283 (display only; the employee id stays the key)."""
    digits = employee_id.removeprefix("EMP")
    return f"E{int(digits)}" if digits.isdigit() else employee_id


def desk_label(workspace_id: str) -> str:
    """DESK_BLD01_F02_045 -> Desk F2-045, CABIN_BLD01_F04_03 -> Cabin F4-03."""
    parts = workspace_id.split("_")
    if len(parts) == 4 and parts[2].startswith("F"):
        kind = "Cabin" if parts[0] == "CABIN" else "Desk"
        return f"{kind} F{int(parts[2][1:])}-{parts[3]}"
    return workspace_id


@dataclass(frozen=True)
class Person:
    code: str
    name: str
    department: str


class ActivityDescriber:
    def __init__(self, master: MasterData) -> None:
        dept = {d.department_id: d.name for d in master.departments}
        self.people = {
            e.employee_id: Person(short_code(e.employee_id), e.employee_name, dept[e.department_id])
            for e in master.employees
        }
        lay = master.layout
        self.floor_names = {f.floor_id: f.name for f in lay.floors}
        self.room_names = {r.room_id: r.name for r in lay.rooms}
        self.zone_names = {z.zone_id: z.name for z in lay.zones}

    def _item(self, person_id: str, t: datetime, text: str, kind: str) -> dict[str, Any] | None:
        p = self.people.get(person_id)
        if p is None:
            return None
        return {
            "t": t.strftime("%H:%M:%S"),
            "person": person_id,
            "code": p.code,
            "name": p.name,
            "dept": p.department,
            "text": text,
            "kind": kind,
        }

    def place(self, location_id: str | None) -> str:
        if location_id is None:
            return ""
        if location_id.startswith(("DESK_", "CABIN_")):
            return desk_label(location_id)
        return self.room_names.get(location_id) or self.zone_names.get(location_id, location_id)

    # ------------------------------------------------------------------ observed (identified only)
    def observed(self, env: EventEnvelope) -> dict[str, Any] | None:
        if env.identity_class != "IDENTIFIED":
            return None
        p, et = env.payload, env.event_type
        if et is EventType.ACCESS_IN:
            text, kind = "entered the building", "in"
        elif et is EventType.ACCESS_OUT:
            text, kind = "left the building", "out"
        elif et is EventType.AREA_ACCESS:
            area = p["area_id"]
            if p["area_type"] == "FLOOR":
                text, kind = f"badged into {self.floor_names.get(area, area)} lobby", "move"
            elif p["area_type"] == "ROOM":
                text, kind = f"badged into {self.place(area)}", "room"
            else:
                text, kind = f"badged into {self.place(area)} (restricted)", "secure"
        elif et is EventType.WORKSPACE_LOGIN:
            text, kind = f"logged in at {desk_label(p['workspace_id'])}", "desk"
        elif et is EventType.WORKSPACE_LOGOUT:
            reason = str(p["logout_reason"]).replace("_", " ").lower()
            text, kind = f"logged out of {desk_label(p['workspace_id'])} ({reason})", "logout"
        elif et is EventType.ROOM_CHECK_IN:
            text, kind = f"checked in to {self.place(p['room_id'])}", "room"
        else:
            return None
        return self._item(env.entity_id, env.event_time, text, kind)

    def observed_status(self, inside: bool, floor_id: str | None, desk: str | None) -> str:
        parts = ["In building" if inside else "Not badged in"]
        if inside and floor_id:
            parts.append(self.floor_names.get(floor_id, floor_id))
        if desk:
            parts.append(f"logged in at {desk_label(desk)}")
        return " · ".join(parts)

    # ------------------------------------------------------------------ truth (simulation view)
    _TRUTH_TEXT: ClassVar[dict[PersonState, tuple[str, str]]] = {
        PersonState.ENTERING: ("arrived at reception", "Arriving"),
        PersonState.MEETING: ("joined a meeting in {place}", "In a meeting · {place}"),
        PersonState.BREAK: ("took a break in the {place}", "On a break · {place}"),
        PersonState.COLLABORATION_AREA: ("went to the {place}", "Collaborating · {place}"),
        PersonState.OTHER_AREA: ("walking around ({place})", "Walking · {place}"),
        PersonState.LEAVING: ("heading out", "Leaving"),
        PersonState.OUTSIDE_OFFICE: ("left the building", "Left the building"),
    }

    def truth(self, tr: TruthTransition) -> tuple[dict[str, Any] | None, str]:
        """(activity line, current status) for a ground-truth transition."""
        place = self.place(tr.location_id)
        state = tr.to_state
        if state is PersonState.AT_DESK:
            back = tr.reason == "PACK_UP"
            text = f"back at {place} to pack up" if back else f"sat down at {place}"
            status = f"At {place}"
        elif state is PersonState.CAFETERIA:
            what = "lunch" if tr.reason == "LUNCH" else "coffee"
            text, status = f"went to the {place.lower()} ({what})", f"Cafeteria ({what})"
        elif state is PersonState.COLLABORATION_AREA and tr.reason == "DESK_SHORTAGE":
            text, status = f"found no free desk, working in the {place}", f"No desk · {place}"
        else:
            text_t, status_t = self._TRUTH_TEXT.get(state, (str(state), str(state)))
            text, status = text_t.format(place=place), status_t.format(place=place)
        return self._item(tr.person_id, tr.event_time, text, state.value.lower()), status
