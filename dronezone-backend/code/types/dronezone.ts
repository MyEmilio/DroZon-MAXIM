// types/dronezone.ts
// ═══════════════════════════════════════════════════════════
// Toate tipurile TypeScript pentru DroneZone
// ═══════════════════════════════════════════════════════════

export type UserRole = 'owner' | 'relay' | 'observer'
export type DroneStatus = 'idle' | 'flying' | 'charging' | 'maintenance' | 'offline'
export type MissionType = 'incendiu' | 'coletarie' | 'salvare' | 'survey' | 'inspectie' | 'patrulare'
export type HandoffStatus = 'pending' | 'accepted' | 'declined' | 'timeout' | 'completed'
export type AlertSeverity = 'info' | 'warning' | 'critical'

// ── PROFILE ──────────────────────────────────────────────
export interface Profile {
  id: string
  full_name: string
  role: UserRole
  phone?: string
  avatar_url?: string
  is_online: boolean
  last_seen: string
  push_token?: string
  created_at: string
}

// ── DRONĂ ────────────────────────────────────────────────
export interface Drone {
  id: string
  name: string
  serial: string
  owner_id: string
  status: DroneStatus
  current_pilot?: string
  battery_pct: number
  battery_voltage?: number
  lat?: number
  lon?: number
  altitude_m?: number
  speed_ms?: number
  heading_deg?: number
  signal_pct?: number
  flight_time_sec: number
  total_dist_km: number
  last_telemetry?: string
  created_at: string
  updated_at: string
  // Joined
  owner?: Profile
  pilot?: Profile
}

// ── TELEMETRIE ───────────────────────────────────────────
export interface TelemetryPoint {
  id?: number
  drone_id: string
  ts?: string
  battery_pct: number
  voltage?: number
  current_a?: number
  lat?: number
  lon?: number
  altitude_m?: number
  speed_ms?: number
  heading_deg?: number
  signal_pct?: number
  temp_c?: number
  humidity?: number
  wind_ms?: number
  motor_rpm?: Record<string, number>
  motor_amp?: Record<string, number>
  motor_temp?: Record<string, number>
  gps_sats?: number
  liquid_pct?: number
  pilot_id?: string
}

// ── MISIUNE ──────────────────────────────────────────────
export interface Waypoint {
  lat: number
  lon: number
  alt: number
  action?: 'hover' | 'photo' | 'video' | 'spray' | 'land'
}

export interface Mission {
  id: string
  drone_id: string
  pilot_id: string
  type: MissionType
  title?: string
  description?: string
  waypoints?: Waypoint[]
  started_at: string
  ended_at?: string
  distance_km: number
  flight_sec: number
  mah_consumed: number
  max_altitude?: number
  avg_speed?: number
  notes?: string
  created_at: string
  // Joined
  drone?: Drone
  pilot?: Profile
}

// ── HANDOFF ──────────────────────────────────────────────
export interface Handoff {
  id: string
  drone_id: string
  mission_id?: string
  from_pilot_id: string
  to_pilot_id: string
  status: HandoffStatus
  initiated_at: string
  responded_at?: string
  completed_at?: string
  declined_reason?: string
  battery_at_handoff?: number
  alt_at_handoff?: number
  lat_at_handoff?: number
  lon_at_handoff?: number
  // Joined
  from_pilot?: Profile
  to_pilot?: Profile
  drone?: Drone
}

// ── ALERTĂ ───────────────────────────────────────────────
export interface Alert {
  id: string
  drone_id: string
  severity: AlertSeverity
  type: AlertType
  message: string
  data?: Record<string, unknown>
  acknowledged: boolean
  ack_by?: string
  ack_at?: string
  created_at: string
  drone?: Drone
}

export type AlertType =
  | 'battery_low'
  | 'battery_critical'
  | 'motor_fault'
  | 'signal_lost'
  | 'signal_weak'
  | 'gps_lost'
  | 'geofence_breach'
  | 'liquid_low'
  | 'temp_high'
  | 'handoff_request'
  | 'handoff_accepted'
  | 'handoff_declined'
  | 'mission_complete'
  | 'landing'

// ── FLIGHT REPORT ────────────────────────────────────────
export interface FlightReport {
  id: string
  mission_id: string
  drone_id: string
  pilot_id: string
  summary: FlightSummary
  created_at: string
}

export interface FlightSummary {
  mission: Mission
  drone: Drone
  pilot: Profile
  stats: {
    total_distance_km: number
    max_altitude_m: number
    avg_speed_ms: number
    flight_duration_sec: number
    mah_consumed: number
    min_battery_pct: number
    handoffs_count: number
    alerts_count: number
    waypoints_completed: number
  }
  telemetry_path: Array<{ lat: number; lon: number; alt: number; ts: string }>
  alerts: Alert[]
  handoffs: Handoff[]
}

// ── WEBSOCKET EVENTS ─────────────────────────────────────
export type RealtimeEvent =
  | { event: 'telemetry'; payload: TelemetryPoint }
  | { event: 'drone_update'; payload: Partial<Drone> }
  | { event: 'handoff_request'; payload: Handoff }
  | { event: 'handoff_response'; payload: Handoff }
  | { event: 'alert'; payload: Alert }
  | { event: 'pilot_online'; payload: { pilot_id: string; is_online: boolean } }
