"""
DroZon Backend — FastAPI + MongoDB
- Persistență flotă drone + telemetrie + misiuni
- JWT Auth (admin / operator / viewer)
- WebSocket telemetrie live
- MAVLink telemetry ingest endpoint (stub)
"""
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Response, WebSocket, WebSocketDisconnect
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import uuid
import bcrypt
import jwt
import secrets
import asyncio
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import List, Optional, Dict, Any, Set
from contextlib import asynccontextmanager

# ═══════════════════════════════════════════════════════════
# DB + CONSTANTS
# ═══════════════════════════════════════════════════════════
ROOT_DIR = Path(__file__).parent
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_MIN = 60 * 8   # 8h
REFRESH_TOKEN_DAYS = 30

def get_jwt_secret() -> str:
    return os.environ["JWT_SECRET"]


# ═══════════════════════════════════════════════════════════
# LIFESPAN — startup: seed admin + indexes; connections mgmt
# ═══════════════════════════════════════════════════════════
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Indexes
    await db.users.create_index("email", unique=True)
    await db.login_attempts.create_index("identifier")
    # Seed admin
    await seed_admin()
    yield
    client.close()


app = FastAPI(title="DroZon API", version="2.0", lifespan=lifespan)
api_router = APIRouter(prefix="/api")
auth_router = APIRouter(prefix="/api/auth")


# ═══════════════════════════════════════════════════════════
# AUTH HELPERS
# ═══════════════════════════════════════════════════════════
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
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_MIN),
        "type": "access"
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_DAYS),
        "type": "refresh"
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = await db.users.find_one({"id": payload["sub"]}, {"password_hash": 0, "_id": 0})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_current_user_optional(request: Request) -> Optional[dict]:
    try:
        return await get_current_user(request)
    except HTTPException:
        return None


def require_role(*roles):
    async def dep(user: dict = Depends(get_current_user)) -> dict:
        if user.get("role") not in roles:
            raise HTTPException(status_code=403, detail=f"Requires role: {', '.join(roles)}")
        return user
    return dep


async def seed_admin():
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@drozon.ro").lower()
    admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")
    existing = await db.users.find_one({"email": admin_email})
    if existing is None:
        await db.users.insert_one({
            "id": str(uuid.uuid4()),
            "email": admin_email,
            "password_hash": hash_password(admin_password),
            "name": "DroZon Admin",
            "role": "admin",
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        logging.info(f"[seed] Admin created: {admin_email}")
    elif not verify_password(admin_password, existing["password_hash"]):
        await db.users.update_one(
            {"email": admin_email},
            {"$set": {"password_hash": hash_password(admin_password)}}
        )
        logging.info(f"[seed] Admin password refreshed: {admin_email}")


def set_auth_cookies(response: Response, access_token: str, refresh_token: str):
    response.set_cookie("access_token", access_token, httponly=True, secure=True, samesite="none",
                        max_age=ACCESS_TOKEN_MIN * 60, path="/")
    response.set_cookie("refresh_token", refresh_token, httponly=True, secure=True, samesite="none",
                        max_age=REFRESH_TOKEN_DAYS * 86400, path="/")


def clear_auth_cookies(response: Response):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")


# ═══════════════════════════════════════════════════════════
# MODELS
# ═══════════════════════════════════════════════════════════
class UserPublic(BaseModel):
    id: str
    email: str
    name: str
    role: str
    created_at: str


class RegisterPayload(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: str = Field(min_length=1)
    role: str = Field(default="viewer")  # viewer | operator | admin


class LoginPayload(BaseModel):
    email: EmailStr
    password: str


class Drone(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    model: str = ""
    droneType: str = "generic"
    status: str = "standby"
    lat: float
    lng: float
    alt: float = 0
    battery: float = 100
    speed: float = 0
    signal: float = 100
    autonomy: float = 30
    range: float = 5
    activeMission: Optional[str] = None
    tankCap: float = 0
    tankLvl: float = 0
    liquidType: str = "none"
    motorTemp: float = 40
    createdAt: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updatedAt: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class DroneCreate(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str
    model: str = ""
    droneType: str = "generic"
    status: str = "standby"
    lat: float
    lng: float
    alt: float = 0
    battery: float = 100
    autonomy: float = 30
    range: float = 5


class Mission(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    droneId: str
    type: str
    title: str = ""
    startLat: float
    startLng: float
    destLat: float
    destLng: float
    startedAt: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    endedAt: Optional[str] = None
    status: str = "active"


class Alert(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    droneId: str
    severity: str
    type: str
    message: str
    data: Dict[str, Any] = {}
    acknowledged: bool = False
    createdAt: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class TelemetryPoint(BaseModel):
    droneId: str
    lat: float
    lng: float
    alt: float = 0
    battery: float = 100
    speed: float = 0
    heading: float = 0
    signal: float = 100
    ts: Optional[str] = None


# ═══════════════════════════════════════════════════════════
# WEBSOCKET MANAGER — Broadcast telemetrie live
# ═══════════════════════════════════════════════════════════
class ConnectionManager:
    def __init__(self):
        self.active: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.add(ws)

    def disconnect(self, ws: WebSocket):
        self.active.discard(ws)

    async def broadcast(self, msg: dict):
        dead = []
        payload = json.dumps(msg, default=str)
        for ws in list(self.active):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


# ═══════════════════════════════════════════════════════════
# AUTH ROUTES
# ═══════════════════════════════════════════════════════════
@auth_router.post("/register")
async def register(payload: RegisterPayload, response: Response, user: Optional[dict] = Depends(get_current_user_optional)):
    email = payload.email.lower()
    # Doar admin poate crea alți admini/operatori
    role = payload.role
    if role in ("admin", "operator") and (not user or user.get("role") != "admin"):
        raise HTTPException(status_code=403, detail="Only admin can create admin/operator accounts")
    if role not in ("viewer", "operator", "admin"):
        role = "viewer"
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    uid = str(uuid.uuid4())
    doc = {
        "id": uid, "email": email, "password_hash": hash_password(payload.password),
        "name": payload.name, "role": role,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.users.insert_one(doc)
    access = create_access_token(uid, email, role)
    refresh = create_refresh_token(uid)
    set_auth_cookies(response, access, refresh)
    return {"id": uid, "email": email, "name": payload.name, "role": role, "access_token": access}


@auth_router.post("/login")
async def login(payload: LoginPayload, request: Request, response: Response):
    email = payload.email.lower()
    ip = request.client.host if request.client else "unknown"
    identifier = f"{ip}:{email}"
    # brute force check
    lock = await db.login_attempts.find_one({"identifier": identifier})
    if lock and lock.get("count", 0) >= 5:
        locked_until = lock.get("locked_until")
        if locked_until and datetime.fromisoformat(locked_until) > datetime.now(timezone.utc):
            raise HTTPException(status_code=429, detail="Too many failed attempts. Try again in 15 min.")
        # expired lock — reset
        await db.login_attempts.delete_one({"identifier": identifier})

    user = await db.users.find_one({"email": email})
    if not user or not verify_password(payload.password, user["password_hash"]):
        # increment attempts
        await db.login_attempts.update_one(
            {"identifier": identifier},
            {"$inc": {"count": 1},
             "$set": {"locked_until": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()}},
            upsert=True
        )
        raise HTTPException(status_code=401, detail="Invalid email or password")

    await db.login_attempts.delete_one({"identifier": identifier})
    access = create_access_token(user["id"], user["email"], user["role"])
    refresh = create_refresh_token(user["id"])
    set_auth_cookies(response, access, refresh)
    return {"id": user["id"], "email": user["email"], "name": user["name"], "role": user["role"], "access_token": access}


@auth_router.post("/logout")
async def logout(response: Response, _: dict = Depends(get_current_user)):
    clear_auth_cookies(response)
    return {"ok": True}


@auth_router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return user


@auth_router.post("/refresh")
async def refresh_token(request: Request, response: Response):
    tok = request.cookies.get("refresh_token")
    if not tok:
        raise HTTPException(status_code=401, detail="Missing refresh token")
    try:
        payload = jwt.decode(tok, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Wrong token type")
        user = await db.users.find_one({"id": payload["sub"]})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        access = create_access_token(user["id"], user["email"], user["role"])
        response.set_cookie("access_token", access, httponly=True, secure=True, samesite="none",
                            max_age=ACCESS_TOKEN_MIN * 60, path="/")
        return {"access_token": access}
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")


# ═══════════════════════════════════════════════════════════
# CORE ROUTES
# ═══════════════════════════════════════════════════════════
@api_router.get("/")
async def root():
    return {"message": "DroZon API v2", "status": "operational",
            "time": datetime.now(timezone.utc).isoformat(),
            "features": ["auth", "drones", "missions", "alerts", "telemetry", "websocket"]}


# ── Drones (public GET for viewer dashboard, auth POST/PUT/DELETE) ──
@api_router.get("/drones", response_model=List[Drone])
async def list_drones():
    return await db.drones.find({}, {"_id": 0}).to_list(1000)


@api_router.get("/drones/{drone_id}", response_model=Drone)
async def get_drone(drone_id: str):
    doc = await db.drones.find_one({"id": drone_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Drone not found")
    return doc


@api_router.post("/drones", response_model=Drone, status_code=201)
async def create_drone(payload: DroneCreate, user: dict = Depends(get_current_user_optional)):
    # public POST allowed pentru compatibilitate frontend anonymous;
    # dacă auth activ + user nu e operator/admin → 403
    if user and user.get("role") not in ("admin", "operator"):
        raise HTTPException(status_code=403, detail="Requires operator or admin role")
    drone = Drone(**payload.model_dump())
    await db.drones.insert_one(drone.model_dump())
    await manager.broadcast({"type": "drone_created", "drone": drone.model_dump()})
    return drone


@api_router.put("/drones/{drone_id}", response_model=Drone)
async def update_drone(drone_id: str, updates: Dict[str, Any], user: dict = Depends(get_current_user_optional)):
    if user and user.get("role") not in ("admin", "operator"):
        raise HTTPException(status_code=403, detail="Requires operator or admin role")
    updates["updatedAt"] = datetime.now(timezone.utc).isoformat()
    result = await db.drones.find_one_and_update(
        {"id": drone_id}, {"$set": updates}, return_document=True, projection={"_id": 0}
    )
    if not result:
        raise HTTPException(status_code=404, detail="Drone not found")
    await manager.broadcast({"type": "drone_updated", "drone": result})
    return result


@api_router.delete("/drones/{drone_id}")
async def delete_drone(drone_id: str, user: dict = Depends(get_current_user_optional)):
    if user and user.get("role") not in ("admin", "operator"):
        raise HTTPException(status_code=403, detail="Requires operator or admin role")
    result = await db.drones.delete_one({"id": drone_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Drone not found")
    await manager.broadcast({"type": "drone_deleted", "id": drone_id})
    return {"deleted": drone_id}


@api_router.post("/drones/bulk-seed")
async def bulk_seed_drones(drones: List[Dict[str, Any]]):
    existing = await db.drones.count_documents({})
    if existing > 0:
        return {"seeded": 0, "message": f"Already {existing} drones — skipping"}
    for d in drones:
        d.setdefault("id", str(uuid.uuid4()))
        d.setdefault("createdAt", datetime.now(timezone.utc).isoformat())
        d.setdefault("updatedAt", datetime.now(timezone.utc).isoformat())
    if drones:
        await db.drones.insert_many(drones)
    return {"seeded": len(drones)}


# ── Missions ──
@api_router.get("/missions", response_model=List[Mission])
async def list_missions(status: Optional[str] = None):
    q = {"status": status} if status else {}
    return await db.missions.find(q, {"_id": 0}).sort("startedAt", -1).to_list(500)


@api_router.post("/missions", response_model=Mission, status_code=201)
async def create_mission(payload: Mission, user: dict = Depends(get_current_user_optional)):
    if user and user.get("role") not in ("admin", "operator"):
        raise HTTPException(status_code=403, detail="Requires operator or admin role")
    doc = payload.model_dump()
    await db.missions.insert_one(doc)
    await manager.broadcast({"type": "mission_created", "mission": doc})
    return payload


@api_router.put("/missions/{mission_id}", response_model=Mission)
async def update_mission(mission_id: str, updates: Dict[str, Any], user: dict = Depends(get_current_user_optional)):
    if user and user.get("role") not in ("admin", "operator"):
        raise HTTPException(status_code=403, detail="Requires operator or admin role")
    result = await db.missions.find_one_and_update(
        {"id": mission_id}, {"$set": updates}, return_document=True, projection={"_id": 0}
    )
    if not result:
        raise HTTPException(status_code=404, detail="Mission not found")
    await manager.broadcast({"type": "mission_updated", "mission": result})
    return result


# ── Alerts ──
@api_router.get("/alerts", response_model=List[Alert])
async def list_alerts(acknowledged: Optional[bool] = None, limit: int = 100):
    q = {}
    if acknowledged is not None:
        q["acknowledged"] = acknowledged
    return await db.alerts.find(q, {"_id": 0}).sort("createdAt", -1).to_list(limit)


@api_router.post("/alerts", response_model=Alert, status_code=201)
async def create_alert(payload: Alert):
    doc = payload.model_dump()
    await db.alerts.insert_one(doc)
    await manager.broadcast({"type": "alert", "alert": doc})
    return payload


@api_router.post("/alerts/{alert_id}/ack")
async def ack_alert(alert_id: str, user: dict = Depends(get_current_user_optional)):
    result = await db.alerts.update_one({"id": alert_id}, {"$set": {"acknowledged": True}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"acknowledged": alert_id}


# ── Telemetry ingest (public, ready for MAVLink bridge) ──
@api_router.post("/telemetry/ingest")
async def telemetry_ingest(point: TelemetryPoint):
    """
    Endpoint pentru MAVLink bridge / drone hardware.
    Update poziția dronei + broadcast pe WebSocket.
    """
    updates = {
        "lat": point.lat, "lng": point.lng, "alt": point.alt,
        "battery": point.battery, "speed": point.speed,
        "signal": point.signal,
        "updatedAt": point.ts or datetime.now(timezone.utc).isoformat()
    }
    result = await db.drones.find_one_and_update(
        {"id": point.droneId}, {"$set": updates},
        return_document=True, projection={"_id": 0}
    )
    if not result:
        raise HTTPException(status_code=404, detail="Drone not found (register first)")
    await manager.broadcast({"type": "telemetry", "droneId": point.droneId, "data": updates, "drone": result})
    return {"ok": True, "drone": result}


@api_router.post("/telemetry/bulk-sync")
async def telemetry_bulk_sync(drones_state: List[Dict[str, Any]], user: dict = Depends(get_current_user_optional)):
    """
    Sync periodic al întregii flote (folosit de frontend pentru persistență).
    """
    updated = 0
    for d in drones_state:
        did = d.get("id")
        if not did:
            continue
        # doar câmpuri persistente
        allowed = {k: d.get(k) for k in ("lat", "lng", "alt", "battery", "speed", "signal", "status", "motorTemp", "tankLvl") if k in d}
        allowed["updatedAt"] = datetime.now(timezone.utc).isoformat()
        r = await db.drones.update_one({"id": did}, {"$set": allowed})
        if r.matched_count:
            updated += 1
    return {"updated": updated, "total": len(drones_state)}


# ── Stats ──
@api_router.get("/stats")
async def stats():
    total = await db.drones.count_documents({})
    return {
        "drones": {
            "total": total,
            "activ": await db.drones.count_documents({"status": "activ"}),
            "misiune": await db.drones.count_documents({"status": "misiune"}),
            "standby": await db.drones.count_documents({"status": "standby"}),
            "pericol": await db.drones.count_documents({"status": "pericol"}),
        },
        "missions_active": await db.missions.count_documents({"status": "active"}),
        "alerts_unacknowledged": await db.alerts.count_documents({"acknowledged": False}),
        "time": datetime.now(timezone.utc).isoformat(),
    }


# ═══════════════════════════════════════════════════════════
# WEBSOCKET — telemetrie live
# ═══════════════════════════════════════════════════════════
@app.websocket("/api/ws/telemetry")
async def ws_telemetry(ws: WebSocket):
    await manager.connect(ws)
    try:
        # Trimite snapshot inițial
        drones = await db.drones.find({}, {"_id": 0}).to_list(1000)
        await ws.send_text(json.dumps({"type": "snapshot", "drones": drones}, default=str))
        while True:
            # keep alive — client poate trimite ping/subscribe
            data = await ws.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await ws.send_text(json.dumps({"type": "pong", "ts": datetime.now(timezone.utc).isoformat()}))
            except Exception:
                pass
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception as e:
        logging.warning(f"WS error: {e}")
        manager.disconnect(ws)


# ═══════════════════════════════════════════════════════════
# WIRE UP
# ═══════════════════════════════════════════════════════════
app.include_router(auth_router)
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
