"""DroZon Backend — Auth (JWT + roles), Missions API, Telemetry sync."""
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import uuid
import logging
import bcrypt
import jwt
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Literal

from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr, Field, ConfigDict

# ────────────────────────────────────────────────────────────────
# Config
# ────────────────────────────────────────────────────────────────
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALG = "HS256"
ACCESS_TTL_MIN = 60 * 8          # 8h — long shift
REFRESH_TTL_DAYS = 30
BRUTE_MAX = 5
BRUTE_WINDOW_MIN = 15

ROLES = ("commander", "pilot", "observer")
Role = Literal["commander", "pilot", "observer"]

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

app = FastAPI(title="DroZon API")
api = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s :: %(message)s")
log = logging.getLogger("drozon")


# ────────────────────────────────────────────────────────────────
# Utils — password + JWT
# ────────────────────────────────────────────────────────────────
def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()

def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except Exception:
        return False

def create_access_token(user_id: str, email: str, role: str) -> str:
    payload = {
        "sub": user_id, "email": email, "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TTL_MIN),
        "type": "access",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

def create_refresh_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=REFRESH_TTL_DAYS),
        "type": "refresh",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

def set_auth_cookies(resp: Response, access: str, refresh: str):
    resp.set_cookie("access_token", access, httponly=True, secure=False, samesite="lax",
                    max_age=ACCESS_TTL_MIN * 60, path="/")
    resp.set_cookie("refresh_token", refresh, httponly=True, secure=False, samesite="lax",
                    max_age=REFRESH_TTL_DAYS * 24 * 3600, path="/")

def clear_auth_cookies(resp: Response):
    resp.delete_cookie("access_token", path="/")
    resp.delete_cookie("refresh_token", path="/")


# ────────────────────────────────────────────────────────────────
# Models
# ────────────────────────────────────────────────────────────────
class UserPublic(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    email: str
    name: str
    role: Role
    callsign: Optional[str] = None
    unit: Optional[str] = None
    created_at: datetime

class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: str
    role: Role = "observer"
    callsign: Optional[str] = None
    unit: Optional[str] = None

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class UserRoleUpdate(BaseModel):
    role: Role

class MissionIn(BaseModel):
    name: str
    mission_type: str   # rescue, swarm, waypoint, stingere, medical, etc.
    drone_ids: List[str] = []
    waypoints: List[dict] = []   # [{lat, lng, alt, action}]
    priority: str = "normal"     # normal, urgent, critical
    notes: Optional[str] = None

class MissionOut(MissionIn):
    id: str
    status: str
    created_by: str
    created_at: datetime
    updated_at: datetime

class TelemetryIn(BaseModel):
    drone_id: str
    lat: float
    lng: float
    alt: float
    battery: float
    speed: float
    heading: float
    status: str
    mission_id: Optional[str] = None
    extra: Optional[dict] = None

class SOSIn(BaseModel):
    drone_id: str
    lat: float
    lng: float
    reason: str
    battery: Optional[float] = None


# ────────────────────────────────────────────────────────────────
# Auth helpers
# ────────────────────────────────────────────────────────────────
def _extract_token(request: Request) -> Optional[str]:
    tok = request.cookies.get("access_token")
    if tok:
        return tok
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None

async def get_current_user(request: Request) -> dict:
    tok = _extract_token(request)
    if not tok:
        raise HTTPException(status_code=401, detail="Nu ești autentificat")
    try:
        payload = jwt.decode(tok, JWT_SECRET, algorithms=[JWT_ALG])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Token invalid")
        user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
        if not user:
            raise HTTPException(status_code=401, detail="Utilizator inexistent")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Sesiune expirată")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token invalid")

def require_role(*allowed: str):
    async def dep(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in allowed:
            raise HTTPException(status_code=403, detail=f"Rol insuficient. Necesar: {', '.join(allowed)}")
        return user
    return dep


# ────────────────────────────────────────────────────────────────
# Brute force protection
# ────────────────────────────────────────────────────────────────
async def check_lockout(ip: str, email: str):
    key = f"{ip}:{email.lower()}"
    doc = await db.login_attempts.find_one({"identifier": key})
    if not doc:
        return
    if doc.get("locked_until") and doc["locked_until"] > datetime.now(timezone.utc):
        raise HTTPException(status_code=429, detail=f"Prea multe încercări. Blocat până la {doc['locked_until'].isoformat()}")

async def record_failed(ip: str, email: str):
    key = f"{ip}:{email.lower()}"
    now = datetime.now(timezone.utc)
    doc = await db.login_attempts.find_one({"identifier": key})
    count = (doc["count"] if doc else 0) + 1
    update = {"count": count, "last_attempt": now}
    if count >= BRUTE_MAX:
        update["locked_until"] = now + timedelta(minutes=BRUTE_WINDOW_MIN)
        update["count"] = 0
    await db.login_attempts.update_one({"identifier": key}, {"$set": update}, upsert=True)

async def clear_attempts(ip: str, email: str):
    key = f"{ip}:{email.lower()}"
    await db.login_attempts.delete_one({"identifier": key})


# ────────────────────────────────────────────────────────────────
# Startup — indexes + seed
# ────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def on_startup():
    await db.users.create_index("email", unique=True)
    await db.users.create_index("id", unique=True)
    await db.login_attempts.create_index("identifier")
    await db.missions.create_index("id", unique=True)
    await db.telemetry.create_index([("drone_id", 1), ("ts", -1)])
    await db.sos_events.create_index([("ts", -1)])

    # Seed admin (commander)
    admin_email = os.environ.get("ADMIN_EMAIL", "comandant@drozon.ro").lower()
    admin_pw = os.environ.get("ADMIN_PASSWORD", "Comandant2026!")
    existing = await db.users.find_one({"email": admin_email})
    if not existing:
        await db.users.insert_one({
            "id": str(uuid.uuid4()),
            "email": admin_email,
            "password_hash": hash_password(admin_pw),
            "name": "Comandant Principal",
            "role": "commander",
            "callsign": "ACTUAL-6",
            "unit": "DroZon Command",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        log.info(f"Seeded admin commander: {admin_email}")
    elif not verify_password(admin_pw, existing["password_hash"]):
        await db.users.update_one(
            {"email": admin_email},
            {"$set": {"password_hash": hash_password(admin_pw), "role": "commander"}},
        )
        log.info("Rotated admin password hash to match .env")

    # Seed demo pilot + observer if missing (for demo purposes)
    for demo in [
        {"email": "pilot@drozon.ro", "password": "Pilot2026!", "name": "Pilot Demo",
         "role": "pilot", "callsign": "HAWK-1", "unit": "Squadron Alpha"},
        {"email": "observer@drozon.ro", "password": "Observer2026!", "name": "Observator Demo",
         "role": "observer", "callsign": "EYE-1", "unit": "ISU București"},
    ]:
        if not await db.users.find_one({"email": demo["email"]}):
            await db.users.insert_one({
                "id": str(uuid.uuid4()),
                "email": demo["email"],
                "password_hash": hash_password(demo["password"]),
                "name": demo["name"],
                "role": demo["role"],
                "callsign": demo["callsign"],
                "unit": demo["unit"],
                "created_at": datetime.now(timezone.utc).isoformat(),
            })


@app.on_event("shutdown")
async def shutdown():
    client.close()


# ────────────────────────────────────────────────────────────────
# Auth endpoints
# ────────────────────────────────────────────────────────────────
def user_public(u: dict) -> dict:
    return {
        "id": u["id"], "email": u["email"], "name": u["name"], "role": u["role"],
        "callsign": u.get("callsign"), "unit": u.get("unit"),
        "created_at": u["created_at"],
    }

@api.post("/auth/register")
async def register(data: RegisterIn, request: Request, response: Response,
                   me: Optional[dict] = None):
    # Public registration only creates observers. Only commanders can create pilots/commanders.
    tok = _extract_token(request)
    role_wanted = data.role
    if role_wanted != "observer":
        if not tok:
            raise HTTPException(status_code=403, detail="Doar comandantul poate crea piloți/comandanți")
        try:
            payload = jwt.decode(tok, JWT_SECRET, algorithms=[JWT_ALG])
            actor = await db.users.find_one({"id": payload["sub"]})
            if not actor or actor["role"] != "commander":
                raise HTTPException(status_code=403, detail="Doar comandantul poate crea acest rol")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=401, detail="Token invalid")

    email = data.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=409, detail="Email deja înregistrat")
    user = {
        "id": str(uuid.uuid4()),
        "email": email,
        "password_hash": hash_password(data.password),
        "name": data.name,
        "role": role_wanted,
        "callsign": data.callsign,
        "unit": data.unit,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(user)
    access = create_access_token(user["id"], user["email"], user["role"])
    refresh = create_refresh_token(user["id"])
    set_auth_cookies(response, access, refresh)
    return {"user": user_public(user), "access_token": access}


@api.post("/auth/login")
async def login(data: LoginIn, request: Request, response: Response):
    email = data.email.lower()
    ip = request.client.host if request.client else "unknown"
    await check_lockout(ip, email)
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(data.password, user["password_hash"]):
        await record_failed(ip, email)
        raise HTTPException(status_code=401, detail="Email sau parolă incorectă")
    await clear_attempts(ip, email)
    access = create_access_token(user["id"], user["email"], user["role"])
    refresh = create_refresh_token(user["id"])
    set_auth_cookies(response, access, refresh)
    return {"user": user_public(user), "access_token": access}


@api.post("/auth/logout")
async def logout(response: Response, _: dict = Depends(get_current_user)):
    clear_auth_cookies(response)
    return {"ok": True}


@api.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return user_public(user)


@api.post("/auth/refresh")
async def refresh_token(request: Request, response: Response):
    tok = request.cookies.get("refresh_token")
    if not tok:
        raise HTTPException(status_code=401, detail="No refresh token")
    try:
        payload = jwt.decode(tok, JWT_SECRET, algorithms=[JWT_ALG])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = await db.users.find_one({"id": payload["sub"]})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        access = create_access_token(user["id"], user["email"], user["role"])
        response.set_cookie("access_token", access, httponly=True, secure=False,
                            samesite="lax", max_age=ACCESS_TTL_MIN * 60, path="/")
        return {"ok": True}
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")


# ────────────────────────────────────────────────────────────────
# User management (commander only)
# ────────────────────────────────────────────────────────────────
@api.get("/users")
async def list_users(_: dict = Depends(require_role("commander"))):
    users = await db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(500)
    return users

@api.patch("/users/{user_id}/role")
async def update_role(user_id: str, upd: UserRoleUpdate,
                      _: dict = Depends(require_role("commander"))):
    result = await db.users.update_one({"id": user_id}, {"$set": {"role": upd.role}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Utilizator inexistent")
    return {"ok": True}

@api.delete("/users/{user_id}")
async def delete_user(user_id: str, actor: dict = Depends(require_role("commander"))):
    if user_id == actor["id"]:
        raise HTTPException(status_code=400, detail="Nu te poți șterge singur")
    result = await db.users.delete_one({"id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Utilizator inexistent")
    return {"ok": True}


# ────────────────────────────────────────────────────────────────
# Missions API (commander create/edit; pilot execute; observer read)
# ────────────────────────────────────────────────────────────────
@api.get("/missions")
async def list_missions(user: dict = Depends(get_current_user)):
    missions = await db.missions.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return missions

@api.post("/missions")
async def create_mission(data: MissionIn,
                         user: dict = Depends(require_role("commander", "pilot"))):
    now = datetime.now(timezone.utc).isoformat()
    m = {
        "id": str(uuid.uuid4()),
        "name": data.name,
        "mission_type": data.mission_type,
        "drone_ids": data.drone_ids,
        "waypoints": data.waypoints,
        "priority": data.priority,
        "notes": data.notes,
        "status": "planned",
        "created_by": user["id"],
        "created_at": now,
        "updated_at": now,
    }
    await db.missions.insert_one(m)
    return m

@api.patch("/missions/{mission_id}")
async def update_mission(mission_id: str, patch: dict,
                         user: dict = Depends(require_role("commander", "pilot"))):
    patch = {k: v for k, v in patch.items() if k in {"status", "waypoints", "notes", "priority", "drone_ids", "name"}}
    patch["updated_at"] = datetime.now(timezone.utc).isoformat()
    r = await db.missions.update_one({"id": mission_id}, {"$set": patch})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Misiune inexistentă")
    return {"ok": True}

@api.delete("/missions/{mission_id}")
async def delete_mission(mission_id: str, _: dict = Depends(require_role("commander"))):
    r = await db.missions.delete_one({"id": mission_id})
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Misiune inexistentă")
    return {"ok": True}


# ────────────────────────────────────────────────────────────────
# Telemetry (write: pilot/commander; read: all)
# ────────────────────────────────────────────────────────────────
@api.post("/telemetry")
async def push_telemetry(t: TelemetryIn,
                          user: dict = Depends(require_role("commander", "pilot"))):
    doc = t.model_dump()
    doc["ts"] = datetime.now(timezone.utc).isoformat()
    doc["pilot_id"] = user["id"]
    await db.telemetry.insert_one(doc)
    return {"ok": True}

@api.get("/telemetry/{drone_id}")
async def get_telemetry(drone_id: str, limit: int = 100,
                        _: dict = Depends(get_current_user)):
    docs = await db.telemetry.find({"drone_id": drone_id}, {"_id": 0}).sort("ts", -1).limit(limit).to_list(limit)
    return docs

@api.post("/sos")
async def push_sos(s: SOSIn, user: dict = Depends(get_current_user)):
    doc = s.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["ts"] = datetime.now(timezone.utc).isoformat()
    doc["reported_by"] = user["id"]
    doc["ack"] = False
    await db.sos_events.insert_one(doc)
    log.warning(f"🆘 SOS RECEIVED — drone={s.drone_id} at {s.lat},{s.lng} — {s.reason}")
    return {"ok": True, "id": doc["id"]}

@api.get("/sos")
async def list_sos(limit: int = 50, _: dict = Depends(get_current_user)):
    docs = await db.sos_events.find({}, {"_id": 0}).sort("ts", -1).limit(limit).to_list(limit)
    return docs

@api.patch("/sos/{sos_id}/ack")
async def ack_sos(sos_id: str, _: dict = Depends(require_role("commander", "pilot"))):
    r = await db.sos_events.update_one({"id": sos_id}, {"$set": {"ack": True, "ack_at": datetime.now(timezone.utc).isoformat()}})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="SOS inexistent")
    return {"ok": True}


# ────────────────────────────────────────────────────────────────
# Drone integration status — placeholder for DJI SDK / MAVLink adapter
# ────────────────────────────────────────────────────────────────
@api.get("/drone-adapters")
async def drone_adapters(_: dict = Depends(get_current_user)):
    """Reports which real-drone adapters are enabled/configured on the server.
    In production these plug into DJI Mobile SDK, MAVLink/ArduPilot, Autel EVO, Parrot Anafi.
    For demo they are 'ready' but running in sim mode."""
    return {
        "adapters": [
            {"id": "dji", "name": "DJI Mobile SDK", "status": "ready", "mode": "simulation",
             "supported_models": ["Mavic 3", "M30T", "Matrice 350 RTK"]},
            {"id": "mavlink", "name": "MAVLink / ArduPilot", "status": "ready", "mode": "simulation",
             "supported_models": ["Custom copters", "Pixhawk-based airframes"]},
            {"id": "autel", "name": "Autel Robotics EVO", "status": "planned", "mode": "n/a",
             "supported_models": ["EVO II Dual", "EVO Max 4T"]},
            {"id": "parrot", "name": "Parrot ANAFI", "status": "planned", "mode": "n/a",
             "supported_models": ["ANAFI USA", "ANAFI Ai"]},
        ],
        "note": "Toate adaptoarele rulează în modul SIM pentru demo. În producție se conectează la firmware real DroZon-MAXIM.",
    }


@api.get("/health")
async def health():
    return {"ok": True, "service": "drozon-api", "ts": datetime.now(timezone.utc).isoformat()}


# Include router + middleware
app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)
