"""
DroZon Backend — FastAPI + MongoDB
Persistență flotă drone + telemetrie + misiuni.
"""
from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI(title="DroZon API", version="1.0")
api_router = APIRouter(prefix="/api")


# ═══════════════════════════════════════════════════════════
# MODELS
# ═══════════════════════════════════════════════════════════
class Drone(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    model: str = ""
    droneType: str = "generic"
    status: str = "standby"  # activ | misiune | standby | pericol
    lat: float
    lng: float
    alt: float = 0
    battery: float = 100
    speed: float = 0
    signal: float = 100
    autonomy: float = 30  # minutes
    range: float = 5  # km
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
    type: str  # incendiu | coletarie | salvare | survey | inspectie | patrulare
    title: str = ""
    startLat: float
    startLng: float
    destLat: float
    destLng: float
    startedAt: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    endedAt: Optional[str] = None
    status: str = "active"  # active | completed | aborted


class Alert(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    droneId: str
    severity: str  # info | warning | critical
    type: str  # battery_low | motor_fault | signal_lost | etc.
    message: str
    data: Dict[str, Any] = {}
    acknowledged: bool = False
    createdAt: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ═══════════════════════════════════════════════════════════
# ROUTES — Health
# ═══════════════════════════════════════════════════════════
@api_router.get("/")
async def root():
    return {"message": "DroZon API", "status": "operational", "time": datetime.now(timezone.utc).isoformat()}


# ═══════════════════════════════════════════════════════════
# ROUTES — Drones CRUD
# ═══════════════════════════════════════════════════════════
@api_router.get("/drones", response_model=List[Drone])
async def list_drones():
    docs = await db.drones.find({}, {"_id": 0}).to_list(1000)
    return docs


@api_router.get("/drones/{drone_id}", response_model=Drone)
async def get_drone(drone_id: str):
    doc = await db.drones.find_one({"id": drone_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Drone not found")
    return doc


@api_router.post("/drones", response_model=Drone)
async def create_drone(payload: DroneCreate):
    drone = Drone(**payload.model_dump())
    await db.drones.insert_one(drone.model_dump())
    return drone


@api_router.put("/drones/{drone_id}", response_model=Drone)
async def update_drone(drone_id: str, updates: Dict[str, Any]):
    updates["updatedAt"] = datetime.now(timezone.utc).isoformat()
    result = await db.drones.find_one_and_update(
        {"id": drone_id},
        {"$set": updates},
        return_document=True,
        projection={"_id": 0},
    )
    if not result:
        raise HTTPException(status_code=404, detail="Drone not found")
    return result


@api_router.delete("/drones/{drone_id}")
async def delete_drone(drone_id: str):
    result = await db.drones.delete_one({"id": drone_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Drone not found")
    return {"deleted": drone_id}


@api_router.post("/drones/bulk-seed")
async def bulk_seed_drones(drones: List[Dict[str, Any]]):
    """Import inițial flotă din frontend (când DB e goală)."""
    existing = await db.drones.count_documents({})
    if existing > 0:
        return {"seeded": 0, "message": f"Already {existing} drones in DB — skipping seed"}
    for d in drones:
        d.setdefault("id", str(uuid.uuid4()))
        d.setdefault("createdAt", datetime.now(timezone.utc).isoformat())
        d.setdefault("updatedAt", datetime.now(timezone.utc).isoformat())
    if drones:
        await db.drones.insert_many(drones)
    return {"seeded": len(drones)}


# ═══════════════════════════════════════════════════════════
# ROUTES — Missions
# ═══════════════════════════════════════════════════════════
@api_router.get("/missions", response_model=List[Mission])
async def list_missions(status: Optional[str] = None):
    query = {}
    if status:
        query["status"] = status
    docs = await db.missions.find(query, {"_id": 0}).sort("startedAt", -1).to_list(500)
    return docs


@api_router.post("/missions", response_model=Mission)
async def create_mission(payload: Mission):
    doc = payload.model_dump()
    await db.missions.insert_one(doc)
    return payload


@api_router.put("/missions/{mission_id}", response_model=Mission)
async def update_mission(mission_id: str, updates: Dict[str, Any]):
    result = await db.missions.find_one_and_update(
        {"id": mission_id}, {"$set": updates}, return_document=True, projection={"_id": 0}
    )
    if not result:
        raise HTTPException(status_code=404, detail="Mission not found")
    return result


# ═══════════════════════════════════════════════════════════
# ROUTES — Alerts
# ═══════════════════════════════════════════════════════════
@api_router.get("/alerts", response_model=List[Alert])
async def list_alerts(acknowledged: Optional[bool] = None, limit: int = 100):
    query = {}
    if acknowledged is not None:
        query["acknowledged"] = acknowledged
    docs = await db.alerts.find(query, {"_id": 0}).sort("createdAt", -1).to_list(limit)
    return docs


@api_router.post("/alerts", response_model=Alert)
async def create_alert(payload: Alert):
    doc = payload.model_dump()
    await db.alerts.insert_one(doc)
    return payload


@api_router.post("/alerts/{alert_id}/ack")
async def ack_alert(alert_id: str):
    result = await db.alerts.update_one({"id": alert_id}, {"$set": {"acknowledged": True}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"acknowledged": alert_id}


# ═══════════════════════════════════════════════════════════
# ROUTES — Stats (dashboard)
# ═══════════════════════════════════════════════════════════
@api_router.get("/stats")
async def stats():
    total = await db.drones.count_documents({})
    activ = await db.drones.count_documents({"status": "activ"})
    misiune = await db.drones.count_documents({"status": "misiune"})
    standby = await db.drones.count_documents({"status": "standby"})
    pericol = await db.drones.count_documents({"status": "pericol"})
    missions_active = await db.missions.count_documents({"status": "active"})
    alerts_unack = await db.alerts.count_documents({"acknowledged": False})
    return {
        "drones": {
            "total": total,
            "activ": activ,
            "misiune": misiune,
            "standby": standby,
            "pericol": pericol,
        },
        "missions_active": missions_active,
        "alerts_unacknowledged": alerts_unack,
        "time": datetime.now(timezone.utc).isoformat(),
    }


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
