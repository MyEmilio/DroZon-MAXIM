# 🚁 DroneZone Firmware v1.0
## Firmware C/C++ STM32H743 + Simulator Python

---

## ARHITECTURA FIRMWARE

```
┌─────────────────────────────────────────────────────┐
│              STM32H743 @ 480MHz                     │
│                                                     │
│  CORE 0 (Timp real critic)    CORE 1 (IO + Comm)   │
│  ┌──────────────────────┐    ┌──────────────────┐  │
│  │ task_failsafe  P:10  │    │ task_gps      P:6│  │
│  │ task_imu_read  P:9   │    │ task_baro     P:6│  │
│  │ task_pid       P:9   │    │ task_telemetry P:6│  │
│  │ task_motor     P:9   │    │ task_enviro   P:4│  │
│  └──────────────────────┘    │ task_relay    P:5│  │
│                              └──────────────────┘  │
│                                                     │
│  COZI: IMU→PID→MOTOR  GPS/BARO→TELEM  FS_EVENTS   │
│  MUTEX: state(global) uart(serial)                  │
│  TIMERE: WDG_GCS(3s) WDG_TELEM(2s) RELAY(15s)     │
└─────────────────────────────────────────────────────┘
         │ MAVLink 2.0 UART            │ DSHOT600 DMA
         ▼                             ▼
    ┌─────────┐                  ┌──────────┐
    │ GCS /   │                  │ 8× ESC   │
    │Companion│                  │ BLHeli32 │
    │Computer │                  └──────────┘
    └────┬────┘
         │ HTTP POST /api/telemetry
         ▼
    ┌─────────────┐
    │  DroneZone  │
    │  Next.js +  │
    │  Supabase   │
    └─────────────┘
```

---

## TASK-URI FREERTOS — PRIORITĂTI ȘI FRECVENȚE

| Task | Core | Prioritate | Frecvență | Funcție |
|---|---|---|---|---|
| `task_failsafe` | 0 | **10 (MAX)** | Event-driven | Watchdog, avarii, RTH |
| `task_imu_read` | 0 | 9 | **400Hz** | ICM-42688 accelero+gyro |
| `task_pid_control` | 0 | 9 | **400Hz** | PID cascadat + mixer X8 |
| `task_motor_write` | 0 | 9 | **400Hz** | DSHOT600 DMA → ESC |
| `task_gps_read` | 1 | 6 | 10Hz | u-blox F9P UBX |
| `task_baro_read` | 1 | 6 | 50Hz | MS5611 altitudine |
| `task_telemetry` | 1 | 6 | 10Hz | MAVLink 2.0 UART |
| `task_relay` | 1 | 5 | Event-driven | Handoff protocol |
| `task_enviro_read` | 1 | 4 | 1Hz | Baterie, temp, lichid |

---

## INSTALARE TOOLCHAIN

### macOS
```bash
brew install arm-none-eabi-gcc cmake openocd
```

### Ubuntu/Debian
```bash
sudo apt install gcc-arm-none-eabi cmake openocd
```

### Windows
Descarcă ARM GCC de la: https://developer.arm.com/tools-and-software/open-source-software/developer-tools/gnu-toolchain

---

## LIBRĂRII NECESARE (clone în /libs)

```bash
mkdir libs && cd libs

# STM32 HAL Driver
git clone https://github.com/STMicroelectronics/stm32h7xx_hal_driver.git STM32H7xx_HAL_Driver

# CMSIS
git clone https://github.com/ARM-software/CMSIS_5.git CMSIS

# FreeRTOS
git clone https://github.com/FreeRTOS/FreeRTOS-Kernel.git FreeRTOS

# MAVLink (headers only)
git clone https://github.com/mavlink/c_library_v2.git mavlink
```

---

## BUILD FIRMWARE

```bash
mkdir build && cd build
cmake .. -DCMAKE_TOOLCHAIN_FILE=../cmake/arm-toolchain.cmake
make -j8

# Output:
#   build/dronezone.bin  ← pentru flashare
#   build/dronezone.elf  ← pentru debug GDB
```

---

## FLASHARE PE PLACĂ

```bash
# Cu ST-Link (Pixhawk 6X are ST-Link integrat)
make flash

# SAU cu DFU (USB bootloader)
dfu-util -a 0 -D build/dronezone.bin -s 0x08000000:leave

# SAU QGroundControl → Firmware → Custom firmware → dronezone.bin
```

---

## SIMULATOR PYTHON

### Instalare
```bash
cd simulator
pip install asyncio aiohttp websockets python-dotenv
```

### Pornire simulator (o singură dronă)
```bash
# Copiază .env.local din proiectul Next.js
cp ../terenuri_app/.env.local .env

python simulator.py \
  --drone "uuid-din-supabase" \
  --name "DRN-001 TEST" \
  --batt 80 \
  --lat 44.4268 \
  --lon 26.1025
```

### Multi-dronă (3 simultane)
```bash
python simulator.py --multi
```

### Output simulator
```
10:23:15 [INFO] 🚀 Simulator pornit → http://localhost:3000/api/telemetry
10:23:15 [INFO]    Drone: DRN-001-SIM | Baterie inițială: 100%
10:23:20 [INFO]   ✅ ARMED — Misiune AUTO pornită
10:23:25 [INFO]   🚁 AUTO       | Alt: 45.2m | Batt:99.8% | GPS:44.4271,26.1028 | WP:0/5
10:23:30 [INFO]   🚁 AUTO       | Alt: 89.7m | Batt:99.5% | GPS:44.4285,26.1035 | WP:1/5
10:23:35 [INFO]   ✓ Waypoint 1/5 atins
...
10:28:00 [WARNING]  ⚠ FAILSAFE: Baterie scăzută 29.8% → RTH
10:28:45 [INFO]   ✅ Aterizare completă — DISARMED
10:28:45 [INFO] ✅ Misiune completă!
10:28:45 [INFO]    Durată: 325s
10:28:45 [INFO]    Distanță: 3.42km
```

---

## INTEGRAREA CU DRONEZONE NEXT.JS

Firmware-ul trimite date la **`/api/telemetry`** prin HTTP POST (MAVLink prin companion computer Raspberry Pi):

```
Dronă (STM32) → UART MAVLink → Raspberry Pi → HTTP POST → DroneZone API → Supabase
```

Pe Raspberry Pi rulează un script bridge simplu:
```python
# bridge.py (pe Raspberry Pi montat pe dronă)
from pymavlink import mavutil
import requests, time

conn = mavutil.mavlink_connection('/dev/ttyS0', baud=57600)
while True:
    msg = conn.recv_match(blocking=True, timeout=0.1)
    if msg:
        # Convertește MAVLink → JSON → POST la DroneZone
        requests.post('https://dronezone.vercel.app/api/telemetry', json={...})
```

---

## FAILSAFE — LOGICA COMPLETĂ

```
Baterie < 30%    → RTH automat (dacă home setat)
Baterie < 15%    → LAND imediat
GCS lipsă > 3s   → RTH (dacă owner) / alertă (dacă relay)
Relay timeout    → RTH
IMU eroare       → DISARM imediat (nu putem zbura fără IMU)
GPS pierdut      → Trece la ALT_HOLD (pilot manual)
Motor fault × 1  → RTH
Motor fault × 2  → LAND imediat
Supraîncălzire   → RTH
Geofence breach  → RTH imediat
```

---

## RELAY HANDOFF — PROTOCOL PE DRONĂ

```
OWNER GCS                DRONE FCU               RELAY GCS
   │                         │                       │
   │── RELAY_CMD_REQUEST ──▶│                       │
   │                         │── Token generat ──▶  │
   │                         │    (15s timeout)      │
   │                         │◀─ RELAY_CMD_ACCEPT ──│
   │                         │   + token valid       │
   │                         │── Ctrl transfer ────▶│
   │                         │── MAVLink confirm ──▶│
   │◀─────── Confirmare ────│                       │
   │  (CTRL_OWNER → CTRL_RELAY)                     │
```

---

*DroneZone Firmware Guide — Rev 1.0 — 2026*
*Target: STM32H743VIT6 (Pixhawk 6X compatible)*
