def test_buildings_with_floor_capacity(client) -> None:
    buildings = client.get("/api/v1/buildings").json()
    assert len(buildings) == 1
    floors = buildings[0]["floors"]
    assert [f["floor_number"] for f in floors] == [1, 2, 3, 4]
    assert sum(f["desks"] for f in floors) == 800
    assert sum(f["home_employees"] for f in floors) == 1000
    readers = {ap["reader_type"] for ap in buildings[0]["access_points"]}
    assert readers == {"BUILDING_ENTRANCE", "FLOOR_LOBBY", "ROOM_DOOR", "SECURE_ZONE"}
    assert all(f["readers"] > 0 for f in floors)


def test_floor_layout(client) -> None:
    layout = client.get("/api/v1/floors/BLD01_F02/layout").json()
    assert layout["plan_width"] > 0
    assert len(layout["zones"]) == 10
    assert len(layout["workspaces"]) == 200
    assert client.get("/api/v1/floors/NOPE/layout").status_code == 404


def test_employees_paging_and_filters(client) -> None:
    page = client.get("/api/v1/employees", params={"page_size": 25, "page": 2}).json()
    assert page["total"] == 1000 and len(page["items"]) == 25
    assert page["items"][0]["employee_id"] == "EMP000026"

    facets = client.get("/api/v1/employees/facets").json()
    hybrid = next(f["count"] for f in facets["work_mode"] if f["value"] == "HYBRID")
    filtered = client.get("/api/v1/employees", params={"work_mode": "HYBRID"}).json()
    assert filtered["total"] == hybrid

    first = page["items"][0]
    found = client.get("/api/v1/employees", params={"search": first["email"]}).json()
    assert [e["employee_id"] for e in found["items"]] == [first["employee_id"]]


def test_teams_departments_rooms_sensors(client) -> None:
    teams = client.get("/api/v1/teams").json()
    assert all(abs(sum(a["share"] for a in t["zone_allocations"]) - 1) < 1e-6 for t in teams)
    assert sum(t["members"] for t in teams) == 1000

    departments = client.get("/api/v1/departments").json()
    assert sum(d["employees"] for d in departments) == 1000

    rooms = client.get("/api/v1/rooms", params={"room_type": "COMMON_AREA"}).json()
    assert {r["area_subtype"] for r in rooms} >= {"CAFETERIA"}

    env = client.get("/api/v1/sensors", params={"sensor_type": "ENVIRONMENT"}).json()
    assert env["total"] == 40


def test_health_includes_master_data(client) -> None:
    body = client.get("/health").json()
    assert body["components"]["master_data"]["status"] == "ok"
    assert body["status"] == "ok"


def test_access_points_and_secure_zones(client) -> None:
    lobby = client.get("/api/v1/access-points", params={"reader_type": "FLOOR_LOBBY"}).json()
    assert [ap["access_point_id"] for ap in lobby] == [
        "AP_BLD01_F02_LOBBY",
        "AP_BLD01_F03_LOBBY",
        "AP_BLD01_F04_LOBBY",
    ]
    secure = client.get("/api/v1/access-points", params={"reader_type": "SECURE_ZONE"}).json()
    assert secure
    zone_ids = {ap["target_id"] for ap in secure}
    zones = client.get("/api/v1/zones").json()
    assert {z["zone_id"] for z in zones if z["is_restricted"]} == zone_ids
    teams = client.get("/api/v1/teams").json()
    assert {s["zone_id"] for t in teams for s in t["secure_zones"]} == zone_ids

    rooms = client.get("/api/v1/rooms", params={"room_type": "LARGE_CONFERENCE"}).json()
    assert rooms and all(r["has_badge_reader"] and r["has_panel"] for r in rooms)
