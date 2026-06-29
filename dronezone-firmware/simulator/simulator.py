#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════
DRONEZONE FIRMWARE SIMULATOR v1.0
Simulează firmware-ul dronei pe PC și trimite date reale la
backend-ul DroneZone (Supabase WebSocket + API REST)

INSTALARE:
    pip install asyncio aiohttp websockets python-dotenv pymavlink
    pip install numpy scipy

UTILIZARE:
    python simulator.py --drone DRN-001 --mode auto
    python simulator.py --drone DRN-002 --mode manual --batt 45
    python simulator.py --help
═══════════════════════════════════════════════════════════════════
"""

import asyncio
import aiohttp
import json
import math
import time
import random
import argparse
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional
from datetime import datetime, timezone
from enum import IntEnum, auto
import os

# ── Logging ──────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger('DroneZone-SIM')

# ── Configurare (din .env.local sau variabile mediu) ──────────────
SUPABASE_URL    = os.getenv('NEXT_PUBLIC_SUPABASE_URL', 'https://xxxx.supabase.co')
SUPABASE_KEY    = os.getenv('NEXT_PUBLIC_SUPABASE_ANON_KEY', 'your_anon_key')
DRONE_API_URL   = os.getenv('DRONE_API_URL', 'http://localhost:3000/api/telemetry')
DRONE_SECRET    = os.getenv('DRONE_SECRET_KEY', 'dronezone_secret_2026')
MAVLINK_HOST    = os.getenv('MAVLINK_HOST', '127.0.0.1')
MAVLINK_PORT    = int(os.getenv('MAVLINK_PORT', '14550'))


# ════════════════════════════════════════════════════════════════
# ENUMS
# ════════════════════════════════════════════════════════════════
class FlightMode(IntEnum):
    DISARMED   = 0
    STABILIZE  = 1
    ALT_HOLD   = 2
    POS_HOLD   = 3
    AUTO       = 4
    RTH        = 5
    LAND       = 6
    FAILSAFE   = 7

class FailsafeType(IntEnum):
    BATTERY_LOW      = 1
    BATTERY_CRITICAL = 2
    GCS_LINK_LOST    = 3
    MOTOR_FAULT      = 7
    GPS_LOST         = 6


# ════════════════════════════════════════════════════════════════
# STRUCTURI DATE
# ════════════════════════════════════════════════════════════════
@dataclass
class IMUData:
    accel_x: float = 0.0  # m/s²
    accel_y: float = 0.0
    accel_z: float = -9.81
    gyro_x:  float = 0.0  # rad/s
    gyro_y:  float = 0.0
    gyro_z:  float = 0.0
    temp_c:  float = 25.0

@dataclass
class GPSData:
    lat:         float = 44.4268
    lon:         float = 26.1025
    alt_msl:     float = 87.0
    alt_rel:     float = 87.0
    speed_ms:    float = 0.0
    vspeed_ms:   float = 0.0
    heading:     float = 0.0
    fix_type:    int   = 4    # RTK
    satellites:  int   = 18
    hdop:        float = 0.8

@dataclass
class MotorState:
    rpm:   list = field(default_factory=lambda: [4800]*8)
    amp:   list = field(default_factory=lambda: [8.2]*8)
    temp:  list = field(default_factory=lambda: [42.0]*8)
    fault: list = field(default_factory=lambda: [False]*8)

@dataclass
class DroneState:
    # Identitate
    drone_id:     str   = "drone-uuid-here"
    drone_name:   str   = "DRN-001"
    serial:       str   = "SN-001-2026"

    # Mod și control
    flight_mode:  FlightMode = FlightMode.DISARMED
    armed:        bool  = False
    controller:   str   = "owner"   # 'owner' | 'relay'

    # Atitudine estimat
    roll:         float = 0.0   # grade
    pitch:        float = 0.0
    yaw:          float = 0.0
    altitude:     float = 0.0
    vspeed:       float = 0.0

    # Baterie
    battery_pct:  float = 100.0
    battery_v:    float = 25.2
    battery_a:    float = 0.0
    mah:          float = 0.0

    # Senzori mediu
    temp_c:       float = 18.0
    humidity:     float = 65.0
    wind_ms:      float = 2.5
    liquid_pct:   float = 100.0

    # Navigație
    home_lat:     float = 44.4268
    home_lon:     float = 26.1025
    home_alt:     float = 0.0
    target_lat:   float = 44.4268
    target_lon:   float = 26.1025
    target_alt:   float = 100.0

    # Stats
    flight_sec:   int   = 0
    total_dist_km: float = 0.0
    max_altitude: float = 0.0
    signal_pct:   float = 98.0

    # Senzori
    imu:    IMUData   = field(default_factory=IMUData)
    gps:    GPSData   = field(default_factory=GPSData)
    motors: MotorState = field(default_factory=MotorState)


# ════════════════════════════════════════════════════════════════
# SIMULATOR PID (simplificat)
# ════════════════════════════════════════════════════════════════
class PIDController:
    def __init__(self, kp, ki, kd, i_max=1.0, out_min=-1.0, out_max=1.0):
        self.kp, self.ki, self.kd = kp, ki, kd
        self.i_max = i_max
        self.out_min, self.out_max = out_min, out_max
        self.integral = 0.0
        self.prev_error = 0.0

    def compute(self, setpoint, measured, dt):
        error = setpoint - measured
        self.integral = max(-self.i_max, min(self.i_max, self.integral + error * dt))
        derivative = (error - self.prev_error) / dt if dt > 0 else 0
        self.prev_error = error
        output = self.kp * error + self.ki * self.integral + self.kd * derivative
        return max(self.out_min, min(self.out_max, output))

    def reset(self):
        self.integral = 0.0
        self.prev_error = 0.0


# ════════════════════════════════════════════════════════════════
# SIMULATOR PRINCIPAL
# ════════════════════════════════════════════════════════════════
class DroneSimulator:
    def __init__(self, drone_id: str, initial_battery: float = 100.0,
                 mission_type: str = 'auto'):
        self.state = DroneState(
            drone_id=drone_id,
            battery_pct=initial_battery,
            battery_v=initial_battery * 0.252  # ~25.2V la 100%
        )
        self.mission_type = mission_type
        self.tick = 0
        self.dt   = 0.1  # 10Hz simulare

        # PID controllers
        self.pid_alt  = PIDController(kp=0.8, ki=0.15, kd=0.2, i_max=0.5, out_min=-2.0, out_max=2.0)
        self.pid_roll = PIDController(kp=6.5, ki=0.0, kd=0.0, out_min=-30.0, out_max=30.0)
        self.pid_pitch= PIDController(kp=6.5, ki=0.0, kd=0.0, out_min=-30.0, out_max=30.0)

        # Waypoints misiune demo
        self.waypoints = [
            (44.4300, 26.1050, 100.0),
            (44.4350, 26.1100, 110.0),
            (44.4400, 26.1080, 100.0),
            (44.4380, 26.1020, 90.0),
            (44.4268, 26.1025, 50.0),  # HOME
        ]
        self.wp_index = 0

        # HTTP session
        self.session: Optional[aiohttp.ClientSession] = None
        self.running = True

        log.info(f"🚁 Simulator inițializat: {drone_id} | Baterie: {initial_battery:.0f}%")

    # ── Simulare IMU ─────────────────────────────────────────────
    def _sim_imu(self):
        s = self.state
        noise = 0.01
        # Accelerometru — gravitație + zgomot
        s.imu.accel_x = -s.pitch * 0.017 * 9.81 + random.gauss(0, noise)
        s.imu.accel_y =  s.roll  * 0.017 * 9.81 + random.gauss(0, noise)
        s.imu.accel_z = -9.81 + random.gauss(0, noise * 2)
        # Giroscop — rate + zgomot
        s.imu.gyro_x = random.gauss(0, 0.005)
        s.imu.gyro_y = random.gauss(0, 0.005)
        s.imu.gyro_z = random.gauss(0, 0.002)
        s.imu.temp_c = 25.0 + self.tick * 0.001

    # ── Simulare GPS ─────────────────────────────────────────────
    def _sim_gps(self):
        s = self.state
        if s.armed:
            # Mișcare spre waypoint
            if self.wp_index < len(self.waypoints):
                wp = self.waypoints[self.wp_index]
                dlat = wp[0] - s.gps.lat
                dlon = wp[1] - s.gps.lon
                dist = math.sqrt(dlat**2 + dlon**2) * 111000  # m
                if dist < 5.0:  # Am ajuns la waypoint
                    self.wp_index = min(self.wp_index + 1, len(self.waypoints) - 1)
                    log.info(f"  ✓ Waypoint {self.wp_index}/{len(self.waypoints)} atins")
                else:
                    speed_deg = 0.0001  # ~11m pe tick
                    s.gps.lat += (dlat / dist * speed_deg) if dist > 0 else 0
                    s.gps.lon += (dlon / dist * speed_deg) if dist > 0 else 0
                    s.gps.heading = math.degrees(math.atan2(dlon, dlat)) % 360
                    s.gps.speed_ms = random.uniform(10, 15)
                    s.total_dist_km += speed_deg * 111 * 1000 / 1000

        # Zgomot GPS mic
        s.gps.lat += random.gauss(0, 0.000001)
        s.gps.lon += random.gauss(0, 0.000001)
        s.gps.alt_msl = s.altitude + 87.0
        s.gps.alt_rel = s.altitude
        s.gps.vspeed_ms = s.vspeed

    # ── Simulare motoare ─────────────────────────────────────────
    def _sim_motors(self):
        s = self.state
        if s.armed:
            base_rpm = 4800 + (s.battery_pct / 100.0) * 400
            base_amp = 8.0 + (1.0 - s.battery_pct / 100.0) * 2.0
            for i in range(8):
                s.motors.rpm[i]  = base_rpm + random.gauss(0, 50)
                s.motors.amp[i]  = base_amp + random.gauss(0, 0.2)
                s.motors.temp[i] += 0.01 + random.gauss(0, 0.05)
                s.motors.temp[i]  = min(85.0, max(30.0, s.motors.temp[i]))
                # Fault aleatoriu după mult timp (test)
                if self.tick > 6000 and i == 2 and random.random() < 0.001:
                    s.motors.fault[i] = True
                    log.warning(f"  ⚠ AVARIE motor M{i+1}!")
        else:
            s.motors.rpm  = [0] * 8
            s.motors.amp  = [0.0] * 8

    # ── Simulare fizică dronă (PID simplificat) ──────────────────
    def _sim_physics(self):
        s = self.state
        if not s.armed:
            return

        # Altitudine cu PID
        target_alt = s.target_alt if s.flight_mode == FlightMode.AUTO else 100.0
        alt_correction = self.pid_alt.compute(target_alt, s.altitude, self.dt)
        s.vspeed   = max(-3.0, min(3.0, alt_correction))
        s.altitude = max(0.0, s.altitude + s.vspeed * self.dt)

        if s.altitude > s.max_altitude:
            s.max_altitude = s.altitude

        # Roll/Pitch oscilații mici (stabilizare)
        s.roll  = s.roll  * 0.95 + random.gauss(0, 0.3)
        s.pitch = s.pitch * 0.95 + random.gauss(0, 0.3)
        s.roll  = max(-30.0, min(30.0, s.roll))
        s.pitch = max(-30.0, min(30.0, s.pitch))

    # ── Simulare baterie ─────────────────────────────────────────
    def _sim_battery(self):
        s = self.state
        if s.armed:
            # Consum: ~1% la fiecare 25s de zbor la putere medie
            drain = 0.04 / self.dt  # 0.04% per secundă reală
            s.battery_pct = max(0.0, s.battery_pct - drain * self.dt * 0.1)
            s.battery_v   = 19.2 + (s.battery_pct / 100.0) * 5.8  # 19.2V-25.2V
            s.battery_a   = sum(s.motors.amp) + 1.5  # motoare + avionică
            s.mah        += s.battery_a * 1000 / 3600 * self.dt

    # ── Simulare senzori mediu ────────────────────────────────────
    def _sim_enviro(self):
        s = self.state
        s.temp_c    = 18.0 + math.sin(self.tick * 0.001) * 3 + random.gauss(0, 0.1)
        s.humidity  = 65.0 + random.gauss(0, 0.5)
        s.wind_ms   = 2.5  + random.gauss(0, 0.3)
        s.signal_pct= max(40.0, min(100.0, s.signal_pct + random.gauss(0, 0.5)))
        if s.armed:
            s.liquid_pct = max(0.0, s.liquid_pct - 0.001)

    # ── Logica failsafe ──────────────────────────────────────────
    def _check_failsafe(self):
        s = self.state
        if not s.armed: return

        if s.battery_pct < 15.0:
            log.critical(f"  🚨 FAILSAFE: Baterie critică {s.battery_pct:.1f}% → LAND")
            s.flight_mode = FlightMode.LAND
        elif s.battery_pct < 30.0 and s.flight_mode != FlightMode.RTH:
            log.warning(f"  ⚠ FAILSAFE: Baterie scăzută {s.battery_pct:.1f}% → RTH")
            s.flight_mode = FlightMode.RTH
            s.target_lat = s.home_lat
            s.target_lon = s.home_lon
            s.target_alt = s.home_alt + 20.0

        if s.flight_mode == FlightMode.LAND and s.altitude < 0.5:
            s.armed = False
            s.flight_mode = FlightMode.DISARMED
            log.info("  ✅ Aterizare completă — DISARMED")

    # ── ARM / DISARM ──────────────────────────────────────────────
    def arm(self):
        self.state.armed = True
        self.state.flight_mode = FlightMode.AUTO
        self.state.target_alt = 100.0
        log.info("  ✅ ARMED — Misiune AUTO pornită")

    # ── Tick principal ────────────────────────────────────────────
    def tick_update(self):
        self.tick += 1
        if self.state.armed:
            self.state.flight_sec += 1

        self._sim_imu()
        self._sim_motors()
        self._sim_physics()
        self._sim_battery()
        self._sim_gps()
        self._sim_enviro()
        self._check_failsafe()

        # ARM automat după 5 secunde
        if self.tick == 50 and not self.state.armed:
            self.arm()

    # ── Construiește pachetul de telemetrie ───────────────────────
    def build_telemetry_packet(self) -> dict:
        s = self.state
        return {
            "drone_id":    s.drone_id,
            "battery_pct": round(s.battery_pct, 2),
            "voltage":     round(s.battery_v, 2),
            "current_a":   round(s.battery_a, 2),
            "lat":         round(s.gps.lat, 7),
            "lon":         round(s.gps.lon, 7),
            "altitude_m":  round(s.altitude, 2),
            "speed_ms":    round(s.gps.speed_ms, 2),
            "heading_deg": round(s.gps.heading, 1),
            "signal_pct":  round(s.signal_pct, 1),
            "temp_c":      round(s.temp_c, 1),
            "humidity":    round(s.humidity, 1),
            "wind_ms":     round(s.wind_ms, 1),
            "gps_sats":    s.gps.satellites,
            "liquid_pct":  round(s.liquid_pct, 1),
            "motor_rpm":   {f"m{i+1}": round(s.motors.rpm[i]) for i in range(8)},
            "motor_amp":   {f"m{i+1}": round(s.motors.amp[i], 1) for i in range(8)},
            "motor_temp":  {f"m{i+1}": round(s.motors.temp[i], 1) for i in range(8)},
        }

    # ── Trimite telemetrie la DroneZone API ───────────────────────
    async def send_telemetry(self):
        packet = self.build_telemetry_packet()
        try:
            async with self.session.post(
                DRONE_API_URL,
                json=packet,
                headers={
                    "Authorization": f"Bearer {DRONE_SECRET}",
                    "Content-Type":  "application/json",
                    "X-Drone-ID":    self.state.drone_id,
                },
                timeout=aiohttp.ClientTimeout(total=3)
            ) as resp:
                if resp.status == 200:
                    log.debug(f"  📡 Telemetrie trimisă OK | Batt:{packet['battery_pct']:.1f}%"
                              f" Alt:{packet['altitude_m']:.1f}m GPS:{packet['lat']:.4f},{packet['lon']:.4f}")
                else:
                    log.warning(f"  ⚠ API error: {resp.status}")
        except aiohttp.ClientConnectorError:
            log.debug("  (Server offline — se continuă simularea)")
        except asyncio.TimeoutError:
            log.warning("  ⚠ Timeout trimitere telemetrie")

    # ── Loop principal async ──────────────────────────────────────
    async def run(self):
        async with aiohttp.ClientSession() as session:
            self.session = session
            log.info(f"🚀 Simulator pornit → {DRONE_API_URL}")
            log.info(f"   Drone: {self.state.drone_name} | "
                     f"Baterie inițială: {self.state.battery_pct:.0f}%")
            log.info("   Ctrl+C pentru oprire\n")

            telem_counter = 0
            while self.running:
                start = time.perf_counter()

                # Update simulare (10Hz intern)
                self.tick_update()
                telem_counter += 1

                # Trimite telemetrie la 2Hz (la fiecare 5 tick-uri)
                if telem_counter % 5 == 0:
                    await self.send_telemetry()

                # Status în consolă la fiecare 10 secunde
                if self.state.flight_sec % 10 == 0 and self.state.armed:
                    s = self.state
                    log.info(
                        f"  🚁 {FlightMode(s.flight_mode).name:10s} | "
                        f"Alt:{s.altitude:5.1f}m | "
                        f"Batt:{s.battery_pct:4.1f}% | "
                        f"GPS:{s.gps.lat:.4f},{s.gps.lon:.4f} | "
                        f"WP:{self.wp_index}/{len(self.waypoints)}"
                    )

                # Verifică aterizare completă
                if (self.state.flight_mode == FlightMode.DISARMED
                        and self.state.flight_sec > 10):
                    log.info("\n✅ Misiune completă!")
                    log.info(f"   Durată: {self.state.flight_sec}s")
                    log.info(f"   Distanță: {self.state.total_dist_km:.2f}km")
                    log.info(f"   Baterie rămasă: {self.state.battery_pct:.1f}%")
                    log.info(f"   Altitudine max: {self.state.max_altitude:.1f}m")
                    log.info(f"   mAh consumat: {self.state.mah:.0f}mAh")
                    break

                # Menține rata de 10Hz
                elapsed = time.perf_counter() - start
                sleep_time = max(0.0, self.dt - elapsed)
                await asyncio.sleep(sleep_time)


# ════════════════════════════════════════════════════════════════
# MULTI-DRONE SIMULATOR
# ════════════════════════════════════════════════════════════════
class MultiDroneSimulator:
    """Rulează mai multe drone simultan"""
    def __init__(self, drones_config: list[dict]):
        self.drones = [
            DroneSimulator(
                drone_id=cfg['id'],
                initial_battery=cfg.get('battery', 100.0),
                mission_type=cfg.get('mission', 'auto')
            )
            for cfg in drones_config
        ]
        for drone, cfg in zip(self.drones, drones_config):
            drone.state.drone_name = cfg.get('name', drone.state.drone_name)
            drone.state.gps.lat   = cfg.get('lat', 44.4268)
            drone.state.gps.lon   = cfg.get('lon', 26.1025)

    async def run_all(self):
        tasks = [drone.run() for drone in self.drones]
        await asyncio.gather(*tasks, return_exceptions=True)


# ════════════════════════════════════════════════════════════════
# ENTRY POINT
# ════════════════════════════════════════════════════════════════
async def main():
    parser = argparse.ArgumentParser(description='DroneZone Firmware Simulator')
    parser.add_argument('--drone',    default='drone-sim-001', help='Drone ID (UUID din Supabase)')
    parser.add_argument('--name',     default='DRN-001-SIM',   help='Drone name')
    parser.add_argument('--batt',     type=float, default=100.0, help='Baterie inițială (%)')
    parser.add_argument('--lat',      type=float, default=44.4268, help='Latitudine start')
    parser.add_argument('--lon',      type=float, default=26.1025, help='Longitudine start')
    parser.add_argument('--mode',     default='auto', choices=['auto','manual'], help='Mod misiune')
    parser.add_argument('--multi',    action='store_true', help='Rulează 3 drone simultan')
    parser.add_argument('--api',      default=None, help='URL API override')
    args = parser.parse_args()

    if args.api:
        global DRONE_API_URL
        DRONE_API_URL = args.api

    if args.multi:
        # Demo cu 3 drone simultane
        sim = MultiDroneSimulator([
            {'id': 'drone-sim-001', 'name': 'DRN-001 AGRO',  'battery': 100, 'lat': 44.4268, 'lon': 26.1025},
            {'id': 'drone-sim-002', 'name': 'DRN-002 INSP',  'battery': 75,  'lat': 44.4300, 'lon': 26.1100},
            {'id': 'drone-sim-003', 'name': 'DRN-003 SURV',  'battery': 50,  'lat': 44.4200, 'lon': 26.0950},
        ])
        await sim.run_all()
    else:
        sim = DroneSimulator(
            drone_id=args.drone,
            initial_battery=args.batt,
            mission_type=args.mode
        )
        sim.state.drone_name = args.name
        sim.state.gps.lat    = args.lat
        sim.state.gps.lon    = args.lon
        await sim.run()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("\n👋 Simulator oprit de utilizator")
