"""
DroZon Backend API tests — pytest.
Covers: root, drones CRUD, bulk-seed idempotency, missions, alerts, stats, error cases.
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    # fallback to reading frontend .env
    from pathlib import Path
    env = Path("/app/frontend/.env").read_text()
    for line in env.splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().strip('"')
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="session")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def created_ids():
    return {"drones": [], "missions": [], "alerts": []}


# ═══════════════════════════════════════════════════════════
# Health / root
# ═══════════════════════════════════════════════════════════
class TestRoot:
    def test_root_operational(self, client):
        r = client.get(f"{API}/")
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "operational"
        assert "time" in data
        assert data.get("message") == "DroZon API"


# ═══════════════════════════════════════════════════════════
# Drones CRUD
# ═══════════════════════════════════════════════════════════
class TestDronesCRUD:
    def test_list_drones_ok(self, client):
        r = client.get(f"{API}/drones")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_create_drone_and_get(self, client, created_ids):
        payload = {
            "name": "TEST_Drone_A",
            "model": "MavicTest",
            "droneType": "quad",
            "status": "standby",
            "lat": 44.4268,
            "lng": 26.1025,
            "battery": 88.5,
        }
        r = client.post(f"{API}/drones", json=payload)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["name"] == "TEST_Drone_A"
        assert d["lat"] == 44.4268
        assert isinstance(d["id"], str) and len(d["id"]) > 0
        created_ids["drones"].append(d["id"])

        # GET verify persistence
        g = client.get(f"{API}/drones/{d['id']}")
        assert g.status_code == 200
        assert g.json()["name"] == "TEST_Drone_A"

    def test_update_drone(self, client, created_ids):
        if not created_ids["drones"]:
            pytest.skip("no created drone")
        did = created_ids["drones"][0]
        r = client.put(f"{API}/drones/{did}", json={"status": "misiune", "battery": 55.0})
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "misiune"
        assert d["battery"] == 55.0
        # Verify GET
        g = client.get(f"{API}/drones/{did}").json()
        assert g["status"] == "misiune"
        assert g["battery"] == 55.0

    def test_get_drone_404(self, client):
        r = client.get(f"{API}/drones/nonexistent-{uuid.uuid4()}")
        assert r.status_code == 404

    def test_update_drone_404(self, client):
        r = client.put(f"{API}/drones/nonexistent-{uuid.uuid4()}", json={"status": "activ"})
        assert r.status_code == 404

    def test_delete_drone_404(self, client):
        r = client.delete(f"{API}/drones/nonexistent-{uuid.uuid4()}")
        assert r.status_code == 404

    def test_create_drone_validation_error(self, client):
        # Missing required lat/lng
        r = client.post(f"{API}/drones", json={"name": "TEST_missing_coords"})
        assert r.status_code == 422

    def test_bulk_seed_idempotent(self, client):
        # Since we created drones already, DB is not empty -> seed should skip
        payload = [
            {"name": "TEST_seed_1", "lat": 45.0, "lng": 25.0},
            {"name": "TEST_seed_2", "lat": 45.1, "lng": 25.1},
        ]
        r = client.post(f"{API}/drones/bulk-seed", json=payload)
        assert r.status_code == 200
        d = r.json()
        assert d["seeded"] == 0
        assert "Already" in d.get("message", "")

    def test_delete_drone(self, client, created_ids):
        if not created_ids["drones"]:
            pytest.skip("no created drone")
        did = created_ids["drones"][0]
        r = client.delete(f"{API}/drones/{did}")
        assert r.status_code == 200
        assert r.json().get("deleted") == did
        # Verify gone
        g = client.get(f"{API}/drones/{did}")
        assert g.status_code == 404
        created_ids["drones"].remove(did)


# ═══════════════════════════════════════════════════════════
# Missions
# ═══════════════════════════════════════════════════════════
class TestMissions:
    def test_create_mission(self, client, created_ids):
        payload = {
            "droneId": "test-drone-xyz",
            "type": "salvare",
            "title": "TEST_mission_1",
            "startLat": 44.4,
            "startLng": 26.1,
            "destLat": 44.5,
            "destLng": 26.2,
        }
        r = client.post(f"{API}/missions", json=payload)
        assert r.status_code == 200, r.text
        m = r.json()
        assert m["title"] == "TEST_mission_1"
        assert m["status"] == "active"
        assert isinstance(m["id"], str)
        created_ids["missions"].append(m["id"])

    def test_list_missions(self, client):
        r = client.get(f"{API}/missions")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_list_missions_filter(self, client):
        r = client.get(f"{API}/missions", params={"status": "active"})
        assert r.status_code == 200
        for m in r.json():
            assert m["status"] == "active"

    def test_update_mission(self, client, created_ids):
        if not created_ids["missions"]:
            pytest.skip("no mission")
        mid = created_ids["missions"][0]
        r = client.put(f"{API}/missions/{mid}", json={"status": "completed"})
        assert r.status_code == 200
        assert r.json()["status"] == "completed"

    def test_update_mission_404(self, client):
        r = client.put(f"{API}/missions/nonexistent-{uuid.uuid4()}", json={"status": "aborted"})
        assert r.status_code == 404

    def test_create_mission_validation(self, client):
        # Missing required fields
        r = client.post(f"{API}/missions", json={"droneId": "x"})
        assert r.status_code == 422


# ═══════════════════════════════════════════════════════════
# Alerts
# ═══════════════════════════════════════════════════════════
class TestAlerts:
    def test_create_alert(self, client, created_ids):
        payload = {
            "droneId": "test-drone-alert",
            "severity": "warning",
            "type": "battery_low",
            "message": "TEST_battery_low",
        }
        r = client.post(f"{API}/alerts", json=payload)
        assert r.status_code == 200, r.text
        a = r.json()
        assert a["message"] == "TEST_battery_low"
        assert a["acknowledged"] is False
        assert isinstance(a["id"], str)
        created_ids["alerts"].append(a["id"])

    def test_list_alerts(self, client):
        r = client.get(f"{API}/alerts")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_list_alerts_filter_unack(self, client):
        r = client.get(f"{API}/alerts", params={"acknowledged": "false"})
        assert r.status_code == 200
        for a in r.json():
            assert a["acknowledged"] is False

    def test_ack_alert(self, client, created_ids):
        if not created_ids["alerts"]:
            pytest.skip("no alert")
        aid = created_ids["alerts"][0]
        r = client.post(f"{API}/alerts/{aid}/ack")
        assert r.status_code == 200
        assert r.json().get("acknowledged") == aid

        # Verify persisted via filter acknowledged=true
        r2 = client.get(f"{API}/alerts", params={"acknowledged": "true"})
        assert r2.status_code == 200
        assert any(x["id"] == aid for x in r2.json())

    def test_ack_alert_404(self, client):
        r = client.post(f"{API}/alerts/nonexistent-{uuid.uuid4()}/ack")
        assert r.status_code == 404

    def test_create_alert_validation(self, client):
        r = client.post(f"{API}/alerts", json={"droneId": "x"})
        assert r.status_code == 422


# ═══════════════════════════════════════════════════════════
# Stats
# ═══════════════════════════════════════════════════════════
class TestStats:
    def test_stats_shape(self, client):
        r = client.get(f"{API}/stats")
        assert r.status_code == 200
        d = r.json()
        assert "drones" in d and isinstance(d["drones"], dict)
        for k in ("total", "activ", "misiune", "standby", "pericol"):
            assert k in d["drones"]
            assert isinstance(d["drones"][k], int)
        assert "missions_active" in d and isinstance(d["missions_active"], int)
        assert "alerts_unacknowledged" in d and isinstance(d["alerts_unacknowledged"], int)
        assert "time" in d


# ═══════════════════════════════════════════════════════════
# Cleanup
# ═══════════════════════════════════════════════════════════
def test_cleanup_zzz(client, created_ids):
    """Final cleanup of TEST_ data (runs last alphabetically)."""
    for did in list(created_ids["drones"]):
        client.delete(f"{API}/drones/{did}")
    # missions/alerts have no DELETE endpoint — leave TEST_ prefixed
