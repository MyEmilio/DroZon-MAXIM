// ═══════════════════════════════════════════════════════════════
// motors/dshot.cpp — Protocol DSHOT600
// ═══════════════════════════════════════════════════════════════
#include "dshot.h"
#include "../core/config.h"
#include "stm32h7xx_hal.h"

// DSHOT600: 1 bit = 1.67μs → 0=625ns HIGH, 1=1250ns HIGH
// Frame: 11 bit throttle (0-2047) + 1 bit telemetrie + 4 bit CRC
#define DSHOT_BIT_0    26   // Timer ticks pentru bit "0" (1/3 din perioadă)
#define DSHOT_BIT_1    52   // Timer ticks pentru bit "1" (2/3 din perioadă)
#define DSHOT_PERIOD   79   // Perioadă totală bit

static uint32_t dshot_dma_buffer[8][18];  // 8 motoare × 16 biți + 2 padding

static uint16_t dshot_make_packet(uint16_t throttle, bool telemetry) {
    uint16_t packet = (throttle << 1) | (telemetry ? 1 : 0);
    // CRC: XOR pe nibble-uri
    uint8_t crc = (~(packet ^ (packet >> 4) ^ (packet >> 8))) & 0x0F;
    return (packet << 4) | crc;
}

static void dshot_encode_packet(uint16_t packet, uint32_t* buf) {
    for (int i = 15; i >= 0; i--) {
        buf[15 - i] = (packet & (1 << i)) ? DSHOT_BIT_1 : DSHOT_BIT_0;
    }
    buf[16] = 0;  // Padding reset
    buf[17] = 0;
}

void DSHOT_Init(void) {
    // Configuram TIM1 + TIM2 cu DMA pentru DSHOT600
    // Frecvență timer: 240MHz / 200 = 1.2MHz
    HAL_TIM_PWM_Start_DMA(&htim1, TIM_CHANNEL_1, dshot_dma_buffer[0], 18);
    HAL_TIM_PWM_Start_DMA(&htim1, TIM_CHANNEL_2, dshot_dma_buffer[1], 18);
    HAL_TIM_PWM_Start_DMA(&htim1, TIM_CHANNEL_3, dshot_dma_buffer[2], 18);
    HAL_TIM_PWM_Start_DMA(&htim1, TIM_CHANNEL_4, dshot_dma_buffer[3], 18);
    HAL_TIM_PWM_Start_DMA(&htim2, TIM_CHANNEL_1, dshot_dma_buffer[4], 18);
    HAL_TIM_PWM_Start_DMA(&htim2, TIM_CHANNEL_2, dshot_dma_buffer[5], 18);
    HAL_TIM_PWM_Start_DMA(&htim2, TIM_CHANNEL_3, dshot_dma_buffer[6], 18);
    HAL_TIM_PWM_Start_DMA(&htim2, TIM_CHANNEL_4, dshot_dma_buffer[7], 18);
}

void DSHOT_SendAll(uint16_t throttle[8]) {
    for (int i = 0; i < 8; i++) {
        uint16_t packet = dshot_make_packet(
            throttle[i],
            (i == 0) // Request telemetrie de la M1 (round-robin)
        );
        dshot_encode_packet(packet, dshot_dma_buffer[i]);
    }
    // DMA trimite automat la urmorul ciclu timer
}

// Comandă specială DSHOT: ARM (trimite 0 de 300 ori)
void DSHOT_Arm(void) {
    uint16_t zero[8] = {0};
    for (int i = 0; i < 300; i++) {
        DSHOT_SendAll(zero);
        HAL_Delay(1);
    }
}

// Beep de confirmare ARM
void DSHOT_Beep(uint8_t tone) {
    uint16_t cmd[8];
    for (int i = 0; i < 8; i++) cmd[i] = tone; // DSHOT CMD 1-5 = beep
    DSHOT_SendAll(cmd);
}


// ═══════════════════════════════════════════════════════════════
// telemetry/mavlink.cpp — MAVLink 2.0 + DroneZone WebSocket
// ═══════════════════════════════════════════════════════════════
#include "mavlink.h"
#include "../core/system.h"
#include "mavlink/v2.0/common/mavlink.h"  // biblioteca MAVLink

// Buffer UART
static uint8_t uart_rx_buf[256];
static uint8_t uart_tx_buf[512];

// Contoare MAVLink
static uint8_t  mav_seq    = 0;
static uint8_t  sys_id     = 1;   // ID sistem (dronă)
static uint8_t  comp_id    = 1;   // ID component (FCU)
static uint32_t boot_time  = 0;   // ms de la pornire

// ── Trimite heartbeat periodic ────────────────────────────────
static void mav_send_heartbeat(void) {
    mavlink_message_t msg;
    uint8_t buf[MAVLINK_MAX_PACKET_LEN];

    uint8_t base_mode = MAV_MODE_FLAG_CUSTOM_MODE_ENABLED;
    if (g_state.armed) base_mode |= MAV_MODE_FLAG_SAFETY_ARMED;

    mavlink_msg_heartbeat_pack(sys_id, comp_id, &msg,
        MAV_TYPE_OCTOROTOR,
        MAV_AUTOPILOT_PX4,
        base_mode,
        (uint32_t)g_state.flight_mode,
        MAV_STATE_ACTIVE);

    uint16_t len = mavlink_msg_to_send_buffer(buf, &msg);
    UART_Transmit(UART_TELEM, buf, len);
}

// ── Trimite telemetrie atitudine ─────────────────────────────
static void mav_send_attitude(void) {
    mavlink_message_t msg;
    uint8_t buf[MAVLINK_MAX_PACKET_LEN];
    uint32_t time_ms = HAL_GetTick() - boot_time;

    mavlink_msg_attitude_pack(sys_id, comp_id, &msg,
        time_ms,
        g_state.roll_est  * DEG_TO_RAD,
        g_state.pitch_est * DEG_TO_RAD,
        g_state.yaw_est   * DEG_TO_RAD,
        g_state.imu.gyro_x,
        g_state.imu.gyro_y,
        g_state.imu.gyro_z);

    uint16_t len = mavlink_msg_to_send_buffer(buf, &msg);
    UART_Transmit(UART_TELEM, buf, len);
}

// ── Trimite poziție GPS ──────────────────────────────────────
static void mav_send_gps(void) {
    mavlink_message_t msg;
    uint8_t buf[MAVLINK_MAX_PACKET_LEN];

    mavlink_msg_global_position_int_pack(sys_id, comp_id, &msg,
        HAL_GetTick() - boot_time,
        (int32_t)(g_state.gps.lat * 1e7),
        (int32_t)(g_state.gps.lon * 1e7),
        (int32_t)(g_state.gps.alt_msl * 1000),
        (int32_t)(g_state.gps.alt_rel * 1000),
        (int16_t)(g_state.imu.accel_x * 100),
        (int16_t)(g_state.imu.accel_y * 100),
        (int16_t)(g_state.imu.accel_z * 100),
        (uint16_t)(g_state.yaw_est * 100));

    uint16_t len = mavlink_msg_to_send_buffer(buf, &msg);
    UART_Transmit(UART_TELEM, buf, len);
}

// ── Trimite stare baterie ────────────────────────────────────
static void mav_send_battery(void) {
    mavlink_message_t msg;
    uint8_t buf[MAVLINK_MAX_PACKET_LEN];

    // Tensiuni celule (mV)
    int16_t voltages[10] = {UINT16_MAX};
    float cell_v = g_state.enviro.battery_voltage / 6.0f;
    for (int i = 0; i < 6; i++) voltages[i] = (int16_t)(cell_v * 1000);

    mavlink_msg_battery_status_pack(sys_id, comp_id, &msg,
        0,                                          // battery_id
        MAV_BATTERY_FUNCTION_ALL,
        MAV_BATTERY_TYPE_LIPO,
        (int16_t)(g_state.enviro.temp_c * 100),
        voltages,
        (int16_t)(g_state.enviro.battery_current * 100),
        (int32_t)g_state.enviro.mah_consumed,
        -1,                                         // energy_consumed
        (int8_t)g_state.enviro.battery_pct,
        0,                                          // time_remaining
        MAV_BATTERY_CHARGE_STATE_OK);

    uint16_t len = mavlink_msg_to_send_buffer(buf, &msg);
    UART_Transmit(UART_TELEM, buf, len);
}

// ── Trimite SYS_STATUS (sănătate sistem) ──────────────────────
static void mav_send_sys_status(void) {
    mavlink_message_t msg;
    uint8_t buf[MAVLINK_MAX_PACKET_LEN];

    uint32_t sensors_present = MAV_SYS_STATUS_SENSOR_3D_GYRO |
                                MAV_SYS_STATUS_SENSOR_3D_ACCEL |
                                MAV_SYS_STATUS_SENSOR_ABSOLUTE_PRESSURE |
                                MAV_SYS_STATUS_SENSOR_GPS;

    mavlink_msg_sys_status_pack(sys_id, comp_id, &msg,
        sensors_present,
        sensors_present,  // enabled
        sensors_present,  // health
        300,              // CPU load (%)
        (uint16_t)(g_state.enviro.battery_voltage * 1000),
        (int16_t)(g_state.enviro.battery_current * 100),
        (int8_t)g_state.enviro.battery_pct,
        0, 0, 0, 0, 0, 0);

    uint16_t len = mavlink_msg_to_send_buffer(buf, &msg);
    UART_Transmit(UART_TELEM, buf, len);
}

// ── Parsează comenzi primite de la GCS ───────────────────────
static void mav_parse_incoming(void) {
    mavlink_message_t msg;
    mavlink_status_t  status;
    uint8_t byte;

    // Citire buffer UART cu timeout scurt
    while (UART_Receive_IT(UART_TELEM, &byte, 1) == HAL_OK) {
        if (mavlink_parse_char(MAVLINK_COMM_0, byte, &msg, &status)) {
            switch (msg.msgid) {
                case MAVLINK_MSG_ID_HEARTBEAT:
                    // GCS viu — resetează watchdog
                    xTimerReset(wdg_gcs, 0);
                    break;

                case MAVLINK_MSG_ID_SET_MODE: {
                    mavlink_set_mode_t mode_msg;
                    mavlink_msg_set_mode_decode(&msg, &mode_msg);
                    if (xSemaphoreTake(mtx_state, pdMS_TO_TICKS(5)) == pdTRUE) {
                        g_state.flight_mode = (FlightMode)mode_msg.custom_mode;
                        xSemaphoreGive(mtx_state);
                    }
                    break;
                }

                case MAVLINK_MSG_ID_COMMAND_LONG: {
                    mavlink_command_long_t cmd;
                    mavlink_msg_command_long_decode(&msg, &cmd);
                    if (cmd.command == MAV_CMD_COMPONENT_ARM_DISARM) {
                        bool arm = (cmd.param1 > 0.5f);
                        if (xSemaphoreTake(mtx_state, pdMS_TO_TICKS(5)) == pdTRUE) {
                            g_state.armed = arm;
                            if (arm) {
                                DSHOT_Arm();
                                DSHOT_Beep(1);
                                g_state.flight_mode = MODE_STABILIZE;
                                GPIO_SetPin(LED_ARMED, GPIO_PIN_SET);
                            } else {
                                g_state.flight_mode = MODE_DISARMED;
                                GPIO_SetPin(LED_ARMED, GPIO_PIN_RESET);
                            }
                            xSemaphoreGive(mtx_state);
                        }
                    }
                    break;
                }

                case MAVLINK_MSG_ID_MANUAL_CONTROL: {
                    mavlink_manual_control_t ctrl;
                    mavlink_msg_manual_control_decode(&msg, &ctrl);
                    if (xSemaphoreTake(mtx_state, pdMS_TO_TICKS(2)) == pdTRUE) {
                        g_state.setpoint.roll     = ctrl.x * 0.3f;  // ±30 grade
                        g_state.setpoint.pitch    = ctrl.y * 0.3f;
                        g_state.setpoint.yaw_rate = ctrl.r * 90.0f; // ±90 grade/s
                        g_state.setpoint.throttle = (ctrl.z + 1000.0f) / 2000.0f;
                        xSemaphoreGive(mtx_state);
                    }
                    break;
                }

                // Handoff relay — mesaj custom MAVLink
                case MAVLINK_MSG_ID_DEBUG_VECT: {
                    // Refolosim DEBUG_VECT pentru comenzi relay (workaround)
                    RelayCmd rcmd;
                    // Decode din name field
                    xQueueSend(q_relay_cmd, &rcmd, 0);
                    break;
                }
            }
        }
    }
}

// ════════════════════════════════════════════════════════════════
// TASK TELEMETRIE — 10Hz, Core 1, Prioritate 6
// ════════════════════════════════════════════════════════════════
void task_telemetry(void* pvParams) {
    TickType_t xLastWake = xTaskGetTickCount();
    const TickType_t period = pdMS_TO_TICKS(100); // 10Hz
    uint8_t hb_counter = 0;

    boot_time = HAL_GetTick();

    while(1) {
        // ── Parsează comenzi primite ──
        mav_parse_incoming();

        // ── Trimite telemetrie ──
        if (xSemaphoreTake(mtx_uart, pdMS_TO_TICKS(10)) == pdTRUE) {
            mav_send_attitude();
            mav_send_gps();

            // Baterie + sys_status la 1Hz (1/10 din 10Hz)
            if (++hb_counter >= 10) {
                mav_send_heartbeat();
                mav_send_battery();
                mav_send_sys_status();
                hb_counter = 0;

                // Resetează watchdog telemetrie
                xTimerReset(wdg_telemetry, 0);
            }
            xSemaphoreGive(mtx_uart);
        }

        // Update contoare zbor
        if (g_state.armed && xSemaphoreTake(mtx_state, 0) == pdTRUE) {
            g_state.flight_time_sec++;
            if (g_state.altitude_est > g_state.max_altitude)
                g_state.max_altitude = g_state.altitude_est;
            if (g_state.enviro.battery_pct < g_state.min_battery)
                g_state.min_battery = g_state.enviro.battery_pct;
            xSemaphoreGive(mtx_state);
        }

        vTaskDelayUntil(&xLastWake, period);
    }
}


// ═══════════════════════════════════════════════════════════════
// failsafe/failsafe.cpp — Sistem Failsafe & Avarii
// ═══════════════════════════════════════════════════════════════
#include "failsafe.h"

// Istoric evenimente (circular buffer)
#define FS_LOG_SIZE 32
static FailsafeEvent fs_log[FS_LOG_SIZE];
static uint8_t fs_log_idx = 0;

static void fs_log_event(const FailsafeEvent* ev) {
    fs_log[fs_log_idx % FS_LOG_SIZE] = *ev;
    fs_log[fs_log_idx % FS_LOG_SIZE].timestamp = HAL_GetTick();
    fs_log_idx++;
}

static void fs_trigger_rth(void) {
    if (xSemaphoreTake(mtx_state, pdMS_TO_TICKS(10)) == pdTRUE) {
        g_state.flight_mode  = MODE_RTH;
        g_state.target_lat   = g_state.home_lat;
        g_state.target_lon   = g_state.home_lon;
        g_state.target_alt   = g_state.home_alt + 10.0f; // +10m safety
        g_state.failsafe_mode = FS_MODE_RTH;
        xSemaphoreGive(mtx_state);
    }
    GPIO_SetPin(LED_ERROR, GPIO_PIN_SET);
    DSHOT_Beep(3); // 3 beep-uri = RTH
}

static void fs_trigger_land(void) {
    if (xSemaphoreTake(mtx_state, pdMS_TO_TICKS(10)) == pdTRUE) {
        g_state.flight_mode   = MODE_LAND;
        g_state.failsafe_mode = FS_MODE_LAND;
        g_state.setpoint.altitude = 0.0f;
        xSemaphoreGive(mtx_state);
    }
}

static void fs_trigger_disarm(void) {
    if (xSemaphoreTake(mtx_state, pdMS_TO_TICKS(10)) == pdTRUE) {
        g_state.armed        = false;
        g_state.flight_mode  = MODE_DISARMED;
        g_state.failsafe_mode = FS_MODE_DISARM;
        xSemaphoreGive(mtx_state);
    }
    GPIO_SetPin(LED_ARMED, GPIO_PIN_RESET);
    DSHOT_Beep(5); // 5 beep-uri = DISARM forțat
}

// ════════════════════════════════════════════════════════════════
// TASK FAILSAFE — 100Hz, Core 0, Prioritate MAX (10)
// ════════════════════════════════════════════════════════════════
void task_failsafe(void* pvParams) {
    FailsafeEvent ev;

    while(1) {
        // Blochează până vine un eveniment
        if (xQueueReceive(q_failsafe_event, &ev, pdMS_TO_TICKS(100)) == pdTRUE) {
            fs_log_event(&ev);

            switch (ev.type) {

                case FS_BATTERY_LOW:
                    // La 30%: RTH dacă nu suntem deja
                    if (g_state.flight_mode != MODE_RTH &&
                        g_state.flight_mode != MODE_LAND &&
                        g_state.armed) {
                        // Trimite alertă MAVLink
                        // mav_send_statustext(MAV_SEVERITY_WARNING, "BATTERY LOW - RTH initiated")
                        if (g_state.home_set) fs_trigger_rth();
                    }
                    break;

                case FS_BATTERY_CRITICAL:
                    // La 15%: Aterizare imediată
                    if (g_state.armed) {
                        // mav_send_statustext(MAV_SEVERITY_CRITICAL, "BATTERY CRITICAL - LANDING")
                        fs_trigger_land();
                    }
                    break;

                case FS_GCS_LINK_LOST:
                    // Pierdere legătură GCS > 3s: RTH
                    if (g_state.armed && g_state.flight_mode != MODE_RTH) {
                        // Verifică dacă relay e activ
                        if (g_state.controller_id == CTRL_RELAY) {
                            // Relay activ — trimite alertă, nu RTH încă
                            FailsafeEvent relay_ev = { .type = FS_RELAY_TIMEOUT, .severity = SEV_WARNING };
                            xQueueSend(q_failsafe_event, &relay_ev, 0);
                        } else {
                            fs_trigger_rth();
                        }
                    }
                    break;

                case FS_RELAY_TIMEOUT:
                    // Relay nu a preluat în timp util: RTH
                    if (g_state.armed) fs_trigger_rth();
                    break;

                case FS_IMU_ERROR:
                    // IMU defect — disarm imediat (nu putem zbura fără IMU)
                    fs_trigger_disarm();
                    break;

                case FS_GPS_LOST:
                    // GPS pierdut: trece la STABILIZE (pilot manual)
                    if (g_state.flight_mode == MODE_AUTO ||
                        g_state.flight_mode == MODE_POS_HOLD) {
                        if (xSemaphoreTake(mtx_state, pdMS_TO_TICKS(5)) == pdTRUE) {
                            g_state.flight_mode = MODE_ALT_HOLD;
                            xSemaphoreGive(mtx_state);
                        }
                    }
                    break;

                case FS_MOTOR_FAULT:
                    // Motor defect: RTH cu putere redusă sau disarm
                    // Octocopter poate zbura cu 7/8 motoare
                    if (ev.severity == SEV_CRITICAL) {
                        // Verifică câte motoare sunt defecte
                        int fault_count = 0;
                        for (int i = 0; i < 8; i++)
                            if (g_state.esc.fault[i]) fault_count++;
                        if (fault_count >= 2) fs_trigger_land();
                        else fs_trigger_rth();
                    }
                    break;

                case FS_MOTOR_OVERHEAT:
                    // Motor supraîncălzit: RTH
                    if (ev.value > MOTOR_TEMP_CRITICAL && g_state.armed)
                        fs_trigger_rth();
                    break;

                case FS_GEOFENCE_BREACH:
                    // Ieșire din geofence: RTH imediat
                    fs_trigger_rth();
                    break;

                default: break;
            }
        }

        // Verificare periodică hardware watchdog
        HAL_IWDG_Refresh(&hiwdg);
    }
}


// ═══════════════════════════════════════════════════════════════
// relay/handoff.cpp — Protocol Transfer Control (Poștalion)
// ═══════════════════════════════════════════════════════════════
#include "handoff.h"
#include <string.h>

#define TOKEN_LEN  32
#define TOKEN_TIMEOUT_MS  15000

static char   active_token[TOKEN_LEN + 1] = {0};
static bool   handoff_pending    = false;
static uint32_t handoff_req_time = 0;

// Generează token simplu (în producție: AES-256 HMAC)
static void generate_token(char* out, uint32_t seed) {
    // Simplificat — în producție folosești crypto HAL
    snprintf(out, TOKEN_LEN + 1, "TKN%08lX%08lX", seed, HAL_GetTick());
}

static bool validate_token(const char* token) {
    return (strlen(token) > 0 && strncmp(token, active_token, TOKEN_LEN) == 0);
}

// ════════════════════════════════════════════════════════════════
// TASK RELAY — Event-driven, Core 1, Prioritate 5
// ════════════════════════════════════════════════════════════════
void task_relay(void* pvParams) {
    RelayCmd cmd;

    while(1) {
        // Așteptare comandă relay (blochează până vine)
        if (xQueueReceive(q_relay_cmd, &cmd, pdMS_TO_TICKS(500)) == pdTRUE) {

            switch (cmd.type) {

                // ── OWNER inițiază transfer ────────────────────
                case RELAY_CMD_REQUEST:
                    if (g_state.controller_id != CTRL_OWNER) break;
                    if (handoff_pending) break; // Transfer deja în curs

                    // Generează token de autentificare
                    generate_token(active_token, cmd.timestamp);
                    handoff_pending  = true;
                    handoff_req_time = HAL_GetTick();

                    // Trimite token înapoi la GCS pentru a fi transmis relay-ului
                    // mav_send_named_value_str("RELAY_TOKEN", active_token)

                    // Pornește timer de timeout acceptare (15s)
                    // Dacă relay-ul nu răspunde, eveniment FS_RELAY_TIMEOUT
                    break;

                // ── Relay ACCEPTĂ controlul ────────────────────
                case RELAY_CMD_ACCEPT:
                    if (!handoff_pending) break;

                    // Verifică token și timeout
                    if (!validate_token(cmd.token)) {
                        // Token invalid — ignoră
                        break;
                    }
                    if ((HAL_GetTick() - handoff_req_time) > TOKEN_TIMEOUT_MS) {
                        // Timeout expirat — refuză
                        handoff_pending = false;
                        memset(active_token, 0, sizeof(active_token));
                        break;
                    }

                    // Transfer confirmat
                    if (xSemaphoreTake(mtx_state, pdMS_TO_TICKS(10)) == pdTRUE) {
                        g_state.controller_id = CTRL_RELAY;
                        strncpy(g_state.current_pilot, cmd.pilot_id, 31);
                        xSemaphoreGive(mtx_state);
                    }
                    handoff_pending = false;

                    // Confirmă prin MAVLink la ambii piloți
                    // mav_send_statustext(MAV_SEVERITY_INFO, "RELAY CTRL ACTIVE")
                    // mav_send_named_value_str("CTRL_PILOT", cmd.pilot_id)

                    DSHOT_Beep(2); // 2 beep-uri = transfer confirmat
                    break;

                // ── Relay REFUZĂ sau RETURNEAZĂ controlul ─────
                case RELAY_CMD_DECLINE:
                case RELAY_CMD_RETURN:
                    if (g_state.controller_id == CTRL_RELAY &&
                        strncmp(g_state.current_pilot, cmd.pilot_id, 31) == 0) {
                        if (xSemaphoreTake(mtx_state, pdMS_TO_TICKS(10)) == pdTRUE) {
                            g_state.controller_id = CTRL_OWNER;
                            strncpy(g_state.current_pilot, "OWNER", 31);
                            xSemaphoreGive(mtx_state);
                        }
                    }
                    handoff_pending = false;
                    memset(active_token, 0, sizeof(active_token));

                    // mav_send_statustext(MAV_SEVERITY_INFO, "CTRL RETURNED TO OWNER")
                    DSHOT_Beep(1);
                    break;

                // ── Timeout fără răspuns ──────────────────────
                case RELAY_CMD_TIMEOUT:
                    handoff_pending = false;
                    memset(active_token, 0, sizeof(active_token));
                    // Failsafe se ocupă de ce urmează
                    break;
            }
        }

        // Verificare timeout handoff pending
        if (handoff_pending &&
            (HAL_GetTick() - handoff_req_time) > TOKEN_TIMEOUT_MS) {
            handoff_pending = false;
            memset(active_token, 0, sizeof(active_token));
            FailsafeEvent ev = { .type = FS_RELAY_TIMEOUT, .severity = SEV_WARNING };
            xQueueSend(q_failsafe_event, &ev, 0);
        }
    }
}
