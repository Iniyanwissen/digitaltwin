"""LayoutGenerator: builds the office hierarchy (building → floor → zone → desk/room) with coordinates.

Deterministic: the same config always yields the same layout and IDs.
Coordinates are in layout units (floor_width × floor_height) and are used directly by the floor renderer.
"""
from __future__ import annotations

import math


def _grid(x, y, w, h, n, pad=1.0):
    """Split a rectangle into n roughly-square cells. Returns list of (cx, cy, cw, ch)."""
    if n <= 0:
        return []
    cols = max(1, round(math.sqrt(n * w / h)))
    rows = math.ceil(n / cols)
    cw, ch = (w - 2 * pad) / cols, (h - 2 * pad) / rows
    cells = []
    for i in range(n):
        r, c = divmod(i, cols)
        cells.append((x + pad + c * cw, y + pad + r * ch, cw, ch))
    return cells


def generate_layout(cfg: dict) -> dict:
    lc, sc = cfg["layout"], cfg["scale"]
    bid = lc["building_id"]
    W, H = lc["floor_width"], lc["floor_height"]
    cap = lc["room_capacity"]

    layout = {
        "building": {"building_id": bid, "name": lc["building_name"], "timezone": cfg["timezone"],
                     "max_occupancy": 0, "floors": sc["floors"]},
        "floors": [], "zones": [], "workspaces": [], "rooms": [], "access_points": [], "sensors": [],
    }
    desk_seq = room_seq = env_seq = 0

    layout["access_points"].append({
        "access_point_id": f"AP_{bid}_ENT01", "floor_id": f"{bid}_F01", "reader_type": "BUILDING_ENTRANCE",
        "target_id": bid, "direction": "IN_OUT", "x": 2.0, "y": H / 2})

    for fn in range(1, sc["floors"] + 1):
        fid = f"{bid}_F{fn:02d}"
        policy = "ASSIGNED" if fn in sc.get("assigned_desk_floors", []) else "HOT_DESK"
        floor = {"floor_id": fid, "building_id": bid, "floor_number": fn, "name": f"Floor {fn}",
                 "desk_policy": policy, "plan_width": W, "plan_height": H, "max_occupancy": 0}
        layout["floors"].append(floor)

        def zone(code, name, ztype, x, y, w, h):
            z = {"zone_id": f"{fid}_Z{code}", "floor_id": fid, "name": name, "zone_type": ztype,
                 "x": x, "y": y, "width": w, "height": h, "is_restricted": False, "capacity": 0}
            layout["zones"].append(z)
            return z

        lobby = zone("LOB", "Lift Lobby" if fn > 1 else "Entrance Lobby",
                     "CIRCULATION" if fn > 1 else "ENTRANCE", 0, 0, 12, H)
        if fn > 1:
            layout["access_points"].append({
                "access_point_id": f"AP_{fid}_LOBBY", "floor_id": fid, "reader_type": "FLOOR_LOBBY",
                "target_id": fid, "direction": "IN", "x": 10.0, "y": H / 2})

        # workspace zones with desks
        nz = sc["workspace_zones_per_floor"]
        per_zone = [sc["desks_per_floor"] // nz + (1 if i < sc["desks_per_floor"] % nz else 0) for i in range(nz)]
        for zi, (zx, zy, zw, zh) in enumerate(_grid(14, 1, 70, H - 2, nz, pad=0.5)):
            z = zone(chr(ord("A") + zi), f"Open Workspace {chr(ord('A') + zi)}", "OPEN_WORKSPACE",
                     zx, zy, zw - 1, zh - 1)
            for (dx, dy, dw, dh) in _grid(z["x"], z["y"] + 2, z["width"], z["height"] - 2, per_zone[zi], pad=0.8):
                desk_seq += 1
                wid = f"DESK_{bid}_F{fn:02d}_{desk_seq:04d}"
                has_sensor = (desk_seq % 1000) < lc["desk_sensor_coverage"] * 1000
                layout["workspaces"].append({
                    "workspace_id": wid, "floor_id": fid, "zone_id": z["zone_id"], "workspace_type": "DESK",
                    "x": round(dx + dw / 2, 2), "y": round(dy + dh / 2, 2), "size": round(min(dw, dh) * 0.7, 2),
                    "status": "ACTIVE", "has_sensor": has_sensor, "device_type": "DOCKING_STATION"})
                z["capacity"] += 1
                if has_sensor:
                    layout["sensors"].append({"sensor_id": f"SEN_DSK_{desk_seq:06d}", "sensor_type": "DESK_OCCUPANCY",
                                              "target_type": "WORKSPACE", "target_id": wid, "floor_id": fid,
                                              "zone_id": z["zone_id"]})

        # meeting rooms
        mz = zone("MTG", "Meeting Rooms", "MEETING", 86, 1, 33, 44)
        specs = [t for t, n in sc["rooms_per_floor"].items() for _ in range(n)]
        if fn == 1 and sc.get("auditorium_on_ground_floor"):
            specs = ["AUDITORIUM"] + specs[: max(0, len(specs) - 3)]
        for (rx, ry, rw, rh), rtype in zip(_grid(mz["x"], mz["y"] + 2, mz["width"], mz["height"] - 2, len(specs), pad=0.4), specs):
            room_seq += 1
            _add_room(layout, lc, fid, mz, f"ROOM_{bid}_F{fn:02d}_{room_seq:03d}", rtype, None, cap[rtype],
                      rx, ry, rw, rh, room_seq)

        # common areas
        cz = zone("COM", "Cafeteria & Lounge" if fn == 1 else "Collaboration & Lounge",
                  "CAFETERIA" if fn == 1 else "COLLABORATION", 86, 47, 33, 24)
        areas = lc["common_areas"]["ground_floor" if fn == 1 else "other_floors"]
        cells = _grid(cz["x"], cz["y"] + 2, cz["width"], cz["height"] - 2, len(areas), pad=0.4)
        for (ax, ay, aw, ah), (atype, acap) in zip(cells, areas.items()):
            room_seq += 1
            capacity = int(acap * sc["employees"]) if isinstance(acap, float) else int(acap)
            _add_room(layout, lc, fid, cz, f"AREA_{bid}_F{fn:02d}_{atype[:3]}", "COMMON_AREA", atype, capacity,
                      ax, ay, aw, ah, room_seq)

        for z in [x for x in layout["zones"] if x["floor_id"] == fid]:
            env_seq += 1
            layout["sensors"].append({"sensor_id": f"SEN_ENV_{env_seq:06d}", "sensor_type": "ENVIRONMENT",
                                      "target_type": "ZONE", "target_id": z["zone_id"], "floor_id": fid,
                                      "zone_id": z["zone_id"],
                                      "metrics": ["TEMPERATURE", "HUMIDITY", "CO2", "LIGHT", "NOISE"]})
        floor["max_occupancy"] = sum(z["capacity"] for z in layout["zones"] if z["floor_id"] == fid)
        floor["desk_count"] = sum(1 for w in layout["workspaces"] if w["floor_id"] == fid)

    layout["building"]["max_occupancy"] = sum(f["max_occupancy"] for f in layout["floors"])
    return layout


def _add_room(layout, lc, fid, zone, rid, rtype, subtype, capacity, x, y, w, h, seq):
    room = {"room_id": rid, "floor_id": fid, "zone_id": zone["zone_id"], "room_type": rtype,
            "area_subtype": subtype, "name": subtype.title() if subtype else f"{rtype.replace('_', ' ').title()} {seq}",
            "capacity": capacity, "x": round(x, 2), "y": round(y, 2), "width": round(w, 2), "height": round(h, 2),
            "is_bookable": rtype != "COMMON_AREA",
            "has_badge_reader": rtype in lc["door_reader_room_types"],
            "has_panel": rtype in lc["panel_room_types"], "status": "ACTIVE"}
    layout["rooms"].append(room)
    zone["capacity"] += capacity
    layout["sensors"].append({"sensor_id": f"SEN_RM_{seq:06d}", "sensor_type": "ROOM_COUNT", "target_type": "ROOM",
                              "target_id": rid, "floor_id": fid, "zone_id": zone["zone_id"]})
    if room["has_badge_reader"]:
        layout["access_points"].append({"access_point_id": f"AP_{rid}_DOOR", "floor_id": fid,
                                        "reader_type": "ROOM_DOOR", "target_id": rid, "direction": "IN",
                                        "x": round(x + 0.5, 2), "y": round(y + h / 2, 2)})
