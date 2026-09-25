"""Master data generators: departments, teams, employees, work patterns, desk assignments.

Also marks restricted zones (secure-zone readers) based on department placement.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from .common import RngFactory, weighted_choice

FIRST = ["Aarav", "Diya", "Karthik", "Meera", "Arjun", "Priya", "Rahul", "Ananya", "Vikram", "Kavya", "Rohan",
         "Isha", "Siddharth", "Nila", "Aditya", "Sneha", "Harish", "Lakshmi", "Varun", "Divya", "Manoj", "Pooja",
         "Suresh", "Deepa", "Ravi", "Janani", "Ashwin", "Keerthi", "Naveen", "Swathi", "Daniel", "Sarah", "Omar",
         "Lena", "Mateo", "Yuki", "Chen", "Fatima", "Noah", "Emma"]
LAST = ["Iyer", "Sharma", "Reddy", "Nair", "Menon", "Kumar", "Rao", "Pillai", "Gupta", "Krishnan", "Das",
        "Subramanian", "Joshi", "Mehta", "Bose", "Chandran", "Varma", "Srinivasan", "Fernandes", "Khan", "Smith",
        "Garcia", "Tanaka", "Wang", "Ali", "Müller", "Rossi", "Silva", "Kim", "Brown"]
ROLES = {
    "Engineering": ["Software Engineer", "Senior Software Engineer", "Data Engineer", "QA Engineer", "DevOps Engineer"],
    "Operations": ["Operations Analyst", "Operations Associate", "Program Coordinator"],
    "Sales": ["Account Executive", "Sales Associate", "Sales Engineer"],
    "Marketing": ["Marketing Specialist", "Content Strategist", "Growth Analyst"],
    "Finance": ["Financial Analyst", "Accountant", "Controller"],
    "HR": ["HR Generalist", "Recruiter", "People Partner"],
    "Management": ["Program Manager", "Product Manager", "Director"],
}


def generate_master(cfg: dict, layout: dict) -> dict:
    rngf = RngFactory(cfg["seed"])
    rng = rngf.stream("master")
    org, sc = cfg["organization"], cfg["scale"]
    n_emp = sc["employees"]

    # departments and teams
    departments, teams = [], []
    dept_counts = {d: int(round(share * n_emp)) for d, share in org["departments"].items()}
    dept_counts[next(iter(dept_counts))] += n_emp - sum(dept_counts.values())
    tseq = 0
    team_members: dict[str, int] = {}
    for dname, count in dept_counts.items():
        did = f"DEP_{dname[:3].upper()}"
        departments.append({"department_id": did, "name": dname})
        remaining = count
        while remaining > 0:
            size = min(remaining, rng.randint(org["team_size"]["min"], org["team_size"]["max"]))
            if remaining - size < org["team_size"]["min"] // 2:
                size = remaining
            tseq += 1
            tid = f"TEAM_{tseq:03d}"
            days = org["team_office_days"].get(dname) or sorted(rng.sample([1, 2, 3, 4, 5], 3))
            teams.append({"team_id": tid, "department_id": did, "department": dname,
                          "name": f"{dname} Team {tseq}", "office_days": days})
            team_members[tid] = size
            remaining -= size

    # place teams on floors and zones (sequential fill keeps departments clustered)
    floors = layout["floors"]
    ws_zones = {f["floor_id"]: [z for z in layout["zones"] if z["floor_id"] == f["floor_id"]
                                and z["zone_type"] == "OPEN_WORKSPACE"] for f in floors}
    per_floor_target = n_emp / len(floors)
    fi, load = 0, 0
    zone_load = {z["zone_id"]: 0 for zs in ws_zones.values() for z in zs}
    allocations = []
    for t in teams:
        if load >= per_floor_target and fi < len(floors) - 1:
            fi, load = fi + 1, 0
        fid = floors[fi]["floor_id"]
        load += team_members[t["team_id"]]
        zs = ws_zones[fid]
        primary = min(zs, key=lambda z: zone_load[z["zone_id"]] / max(z["capacity"], 1))
        zone_load[primary["zone_id"]] += team_members[t["team_id"]]
        t["home_floor_id"], t["primary_zone_id"] = fid, primary["zone_id"]
        allocations.append({"team_id": t["team_id"], "zone_id": primary["zone_id"], "share": 0.8})
        others = [z for z in zs if z is not primary]
        if others:
            allocations.append({"team_id": t["team_id"], "zone_id": rng.choice(others)["zone_id"], "share": 0.2})
        else:
            allocations[-1]["share"] = 1.0

    # restricted zones
    for t in teams:
        if t["department"] in cfg["layout"]["restricted_departments"]:
            z = next(z for z in layout["zones"] if z["zone_id"] == t["primary_zone_id"])
            if not z["is_restricted"]:
                z["is_restricted"] = True
                layout["access_points"].append({
                    "access_point_id": f"AP_{z['zone_id']}_SECURE", "floor_id": z["floor_id"],
                    "reader_type": "SECURE_ZONE", "target_id": z["zone_id"], "direction": "IN",
                    "x": z["x"] + 0.5, "y": z["y"] + z["height"] / 2})
            z.setdefault("allowed_team_ids", []).append(t["team_id"])

    # employees
    employees, patterns = [], []
    eseq = 0
    dept_head: dict[str, str] = {}
    for t in teams:
        lead = None
        for i in range(team_members[t["team_id"]]):
            eseq += 1
            eid = f"EMP{eseq:06d}"
            fn, ln = rng.choice(FIRST), rng.choice(LAST)
            dname = t["department"]
            if dname not in dept_head:
                role, manager = f"Head of {dname}", None
                dept_head[dname] = eid
            elif i == 0:
                role, manager = "Team Lead", dept_head[dname]
            else:
                role, manager = rng.choice(ROLES[dname]), lead or dept_head[dname]
            if i == 0:
                lead = eid
            mode = weighted_choice(rng, org["work_mode_mix"])
            profile = weighted_choice(rng, org["profile_mix"])
            if mode == "REMOTE" and rng.random() < 0.5:
                profile = "REMOTE_HEAVY"
            employees.append({
                "employee_id": eid, "employee_name": f"{fn} {ln}",
                "email": f"{fn.lower()}.{ln.lower()}.{eseq}@example-corp.com".replace("ü", "u"),
                "team_id": t["team_id"], "department_id": next(d["department_id"] for d in departments if d["name"] == dname),
                "department": dname, "job_role": role, "manager_id": manager or "",
                "home_floor_id": t["home_floor_id"], "preferred_zone_id": t["primary_zone_id"],
                "employment_type": weighted_choice(rng, org["employment_type_mix"]),
                "work_mode": mode, "behavior_profile": profile, "active_flag": True})
            flex_day = rng.choice([d for d in range(1, 6) if d not in t["office_days"]] or [5])
            for wd in range(1, 8):
                if wd > 5:
                    pm = "REMOTE"
                elif mode == "OFFICE":
                    pm = "OFFICE"
                elif mode == "REMOTE":
                    pm = "REMOTE"
                else:
                    pm = "OFFICE" if wd in t["office_days"] else ("FLEX" if wd == flex_day and rng.random() < 0.3 else "REMOTE")
                patterns.append({"employee_id": eid, "iso_weekday": wd, "planned_mode": pm})

    # assigned desks on ASSIGNED floors
    assignments = []
    for f in floors:
        if f["desk_policy"] != "ASSIGNED":
            continue
        free = {z["zone_id"]: [w["workspace_id"] for w in layout["workspaces"] if w["zone_id"] == z["zone_id"]]
                for z in ws_zones[f["floor_id"]]}
        for e in employees:
            if e["home_floor_id"] == f["floor_id"] and e["work_mode"] != "REMOTE":
                pool = free[e["preferred_zone_id"]] or next((v for v in free.values() if v), [])
                if pool:
                    assignments.append({"employee_id": e["employee_id"], "workspace_id": pool.pop(0),
                                        "valid_from": "2026-01-01"})

    return {"departments": departments, "teams": teams, "team_zone_allocation": allocations,
            "employees": employees, "employee_work_pattern": patterns, "workspace_assignment": assignments}


def write_master(out: Path, layout: dict, master: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "layout.json").write_text(json.dumps(layout, indent=1))
    tables = {
        "buildings": [layout["building"]], "floors": layout["floors"], "zones": layout["zones"],
        "workspaces": layout["workspaces"], "rooms": layout["rooms"], "access_points": layout["access_points"],
        "sensors": layout["sensors"], **master}
    for name, rows in tables.items():
        if not rows:
            continue
        keys = list(dict.fromkeys(k for r in rows for k in r))
        with open(out / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys, lineterminator="\n")
            w.writeheader()
            for r in rows:
                w.writerow({k: (json.dumps(v) if isinstance(v, (list, dict)) else v) for k, v in r.items()})
