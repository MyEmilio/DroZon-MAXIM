"""DroZon Sprint 1 backend regression tests.

Covers:
- Auth (login, register, me, logout, refresh)
- Role gates (commander/pilot/observer)
- User admin CRUD
- Missions CRUD (role-gated)
- Telemetry, SOS + ACK
- Drone adapters
- Brute-force lockout
- Health
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else None
if not BASE_URL:
    # fall back to reading frontend .env
    from pathlib import Path
    for line in Path("/app/frontend/.env").read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
            break

API = f"{BASE_URL}/api"

CRED = {
    "commander": {"email": "comandant@drozon.ro", "password": "Comandant2026!"},
    "pilot":     {"email": "pilot@drozon.ro",     "password": "Pilot2026!"},
    "observer":  {"email": "observer@drozon.ro",  "password": "Observer2026!"},
}


def _session_for(role: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=CRED[role])
    assert r.status_code == 200, f"login {role} failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def commander(): return _session_for("commander")

@pytest.fixture(scope="module")
def pilot(): return _session_for("pilot")

@pytest.fixture(scope="module")
def observer(): return _session_for("observer")


# ── Health ────────────────────────────────────────────────────────────
class TestHealth:
    def test_health(self):
        r = requests.get(f"{API}/health")
        assert r.status_code == 200
        assert r.json()["ok"] is True


# ── Auth ──────────────────────────────────────────────────────────────
class TestAuth:
    def test_login_commander(self):
        s = requests.Session()
        r = s.post(f"{API}/auth/login", json=CRED["commander"])
        assert r.status_code == 200
        data = r.json()
        assert data["user"]["role"] == "commander"
        assert data["user"]["callsign"] == "ACTUAL-6"
        assert "access_token" in s.cookies
        assert "refresh_token" in s.cookies

    def test_login_pilot(self):
        r = requests.post(f"{API}/auth/login", json=CRED["pilot"])
        assert r.status_code == 200
        assert r.json()["user"]["role"] == "pilot"

    def test_login_observer(self):
        r = requests.post(f"{API}/auth/login", json=CRED["observer"])
        assert r.status_code == 200
        assert r.json()["user"]["role"] == "observer"

    def test_login_wrong_password(self):
        # unique email so it doesn't collide with lockout counter of others
        r = requests.post(f"{API}/auth/login", json={
            "email": f"nouser+{uuid.uuid4().hex[:8]}@drozon.ro",
            "password": "wrongpass!!"
        })
        assert r.status_code == 401
        assert "incorect" in r.json()["detail"].lower()

    def test_me_without_cookie(self):
        r = requests.get(f"{API}/auth/me")
        assert r.status_code == 401

    def test_me_with_cookie(self, commander):
        r = commander.get(f"{API}/auth/me")
        assert r.status_code == 200
        d = r.json()
        for k in ("id", "email", "name", "role", "callsign", "unit"):
            assert k in d
        assert d["role"] == "commander"

    def test_logout_clears_cookies(self):
        s = _session_for("observer")
        r = s.post(f"{API}/auth/logout")
        assert r.status_code == 200
        # Cookie deletion may either remove or blank; verify /me is 401 on new session with same cookies
        r2 = s.get(f"{API}/auth/me")
        assert r2.status_code == 401


# ── Registration & role gating ────────────────────────────────────────
class TestRegistration:
    def test_public_register_observer(self):
        email = f"TEST_obs_{uuid.uuid4().hex[:8]}@drozon.ro"
        r = requests.post(f"{API}/auth/register", json={
            "email": email, "password": "Test1234!", "name": "Obs Test",
            "role": "observer", "callsign": "TST-OBS", "unit": "Test"
        })
        assert r.status_code == 200, r.text
        assert r.json()["user"]["role"] == "observer"

    def test_public_register_pilot_forbidden(self):
        r = requests.post(f"{API}/auth/register", json={
            "email": f"TEST_pi_{uuid.uuid4().hex[:8]}@drozon.ro",
            "password": "Test1234!", "name": "Pi Test", "role": "pilot",
        })
        assert r.status_code == 403

    def test_public_register_commander_forbidden(self):
        r = requests.post(f"{API}/auth/register", json={
            "email": f"TEST_cmd_{uuid.uuid4().hex[:8]}@drozon.ro",
            "password": "Test1234!", "name": "Cmd Test", "role": "commander",
        })
        assert r.status_code == 403

    def test_commander_can_create_pilot(self):
        # Use a fresh commander session — register mutates the caller's cookies
        # (sets them to the newly-created user) so we must not use the shared fixture.
        cmd = _session_for("commander")
        email = f"TEST_pilot_{uuid.uuid4().hex[:8]}@drozon.ro"
        r = cmd.post(f"{API}/auth/register", json={
            "email": email, "password": "Test1234!", "name": "Pilot Test",
            "role": "pilot", "callsign": "TST-PIL", "unit": "Test",
        })
        assert r.status_code == 200, r.text
        assert r.json()["user"]["role"] == "pilot"

    def test_pilot_cannot_create_pilot(self, pilot):
        r = pilot.post(f"{API}/auth/register", json={
            "email": f"TEST_p2_{uuid.uuid4().hex[:8]}@drozon.ro",
            "password": "Test1234!", "name": "Bad", "role": "pilot",
        })
        assert r.status_code == 403


# ── Users admin ───────────────────────────────────────────────────────
class TestUsersAdmin:
    def test_list_users_commander(self, commander):
        r = commander.get(f"{API}/users")
        assert r.status_code == 200
        users = r.json()
        assert isinstance(users, list)
        emails = {u["email"] for u in users}
        assert "comandant@drozon.ro" in emails
        assert "pilot@drozon.ro" in emails

    def test_list_users_pilot_forbidden(self, pilot):
        r = pilot.get(f"{API}/users")
        assert r.status_code == 403

    def test_list_users_observer_forbidden(self, observer):
        r = observer.get(f"{API}/users")
        assert r.status_code == 403

    def test_patch_role_pilot_forbidden(self, pilot, commander):
        # get some user id
        users = commander.get(f"{API}/users").json()
        target = next(u for u in users if u["role"] == "observer")
        r = pilot.patch(f"{API}/users/{target['id']}/role", json={"role": "pilot"})
        assert r.status_code == 403

    def test_delete_self_forbidden(self, commander):
        me = commander.get(f"{API}/auth/me").json()
        r = commander.delete(f"{API}/users/{me['id']}")
        assert r.status_code == 400

    def test_delete_user_by_commander(self):
        # Use a fresh commander session — register mutates cookies of the caller
        cmd_creator = _session_for("commander")
        email = f"TEST_del_{uuid.uuid4().hex[:8]}@drozon.ro"
        cr = cmd_creator.post(f"{API}/auth/register", json={
            "email": email, "password": "Test1234!", "name": "Del Test",
            "role": "pilot",
        })
        assert cr.status_code == 200, cr.text
        # register-side effect: cmd_creator now holds the new pilot's cookies.
        # Use a second fresh commander session for the delete flow.
        cmd2 = _session_for("commander")
        users = cmd2.get(f"{API}/users").json()
        target = next((u for u in users if u["email"] == email.lower()), None)
        assert target is not None, f"created user {email} not found in list"
        dr = cmd2.delete(f"{API}/users/{target['id']}")
        assert dr.status_code == 200


# ── Missions ──────────────────────────────────────────────────────────
class TestMissions:
    def test_create_mission_as_pilot(self, pilot):
        r = pilot.post(f"{API}/missions", json={
            "name": "TEST Mission Rescue",
            "mission_type": "rescue",
            "drone_ids": ["VULTUR-01"],
            "waypoints": [{"lat": 45.5, "lng": 25.5, "alt": 100, "action": "search"}],
            "priority": "urgent",
        })
        assert r.status_code == 200, r.text
        m = r.json()
        assert m["status"] == "planned"
        assert m["name"] == "TEST Mission Rescue"
        assert "id" in m and isinstance(m["id"], str)
        assert "_id" not in m  # regression: no ObjectId leak

    def test_create_mission_as_observer_forbidden(self, observer):
        r = observer.post(f"{API}/missions", json={
            "name": "obs mission", "mission_type": "rescue"
        })
        assert r.status_code == 403

    def test_delete_mission_pilot_forbidden(self, pilot):
        m = pilot.post(f"{API}/missions", json={
            "name": "TEST del by pilot", "mission_type": "rescue"
        }).json()
        r = pilot.delete(f"{API}/missions/{m['id']}")
        assert r.status_code == 403

    def test_delete_mission_commander_ok(self, pilot):
        # Use fresh commander session to avoid any prior test polluting shared cookies
        cmd = _session_for("commander")
        m = pilot.post(f"{API}/missions", json={
            "name": "TEST cmd del", "mission_type": "rescue"
        }).json()
        r = cmd.delete(f"{API}/missions/{m['id']}")
        assert r.status_code == 200


# ── Telemetry & SOS ───────────────────────────────────────────────────
class TestTelemetryAndSOS:
    def test_telemetry_as_pilot(self, pilot):
        r = pilot.post(f"{API}/telemetry", json={
            "drone_id": "VULTUR-01", "lat": 45.5, "lng": 25.5, "alt": 100,
            "battery": 80, "speed": 12, "heading": 180, "status": "flying",
        })
        assert r.status_code == 200

    def test_telemetry_as_observer_forbidden(self, observer):
        r = observer.post(f"{API}/telemetry", json={
            "drone_id": "VULTUR-01", "lat": 45.5, "lng": 25.5, "alt": 100,
            "battery": 80, "speed": 12, "heading": 180, "status": "flying",
        })
        assert r.status_code == 403

    def test_sos_any_authenticated(self, observer, pilot, commander):
        for s in (observer, pilot, commander):
            r = s.post(f"{API}/sos", json={
                "drone_id": "TEST-SOS", "lat": 45.0, "lng": 25.0,
                "reason": "TEST — distress"
            })
            assert r.status_code == 200, f"role {s} SOS failed"

    def test_sos_ack_observer_forbidden(self, observer, pilot):
        # create a fresh sos as pilot (or anyone)
        sos = pilot.post(f"{API}/sos", json={
            "drone_id": "TEST-SOS-ACK", "lat": 1.0, "lng": 2.0, "reason": "TEST"
        }).json()
        r = observer.patch(f"{API}/sos/{sos['id']}/ack")
        assert r.status_code == 403

    def test_sos_ack_commander_ok(self, commander, pilot):
        sos = pilot.post(f"{API}/sos", json={
            "drone_id": "TEST-SOS-ACK2", "lat": 1.0, "lng": 2.0, "reason": "TEST"
        }).json()
        r = commander.patch(f"{API}/sos/{sos['id']}/ack")
        assert r.status_code == 200


# ── Adapters ──────────────────────────────────────────────────────────
class TestDroneAdapters:
    def test_adapters_list(self, observer):
        r = observer.get(f"{API}/drone-adapters")
        assert r.status_code == 200
        adapters = r.json()["adapters"]
        assert len(adapters) == 4
        ids = {a["id"] for a in adapters}
        assert ids == {"dji", "mavlink", "autel", "parrot"}
        # DJI and mavlink should be 'ready'
        ready = {a["id"] for a in adapters if a["status"] == "ready"}
        assert "dji" in ready and "mavlink" in ready


# ── Brute-force lockout ───────────────────────────────────────────────
class TestBruteForce:
    def test_lockout_after_5_failed(self):
        # Use a unique email so we don't pollute real accounts' lockout counters
        email = f"brute_{uuid.uuid4().hex[:8]}@drozon.ro"
        s = requests.Session()
        # 5 failed attempts should trigger 429 on the 6th (or on the 5th's response)
        codes = []
        for i in range(7):
            r = s.post(f"{API}/auth/login", json={"email": email, "password": "wrong!!"})
            codes.append(r.status_code)
        # After BRUTE_MAX(5) failed attempts we expect at least one 429 in subsequent calls
        assert 429 in codes, f"expected 429 lockout somewhere, got {codes}"
