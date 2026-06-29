// ═══════════════════════════════════════════════════════════════════
// DRONEZONE FIRMWARE v1.0
// Target: STM32H743 (Pixhawk 6X compatible)
// RTOS: FreeRTOS
// Toolchain: ARM GCC + CMake
//
// STRUCTURA PROIECT:
//   firmware/
//   ├── core/
//   │   ├── main.cpp          ← ACESTA — entry point + scheduler
//   │   ├── config.h          ← Configurare hardware pinout
//   │   └── system.h          ← Tipuri și constante globale
//   ├── sensors/
//   │   ├── imu.cpp/h         ← ICM-42688 accelerometru+giroscop
//   │   ├── gps.cpp/h         ← u-blox F9P GNSS
//   │   ├── baro.cpp/h        ← MS5611 barometru
//   │   └── enviro.cpp/h      ← SHT40 temp+umiditate, curent
//   ├── motors/
//   │   └── dshot.cpp/h       ← Protocol DSHOT600 pentru ESC
//   ├── pid/
//   │   └── controller.cpp/h  ← PID cascadat 3 axe
//   ├── telemetry/
//   │   └── mavlink.cpp/h     ← MAVLink 2.0 + WebSocket DroneZone
//   ├── failsafe/
//   │   └── failsafe.cpp/h    ← Watchdog + avarii + RTH
//   └── relay/
//       └── handoff.cpp/h     ← Protocol transfer control
// ═══════════════════════════════════════════════════════════════════

#include "FreeRTOS.h"
#include "task.h"
#include "queue.h"
#include "semphr.h"
#include "timers.h"

#include "core/config.h"
#include "core/system.h"
#include "sensors/imu.h"
#include "sensors/gps.h"
#include "sensors/baro.h"
#include "sensors/enviro.h"
#include "motors/dshot.h"
#include "pid/controller.h"
#include "telemetry/mavlink.h"
#include "failsafe/failsafe.h"
#include "relay/handoff.h"

// ── COZI INTER-TASK ──────────────────────────────────────────────
QueueHandle_t   q_imu_data;        // IMU → PID (400Hz)
QueueHandle_t   q_gps_data;        // GPS → Telemetrie (10Hz)
QueueHandle_t   q_baro_data;       // Baro → PID + Telem (50Hz)
QueueHandle_t   q_enviro_data;     // Senzori mediu → Telem (1Hz)
QueueHandle_t   q_motor_cmd;       // PID → DSHOT (400Hz)
QueueHandle_t   q_telem_out;       // Telem → UART/WiFi (10Hz)
QueueHandle_t   q_failsafe_event;  // Orice → Failsafe (imediat)
QueueHandle_t   q_relay_cmd;       // GCS → Relay handler

// ── MUTEX-URI ────────────────────────────────────────────────────
SemaphoreHandle_t mtx_state;       // Protejează DroneState global
SemaphoreHandle_t mtx_uart;        // Protejează UART telemetrie

// ── STARE GLOBALĂ DRONĂ ──────────────────────────────────────────
DroneState g_state;

// ── PROTOTIPURI TASK-URI ─────────────────────────────────────────
void task_imu_read    (void* pvParams);  // Core 1 — prio MAX  400Hz
void task_pid_control (void* pvParams);  // Core 1 — prio HIGH 400Hz
void task_motor_write (void* pvParams);  // Core 1 — prio HIGH 400Hz
void task_gps_read    (void* pvParams);  // Core 2 — prio MED  10Hz
void task_baro_read   (void* pvParams);  // Core 2 — prio MED  50Hz
void task_enviro_read (void* pvParams);  // Core 2 — prio LOW  1Hz
void task_telemetry   (void* pvParams);  // Core 2 — prio MED  10Hz
void task_failsafe    (void* pvParams);  // Core 1 — prio MAX  100Hz
void task_relay       (void* pvParams);  // Core 2 — prio MED  event-driven

// ── TIMER WATCHDOG ───────────────────────────────────────────────
TimerHandle_t wdg_telemetry;  // Resetează dacă telemetria tace >2s
TimerHandle_t wdg_gcs;        // Resetează dacă GCS tace >3s (pierdere link)

void cb_wdg_telemetry(TimerHandle_t xTimer) {
    FailsafeEvent ev = { .type = FS_TELEMETRY_TIMEOUT, .severity = SEV_WARNING };
    xQueueSend(q_failsafe_event, &ev, 0);
}

void cb_wdg_gcs(TimerHandle_t xTimer) {
    FailsafeEvent ev = { .type = FS_GCS_LINK_LOST, .severity = SEV_CRITICAL };
    xQueueSend(q_failsafe_event, &ev, 0);
}

// ════════════════════════════════════════════════════════════════
// MAIN — Entry point
// ════════════════════════════════════════════════════════════════
int main(void) {
    // ── Inițializare hardware ──
    HAL_Init();
    SystemClock_Config();     // 480MHz STM32H743
    HAL_Delay(100);           // Stabilizare tensiuni

    // ── LED boot indicator ──
    GPIO_SetPin(LED_BOOT, GPIO_PIN_SET);

    // ── Inițializare periferice ──
    UART_Init(UART_GPS,   9600);
    UART_Init(UART_TELEM, 57600);
    SPI_Init(SPI_IMU,     8000000);
    I2C_Init(I2C_SENSORS, 400000);
    TIM_Init(TIM_DSHOT,   DSHOT600_FREQ);

    // ── Inițializare senzori ──
    IMU_Init();
    GPS_Init();
    Baro_Init();
    Enviro_Init();
    DSHOT_Init();

    // ── Stare inițială ──
    memset(&g_state, 0, sizeof(DroneState));
    g_state.flight_mode   = MODE_DISARMED;
    g_state.failsafe_mode = FS_MODE_NONE;
    g_state.controller_id = CTRL_OWNER;  // Owner are controlul la boot

    // ── Creare cozi ──
    q_imu_data       = xQueueCreate(4,   sizeof(IMUData));
    q_gps_data       = xQueueCreate(4,   sizeof(GPSData));
    q_baro_data      = xQueueCreate(4,   sizeof(BaroData));
    q_enviro_data    = xQueueCreate(2,   sizeof(EnviroData));
    q_motor_cmd      = xQueueCreate(4,   sizeof(MotorCmd));
    q_telem_out      = xQueueCreate(8,   sizeof(TelemetryPacket));
    q_failsafe_event = xQueueCreate(16,  sizeof(FailsafeEvent));
    q_relay_cmd      = xQueueCreate(4,   sizeof(RelayCmd));

    // ── Mutex-uri ──
    mtx_state = xSemaphoreCreateMutex();
    mtx_uart  = xSemaphoreCreateMutex();

    // ── Timere watchdog ──
    wdg_telemetry = xTimerCreate("WDG_TELEM", pdMS_TO_TICKS(2000), pdFALSE, 0, cb_wdg_telemetry);
    wdg_gcs       = xTimerCreate("WDG_GCS",   pdMS_TO_TICKS(3000), pdFALSE, 0, cb_wdg_gcs);
    xTimerStart(wdg_gcs, 0);

    // ── Creare task-uri FreeRTOS ──
    // Numele task,        Funcție,          Stack,  Params, Prioritate,  Handle,  Core
    xTaskCreatePinnedToCore(task_failsafe,    "FAILSAFE", 2048, NULL, 10, NULL, 0); // MAX PRIO
    xTaskCreatePinnedToCore(task_imu_read,    "IMU",      1024, NULL,  9, NULL, 0);
    xTaskCreatePinnedToCore(task_pid_control, "PID",      2048, NULL,  9, NULL, 0);
    xTaskCreatePinnedToCore(task_motor_write, "MOTORS",   1024, NULL,  9, NULL, 0);
    xTaskCreatePinnedToCore(task_gps_read,    "GPS",      1024, NULL,  6, NULL, 1);
    xTaskCreatePinnedToCore(task_baro_read,   "BARO",     512,  NULL,  6, NULL, 1);
    xTaskCreatePinnedToCore(task_enviro_read, "ENVIRO",   512,  NULL,  4, NULL, 1);
    xTaskCreatePinnedToCore(task_telemetry,   "TELEM",    4096, NULL,  6, NULL, 1);
    xTaskCreatePinnedToCore(task_relay,       "RELAY",    1024, NULL,  5, NULL, 1);

    GPIO_SetPin(LED_BOOT, GPIO_PIN_RESET);
    GPIO_SetPin(LED_ARMED, GPIO_PIN_RESET);

    // ── Start scheduler ──
    vTaskStartScheduler();

    // Nu ar trebui să ajungă aici niciodată
    while(1) { HAL_Delay(1000); }
    return 0;
}

// ════════════════════════════════════════════════════════════════
// TASK IMU — 400Hz, Core 0, Prioritate 9
// Citește accelerometru + giroscop ICM-42688
// ════════════════════════════════════════════════════════════════
void task_imu_read(void* pvParams) {
    IMUData data;
    TickType_t xLastWake = xTaskGetTickCount();
    const TickType_t period = pdMS_TO_TICKS(2.5f); // 400Hz

    IMU_Calibrate(); // Calibrare giroscop la pornire (2s)

    while(1) {
        // Citire burst SPI — accelerometru + giroscop (6+6 bytes)
        if (IMU_ReadBurst(&data) == HAL_OK) {
            // Aplică calibrare offset + scale
            IMU_ApplyCalibration(&data);
            // Filtrare Kalman basic pentru giroscop
            IMU_KalmanFilter(&data);
            // Trimite la PID — non-blocking (înlocuiește dacă coada e plină)
            xQueueOverwrite(q_imu_data, &data);
            // Update stare globală
            if (xSemaphoreTake(mtx_state, 0) == pdTRUE) {
                g_state.imu = data;
                g_state.imu_ts = xTaskGetTickCount();
                xSemaphoreGive(mtx_state);
            }
        } else {
            // Eroare IMU — eveniment failsafe
            FailsafeEvent ev = { .type = FS_IMU_ERROR, .severity = SEV_CRITICAL };
            xQueueSend(q_failsafe_event, &ev, 0);
        }
        vTaskDelayUntil(&xLastWake, period);
    }
}

// ════════════════════════════════════════════════════════════════
// TASK GPS — 10Hz, Core 1, Prioritate 6
// Parsează NMEA/UBX de la u-blox F9P
// ════════════════════════════════════════════════════════════════
void task_gps_read(void* pvParams) {
    GPSData data;
    TickType_t xLastWake = xTaskGetTickCount();
    const TickType_t period = pdMS_TO_TICKS(100); // 10Hz

    while(1) {
        if (GPS_ReadUBX(&data) == GPS_FIX_RTK) {
            if (xSemaphoreTake(mtx_state, pdMS_TO_TICKS(5)) == pdTRUE) {
                g_state.gps = data;
                g_state.gps_ts = xTaskGetTickCount();
                // Actualizează home position la primul fix RTK
                if (!g_state.home_set && data.fix_type >= GPS_FIX_3D) {
                    g_state.home_lat = data.lat;
                    g_state.home_lon = data.lon;
                    g_state.home_alt = data.alt_msl;
                    g_state.home_set = true;
                }
                xSemaphoreGive(mtx_state);
            }
            xQueueOverwrite(q_gps_data, &data);
        } else if (data.fix_type == GPS_FIX_NONE) {
            FailsafeEvent ev = { .type = FS_GPS_LOST, .severity = SEV_WARNING };
            xQueueSend(q_failsafe_event, &ev, 0);
        }
        vTaskDelayUntil(&xLastWake, period);
    }
}

// ════════════════════════════════════════════════════════════════
// TASK BARO — 50Hz, Core 1
// MS5611 — altitudine presiune + temperatura
// ════════════════════════════════════════════════════════════════
void task_baro_read(void* pvParams) {
    BaroData data;
    TickType_t xLastWake = xTaskGetTickCount();
    const TickType_t period = pdMS_TO_TICKS(20); // 50Hz

    Baro_Reset();
    HAL_Delay(10);

    while(1) {
        Baro_TriggerMeasurement();
        vTaskDelay(pdMS_TO_TICKS(10)); // Conversie D1+D2
        if (Baro_Read(&data) == HAL_OK) {
            Baro_ComputeAltitude(&data); // Ecuația barometrică internațională
            if (xSemaphoreTake(mtx_state, pdMS_TO_TICKS(2)) == pdTRUE) {
                g_state.baro = data;
                xSemaphoreGive(mtx_state);
            }
            xQueueOverwrite(q_baro_data, &data);
        }
        vTaskDelayUntil(&xLastWake, period);
    }
}

// ════════════════════════════════════════════════════════════════
// TASK ENVIRO — 1Hz, Core 1
// Senzori secundari: baterie, temp, umiditate, vibrații, lichid
// ════════════════════════════════════════════════════════════════
void task_enviro_read(void* pvParams) {
    EnviroData data;
    TickType_t xLastWake = xTaskGetTickCount();
    const TickType_t period = pdMS_TO_TICKS(1000); // 1Hz

    while(1) {
        // Baterie — INA226 (I2C)
        data.battery_voltage = INA226_ReadVoltage();
        data.battery_current = INA226_ReadCurrent();
        data.battery_pct     = Battery_ComputeSOC(data.battery_voltage);
        data.mah_consumed    += (data.battery_current * 1000.0f / 3600.0f); // mAh integrat

        // Temperatură + umiditate — SHT40 (I2C)
        SHT40_Read(&data.temp_c, &data.humidity_pct);

        // Nivel lichid — senzor capacitiv ADC
        data.liquid_pct = ADC_ReadLiquidLevel();

        // Motor temps — NTC pe fiecare braț (ADC × 8)
        for (int i = 0; i < 8; i++) {
            data.motor_temp[i] = ADC_ReadMotorTemp(i);
        }

        // Vibrații — ADXL345 (SPI, per braț)
        for (int i = 0; i < 4; i++) {
            data.vibration[i] = ADXL345_ReadRMS(i);
        }

        if (xSemaphoreTake(mtx_state, pdMS_TO_TICKS(5)) == pdTRUE) {
            g_state.enviro = data;
            xSemaphoreGive(mtx_state);
        }
        xQueueOverwrite(q_enviro_data, &data);

        // Verificare praguri baterie
        if (data.battery_pct < 15.0f) {
            FailsafeEvent ev = { .type = FS_BATTERY_CRITICAL, .severity = SEV_CRITICAL,
                                 .value = data.battery_pct };
            xQueueSend(q_failsafe_event, &ev, 0);
        } else if (data.battery_pct < 30.0f) {
            FailsafeEvent ev = { .type = FS_BATTERY_LOW, .severity = SEV_WARNING,
                                 .value = data.battery_pct };
            xQueueSend(q_failsafe_event, &ev, 0);
        }

        // Verificare temperaturi motoare
        for (int i = 0; i < 8; i++) {
            if (data.motor_temp[i] > MOTOR_TEMP_CRITICAL) {
                FailsafeEvent ev = { .type = FS_MOTOR_OVERHEAT, .severity = SEV_CRITICAL,
                                     .motor_id = i, .value = data.motor_temp[i] };
                xQueueSend(q_failsafe_event, &ev, 0);
            }
        }

        vTaskDelayUntil(&xLastWake, period);
    }
}
