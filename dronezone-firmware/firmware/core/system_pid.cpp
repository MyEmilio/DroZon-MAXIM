// ═══════════════════════════════════════════════════════════════
// core/system.h — Tipuri și structuri globale DroneZone
// ═══════════════════════════════════════════════════════════════
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <string.h>

// ── VERSIUNE FIRMWARE ────────────────────────────────────────────
#define FW_VERSION_MAJOR  1
#define FW_VERSION_MINOR  0
#define FW_VERSION_PATCH  0
#define DRONE_ID          "DRN-001"
#define DRONE_SERIAL      "SN-001-2026"

// ── MODURI DE ZBOR ───────────────────────────────────────────────
typedef enum {
    MODE_DISARMED   = 0,
    MODE_STABILIZE  = 1,
    MODE_ALT_HOLD   = 2,
    MODE_POS_HOLD   = 3,
    MODE_AUTO       = 4,   // Misiune waypoint
    MODE_RTH        = 5,   // Return to Home
    MODE_LAND       = 6,
    MODE_FAILSAFE   = 7,
} FlightMode;

// ── FAILSAFE ─────────────────────────────────────────────────────
typedef enum {
    FS_MODE_NONE        = 0,
    FS_MODE_RTH         = 1,
    FS_MODE_LAND        = 2,
    FS_MODE_HOVER       = 3,
    FS_MODE_DISARM      = 4,
} FailsafeMode;

typedef enum {
    FS_BATTERY_LOW      = 1,
    FS_BATTERY_CRITICAL = 2,
    FS_GCS_LINK_LOST    = 3,
    FS_TELEMETRY_TIMEOUT= 4,
    FS_IMU_ERROR        = 5,
    FS_GPS_LOST         = 6,
    FS_MOTOR_FAULT      = 7,
    FS_MOTOR_OVERHEAT   = 8,
    FS_GEOFENCE_BREACH  = 9,
    FS_RELAY_TIMEOUT    = 10,
} FailsafeEventType;

typedef enum {
    SEV_INFO     = 0,
    SEV_WARNING  = 1,
    SEV_CRITICAL = 2,
} Severity;

typedef struct {
    FailsafeEventType type;
    Severity          severity;
    uint8_t           motor_id;
    float             value;
    uint32_t          timestamp;
} FailsafeEvent;

// ── DATE SENZORI ─────────────────────────────────────────────────
typedef struct {
    float accel_x, accel_y, accel_z;  // m/s²
    float gyro_x,  gyro_y,  gyro_z;   // rad/s
    float temp_c;
    uint32_t timestamp_us;
} IMUData;

typedef struct {
    double lat, lon;       // grade decimale
    float  alt_msl;        // altitudine MSL (m)
    float  alt_rel;        // altitudine relativă față de home (m)
    float  speed_ms;       // viteză orizontală m/s
    float  vspeed_ms;      // viteză verticală m/s
    float  heading;        // heading grade
    uint8_t fix_type;      // 0=none, 1=2D, 2=3D, 3=RTK_float, 4=RTK_fixed
    uint8_t satellites;
    float  hdop;
} GPSData;

#define GPS_FIX_NONE  0
#define GPS_FIX_2D    1
#define GPS_FIX_3D    2
#define GPS_FIX_RTK   4

typedef struct {
    float pressure_pa;
    float temp_c;
    float altitude_m;
    float vspeed_ms;       // viteză verticală calculată din baro
} BaroData;

typedef struct {
    float battery_voltage;
    float battery_current;
    float battery_pct;
    float mah_consumed;
    float temp_c;
    float humidity_pct;
    float liquid_pct;
    float motor_temp[8];
    float vibration[4];    // RMS per braț
} EnviroData;

// ── DATE MOTOARE ─────────────────────────────────────────────────
typedef struct {
    uint16_t throttle[8];  // 0–2047 DSHOT
    bool     beep;
    bool     direction_3d;
} MotorCmd;

typedef struct {
    uint16_t rpm[8];
    float    current[8];
    float    temp[8];
    bool     fault[8];
} ESCTelemetry;

// ── CONTROLUL ATITUDINII ─────────────────────────────────────────
typedef struct {
    float roll, pitch, yaw;    // grade
    float roll_rate, pitch_rate, yaw_rate; // grade/s
    float altitude;
    float throttle;            // 0.0–1.0
} AttitudeSetpoint;

// ── RELAY ────────────────────────────────────────────────────────
typedef enum {
    CTRL_OWNER   = 0,
    CTRL_RELAY   = 1,
} ControllerType;

typedef enum {
    RELAY_CMD_REQUEST  = 1,
    RELAY_CMD_ACCEPT   = 2,
    RELAY_CMD_DECLINE  = 3,
    RELAY_CMD_RETURN   = 4,
    RELAY_CMD_TIMEOUT  = 5,
} RelayCmdType;

typedef struct {
    RelayCmdType type;
    char         pilot_id[32];
    char         token[64];    // Token AES-256 pentru validare
    uint32_t     timestamp;
    float        battery_at_handoff;
} RelayCmd;

// ── STAREA GLOBALĂ ───────────────────────────────────────────────
typedef struct {
    // Senzori
    IMUData    imu;
    GPSData    gps;
    BaroData   baro;
    EnviroData enviro;
    ESCTelemetry esc;

    // Timestamps
    uint32_t imu_ts, gps_ts, baro_ts;

    // Estimator
    float roll_est, pitch_est, yaw_est;   // grade
    float altitude_est;                    // m
    float vspeed_est;                      // m/s

    // Control
    FlightMode    flight_mode;
    FailsafeMode  failsafe_mode;
    AttitudeSetpoint setpoint;
    MotorCmd      last_motor_cmd;

    // Navigație
    double home_lat, home_lon;
    float  home_alt;
    bool   home_set;
    double target_lat, target_lon;
    float  target_alt;

    // Sistem
    ControllerType controller_id;
    char           current_pilot[32];
    uint32_t       flight_time_sec;
    float          total_dist_km;
    bool           armed;

    // Statistici
    float max_altitude;
    float min_battery;
} DroneState;

// ── PRAGURI HARDWARE ─────────────────────────────────────────────
#define BATTERY_LOW_PCT         30.0f
#define BATTERY_CRITICAL_PCT    15.0f
#define MOTOR_TEMP_WARNING      70.0f
#define MOTOR_TEMP_CRITICAL     85.0f
#define MOTOR_CURRENT_MAX       18.0f
#define SIGNAL_WEAK_PCT         40.0f
#define GCS_TIMEOUT_MS          3000
#define TELEMETRY_TIMEOUT_MS    2000
#define RELAY_ACCEPT_TIMEOUT_MS 15000


// ═══════════════════════════════════════════════════════════════
// core/config.h — Pinout STM32H743 / Pixhawk 6X
// ═══════════════════════════════════════════════════════════════
#pragma once

// ── SPI (IMU) ────────────────────────────────────────────────────
#define SPI_IMU         SPI1
#define IMU_CS_PIN      GPIO_PIN_4
#define IMU_CS_PORT     GPIOA
#define IMU_INT_PIN     GPIO_PIN_3
#define IMU_INT_PORT    GPIOB

// ── I2C (Senzori auxiliari) ──────────────────────────────────────
#define I2C_SENSORS     I2C1
#define INA226_ADDR     0x40   // Senzor curent/tensiune
#define SHT40_ADDR      0x44   // Temp+umiditate
#define MS5611_ADDR     0x77   // Barometru

// ── UART ─────────────────────────────────────────────────────────
#define UART_GPS        USART2  // GPS u-blox F9P (921600 baud)
#define UART_TELEM      USART3  // Telemetrie MAVLink (57600 baud)
#define UART_RC         UART4   // RC receiver SBUS/CRSF
#define UART_ESC        UART5   // ESC telemetrie

// ── TIMERE DSHOT ─────────────────────────────────────────────────
#define TIM_DSHOT       TIM1
#define DSHOT600_FREQ   1200000  // 1.2MHz pentru DSHOT600
// Canale motoare PWM (TIM1_CH1..4 + TIM2_CH1..4)
#define MOTOR_1_CH      TIM_CHANNEL_1
#define MOTOR_2_CH      TIM_CHANNEL_2
#define MOTOR_3_CH      TIM_CHANNEL_3
#define MOTOR_4_CH      TIM_CHANNEL_4
#define MOTOR_5_CH      TIM_CHANNEL_1  // TIM2
#define MOTOR_6_CH      TIM_CHANNEL_2
#define MOTOR_7_CH      TIM_CHANNEL_3
#define MOTOR_8_CH      TIM_CHANNEL_4

// ── GPIO ─────────────────────────────────────────────────────────
#define LED_BOOT        GPIO_PIN_1, GPIOE
#define LED_ARMED       GPIO_PIN_2, GPIOE
#define LED_ERROR       GPIO_PIN_3, GPIOE
#define BUZZER_PIN      GPIO_PIN_5, GPIOD
#define KILL_SWITCH_PIN GPIO_PIN_6, GPIOD

// ── ADC ──────────────────────────────────────────────────────────
#define ADC_LIQUID      ADC1_IN0
#define ADC_MOTOR_TEMP0 ADC1_IN1
// ... ADC1_IN1..8 pentru temperaturi motoare


// ═══════════════════════════════════════════════════════════════
// pid/controller.cpp — PID Cascadat 3 Axe (Roll, Pitch, Yaw)
// ═══════════════════════════════════════════════════════════════
#include "controller.h"
#include "../core/system.h"
#include "../motors/dshot.h"
#include <math.h>

// ── Structura PID ────────────────────────────────────────────────
typedef struct {
    float kp, ki, kd;
    float integral;
    float prev_error;
    float i_max;       // Anti-windup
    float out_min, out_max;
    float dt;
} PIDController;

// ── PID-uri externe (rate) ───────────────────────────────────────
static PIDController pid_roll_rate   = { .kp=0.15f, .ki=0.05f, .kd=0.003f, .i_max=0.3f, .out_min=-1.f, .out_max=1.f };
static PIDController pid_pitch_rate  = { .kp=0.15f, .ki=0.05f, .kd=0.003f, .i_max=0.3f, .out_min=-1.f, .out_max=1.f };
static PIDController pid_yaw_rate    = { .kp=0.20f, .ki=0.08f, .kd=0.001f, .i_max=0.4f, .out_min=-1.f, .out_max=1.f };

// ── PID-uri interne (atitudine) ──────────────────────────────────
static PIDController pid_roll_att    = { .kp=6.5f,  .ki=0.0f,  .kd=0.0f,   .i_max=0.0f, .out_min=-200.f,.out_max=200.f };
static PIDController pid_pitch_att   = { .kp=6.5f,  .ki=0.0f,  .kd=0.0f,   .i_max=0.0f, .out_min=-200.f,.out_max=200.f };
static PIDController pid_yaw_att     = { .kp=4.0f,  .ki=0.0f,  .kd=0.0f,   .i_max=0.0f, .out_min=-200.f,.out_max=200.f };

// ── PID altitudine ───────────────────────────────────────────────
static PIDController pid_alt         = { .kp=0.8f,  .ki=0.15f, .kd=0.2f,   .i_max=0.5f, .out_min=-0.5f, .out_max=0.5f };

// ── Funcție calcul PID ───────────────────────────────────────────
static float pid_compute(PIDController* pid, float setpoint, float measured, float dt) {
    float error = setpoint - measured;
    pid->integral += error * dt;
    // Anti-windup clamp
    pid->integral = fmaxf(-pid->i_max, fminf(pid->i_max, pid->integral));
    float derivative = (error - pid->prev_error) / dt;
    pid->prev_error = error;
    float output = pid->kp * error + pid->ki * pid->integral + pid->kd * derivative;
    return fmaxf(pid->out_min, fminf(pid->out_max, output));
}

// ── Mixer octocopter X8 ──────────────────────────────────────────
// Dispunere motoare (văzut de sus, sens acelor):
//   M1(FR-top) M2(BL-top) M3(FL-top) M4(BR-top)
//   M5(FR-bot) M6(BL-bot) M7(FL-bot) M8(BR-bot)
static void mixer_x8(float throttle, float roll, float pitch, float yaw, MotorCmd* cmd) {
    // Factori mixer pentru X8 coaxial
    float m[8];
    m[0] = throttle + roll - pitch + yaw;  // FR top (CW)
    m[1] = throttle - roll + pitch + yaw;  // BL top (CW)
    m[2] = throttle - roll - pitch - yaw;  // FL top (CCW)
    m[3] = throttle + roll + pitch - yaw;  // BR top (CCW)
    m[4] = throttle + roll - pitch - yaw;  // FR bot (CCW)
    m[5] = throttle - roll + pitch - yaw;  // BL bot (CCW)
    m[6] = throttle - roll - pitch + yaw;  // FL bot (CW)
    m[7] = throttle + roll + pitch + yaw;  // BR bot (CW)

    // Normalizare 0–2047 DSHOT
    for (int i = 0; i < 8; i++) {
        m[i] = fmaxf(0.0f, fminf(1.0f, m[i]));
        cmd->throttle[i] = (uint16_t)(m[i] * 2047.0f);
    }
}

// ════════════════════════════════════════════════════════════════
// TASK PID — 400Hz, Core 0, Prioritate 9
// Bucla de control principală: Estimator → PID → Mixer → DSHOT
// ════════════════════════════════════════════════════════════════
void task_pid_control(void* pvParams) {
    IMUData  imu;
    BaroData baro;
    MotorCmd cmd;
    AttitudeSetpoint sp;

    TickType_t xLastWake = xTaskGetTickCount();
    const TickType_t period = pdMS_TO_TICKS(2.5f); // 400Hz
    const float dt = 0.0025f;  // 2.5ms

    // Estimator stare (Complementary filter — simplu și rapid)
    float roll_est = 0.0f, pitch_est = 0.0f, yaw_est = 0.0f;
    const float alpha = 0.98f;  // Factor giroscop vs accelerometru

    while(1) {
        // ── Dacă drona e disarmată — motoare la minim ──
        if (g_state.flight_mode == MODE_DISARMED ||
            g_state.flight_mode == MODE_FAILSAFE) {
            memset(&cmd, 0, sizeof(MotorCmd));
            xQueueOverwrite(q_motor_cmd, &cmd);
            vTaskDelayUntil(&xLastWake, period);
            continue;
        }

        // ── Citire senzori (non-blocking) ──
        xQueuePeek(q_imu_data, &imu, 0);
        xQueuePeek(q_baro_data, &baro, 0);

        if (xSemaphoreTake(mtx_state, pdMS_TO_TICKS(1)) == pdTRUE) {
            sp = g_state.setpoint;
            xSemaphoreGive(mtx_state);
        }

        // ── Estimator atitudine (Complementary Filter) ──
        // Unghi din accelerometru
        float accel_roll  = atan2f(imu.accel_y, imu.accel_z) * RAD_TO_DEG;
        float accel_pitch = atan2f(-imu.accel_x,
            sqrtf(imu.accel_y*imu.accel_y + imu.accel_z*imu.accel_z)) * RAD_TO_DEG;

        // Integrare giroscop
        roll_est  = alpha * (roll_est  + imu.gyro_x * dt * RAD_TO_DEG)
                  + (1.0f - alpha) * accel_roll;
        pitch_est = alpha * (pitch_est + imu.gyro_y * dt * RAD_TO_DEG)
                  + (1.0f - alpha) * accel_pitch;
        yaw_est  += imu.gyro_z * dt * RAD_TO_DEG; // Yaw doar din giroscop

        // ── PID Cascadat ──
        // Nivel 1: Atitudine → Rată dorită
        float roll_rate_sp  = pid_compute(&pid_roll_att,  sp.roll,  roll_est,  dt);
        float pitch_rate_sp = pid_compute(&pid_pitch_att, sp.pitch, pitch_est, dt);
        float yaw_rate_sp   = pid_compute(&pid_yaw_att,   sp.yaw,   yaw_est,   dt);

        // Nivel 2: Rată → Comandă motor
        float roll_out  = pid_compute(&pid_roll_rate,  roll_rate_sp,  imu.gyro_x * RAD_TO_DEG, dt);
        float pitch_out = pid_compute(&pid_pitch_rate, pitch_rate_sp, imu.gyro_y * RAD_TO_DEG, dt);
        float yaw_out   = pid_compute(&pid_yaw_rate,   yaw_rate_sp,   imu.gyro_z * RAD_TO_DEG, dt);

        // PID Altitudine (în mod ALT_HOLD sau AUTO)
        float throttle = sp.throttle;
        if (g_state.flight_mode == MODE_ALT_HOLD ||
            g_state.flight_mode == MODE_AUTO) {
            float alt_correction = pid_compute(&pid_alt, sp.altitude, baro.altitude_m, dt);
            throttle = fmaxf(0.1f, fminf(0.9f, 0.5f + alt_correction));
        }

        // ── Mixer → Comenzi DSHOT ──
        mixer_x8(throttle, roll_out, pitch_out, yaw_out, &cmd);

        // ── Update stare globală ──
        if (xSemaphoreTake(mtx_state, 0) == pdTRUE) {
            g_state.roll_est    = roll_est;
            g_state.pitch_est   = pitch_est;
            g_state.yaw_est     = yaw_est;
            g_state.altitude_est = baro.altitude_m;
            g_state.last_motor_cmd = cmd;
            xSemaphoreGive(mtx_state);
        }

        xQueueOverwrite(q_motor_cmd, &cmd);
        vTaskDelayUntil(&xLastWake, period);
    }
}

// ════════════════════════════════════════════════════════════════
// TASK MOTOR WRITE — 400Hz, Core 0, Prioritate 9
// Trimite comenzi DSHOT600 la ESC-uri
// ════════════════════════════════════════════════════════════════
void task_motor_write(void* pvParams) {
    MotorCmd cmd;
    TickType_t xLastWake = xTaskGetTickCount();
    const TickType_t period = pdMS_TO_TICKS(2.5f);

    while(1) {
        if (xQueueReceive(q_motor_cmd, &cmd, pdMS_TO_TICKS(3)) == pdTRUE) {
            DSHOT_SendAll(cmd.throttle);
            // Citește telemetria ESC înapoi (curent, rpm, temp)
            ESCTelemetry esc_telem;
            if (DSHOT_ReadTelemetry(&esc_telem) == HAL_OK) {
                // Verifică avarii motoare
                for (int i = 0; i < 8; i++) {
                    if (esc_telem.fault[i]) {
                        FailsafeEvent ev = {
                            .type = FS_MOTOR_FAULT,
                            .severity = SEV_CRITICAL,
                            .motor_id = (uint8_t)i,
                            .value = esc_telem.current[i]
                        };
                        xQueueSend(q_failsafe_event, &ev, 0);
                    }
                }
                if (xSemaphoreTake(mtx_state, 0) == pdTRUE) {
                    g_state.esc = esc_telem;
                    xSemaphoreGive(mtx_state);
                }
            }
        }
        vTaskDelayUntil(&xLastWake, period);
    }
}
