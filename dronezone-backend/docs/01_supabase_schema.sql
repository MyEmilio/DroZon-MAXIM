-- ═══════════════════════════════════════════════════════════════
-- DRONEZONE — SUPABASE SCHEMA COMPLET
-- Rulează în Supabase SQL Editor (Settings → SQL Editor)
-- ═══════════════════════════════════════════════════════════════

-- ── 1. EXTENSII ──────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── 2. ENUM-URI ──────────────────────────────────────────────
CREATE TYPE user_role AS ENUM ('owner', 'relay', 'observer');
CREATE TYPE drone_status AS ENUM ('idle', 'flying', 'charging', 'maintenance', 'offline');
CREATE TYPE mission_type AS ENUM ('incendiu', 'coletarie', 'salvare', 'survey', 'inspectie', 'patrulare');
CREATE TYPE handoff_status AS ENUM ('pending', 'accepted', 'declined', 'timeout', 'completed');
CREATE TYPE alert_severity AS ENUM ('info', 'warning', 'critical');

-- ── 3. PROFILES (extinde auth.users din Supabase) ────────────
CREATE TABLE profiles (
  id          UUID REFERENCES auth.users(id) ON DELETE CASCADE PRIMARY KEY,
  full_name   TEXT NOT NULL,
  role        user_role NOT NULL DEFAULT 'observer',
  phone       TEXT,
  avatar_url  TEXT,
  is_online   BOOLEAN DEFAULT FALSE,
  last_seen   TIMESTAMPTZ DEFAULT NOW(),
  push_token  TEXT,                        -- PWA push subscription JSON
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Auto-create profile when user signs up
CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO profiles (id, full_name, role)
  VALUES (
    NEW.id,
    COALESCE(NEW.raw_user_meta_data->>'full_name', 'Pilot'),
    COALESCE((NEW.raw_user_meta_data->>'role')::user_role, 'observer')
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION handle_new_user();

-- ── 4. DRONE ─────────────────────────────────────────────────
CREATE TABLE drones (
  id              UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  name            TEXT NOT NULL,               -- ex: "DRN-001 AGRO-ALFA"
  serial          TEXT UNIQUE NOT NULL,
  owner_id        UUID REFERENCES profiles(id),
  status          drone_status DEFAULT 'idle',
  current_pilot   UUID REFERENCES profiles(id),-- cine are controlul acum
  battery_pct     NUMERIC(5,2) DEFAULT 100,
  battery_voltage NUMERIC(5,2),
  lat             NUMERIC(10,7),
  lon             NUMERIC(10,7),
  altitude_m      NUMERIC(7,2),
  speed_ms        NUMERIC(6,2),
  heading_deg     NUMERIC(6,2),
  signal_pct      NUMERIC(5,2),
  flight_time_sec INTEGER DEFAULT 0,
  total_dist_km   NUMERIC(10,3) DEFAULT 0,
  last_telemetry  TIMESTAMPTZ,
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── 5. TELEMETRIE (time-series) ──────────────────────────────
CREATE TABLE telemetry (
  id          BIGSERIAL PRIMARY KEY,
  drone_id    UUID REFERENCES drones(id) ON DELETE CASCADE,
  ts          TIMESTAMPTZ DEFAULT NOW(),
  battery_pct NUMERIC(5,2),
  voltage     NUMERIC(5,2),
  current_a   NUMERIC(6,2),
  lat         NUMERIC(10,7),
  lon         NUMERIC(10,7),
  altitude_m  NUMERIC(7,2),
  speed_ms    NUMERIC(6,2),
  heading_deg NUMERIC(6,2),
  signal_pct  NUMERIC(5,2),
  temp_c      NUMERIC(5,2),
  humidity    NUMERIC(5,2),
  wind_ms     NUMERIC(5,2),
  motor_rpm   JSONB,    -- {m1:4820, m2:4835, ...}
  motor_amp   JSONB,    -- {m1:8.2, m2:8.3, ...}
  motor_temp  JSONB,    -- {m1:41, m2:40, ...}
  gps_sats    INTEGER,
  liquid_pct  NUMERIC(5,2),
  pilot_id    UUID REFERENCES profiles(id)
);

-- Index pentru query-uri rapide
CREATE INDEX idx_telemetry_drone_ts ON telemetry(drone_id, ts DESC);

-- Auto-delete telemetrie mai veche de 30 zile (retention policy)
CREATE OR REPLACE FUNCTION delete_old_telemetry()
RETURNS void AS $$
BEGIN
  DELETE FROM telemetry WHERE ts < NOW() - INTERVAL '30 days';
END;
$$ LANGUAGE plpgsql;

-- ── 6. MISIUNI ───────────────────────────────────────────────
CREATE TABLE missions (
  id            UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  drone_id      UUID REFERENCES drones(id),
  pilot_id      UUID REFERENCES profiles(id),
  type          mission_type NOT NULL,
  title         TEXT,
  description   TEXT,
  waypoints     JSONB,       -- [{lat, lon, alt, action}]
  started_at    TIMESTAMPTZ DEFAULT NOW(),
  ended_at      TIMESTAMPTZ,
  distance_km   NUMERIC(10,3) DEFAULT 0,
  flight_sec    INTEGER DEFAULT 0,
  mah_consumed  INTEGER DEFAULT 0,
  max_altitude  NUMERIC(7,2),
  avg_speed     NUMERIC(6,2),
  notes         TEXT,
  created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- ── 7. HANDOFF / RELAY ──────────────────────────────────────
CREATE TABLE handoffs (
  id              UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  drone_id        UUID REFERENCES drones(id),
  mission_id      UUID REFERENCES missions(id),
  from_pilot_id   UUID REFERENCES profiles(id),
  to_pilot_id     UUID REFERENCES profiles(id),
  status          handoff_status DEFAULT 'pending',
  initiated_at    TIMESTAMPTZ DEFAULT NOW(),
  responded_at    TIMESTAMPTZ,
  completed_at    TIMESTAMPTZ,
  declined_reason TEXT,
  battery_at_handoff NUMERIC(5,2),
  alt_at_handoff     NUMERIC(7,2),
  lat_at_handoff     NUMERIC(10,7),
  lon_at_handoff     NUMERIC(10,7)
);

-- ── 8. ALERTE ────────────────────────────────────────────────
CREATE TABLE alerts (
  id          UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  drone_id    UUID REFERENCES drones(id),
  severity    alert_severity NOT NULL,
  type        TEXT NOT NULL,    -- ex: 'battery_low', 'motor_fault', 'signal_lost'
  message     TEXT NOT NULL,
  data        JSONB,            -- date suplimentare
  acknowledged BOOLEAN DEFAULT FALSE,
  ack_by      UUID REFERENCES profiles(id),
  ack_at      TIMESTAMPTZ,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ── 9. FLIGHT LOGS (pentru rapoarte PDF) ────────────────────
CREATE TABLE flight_logs (
  id            UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  mission_id    UUID REFERENCES missions(id),
  drone_id      UUID REFERENCES drones(id),
  pilot_id      UUID REFERENCES profiles(id),
  summary       JSONB,    -- rezumat complet generat post-zbor
  created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- ── 10. ROW LEVEL SECURITY ───────────────────────────────────
ALTER TABLE profiles   ENABLE ROW LEVEL SECURITY;
ALTER TABLE drones     ENABLE ROW LEVEL SECURITY;
ALTER TABLE telemetry  ENABLE ROW LEVEL SECURITY;
ALTER TABLE missions   ENABLE ROW LEVEL SECURITY;
ALTER TABLE handoffs   ENABLE ROW LEVEL SECURITY;
ALTER TABLE alerts     ENABLE ROW LEVEL SECURITY;
ALTER TABLE flight_logs ENABLE ROW LEVEL SECURITY;

-- Profiles: fiecare vede toți (pentru listă piloți), editează doar al lui
CREATE POLICY "profiles_select_all" ON profiles FOR SELECT USING (true);
CREATE POLICY "profiles_update_own" ON profiles FOR UPDATE USING (auth.uid() = id);

-- Drones: toți autentificați văd, doar owner și piloți activi modifică
CREATE POLICY "drones_select_auth" ON drones FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "drones_update_pilot" ON drones FOR UPDATE
  USING (auth.uid() = owner_id OR auth.uid() = current_pilot);

-- Telemetrie: toți autentificați văd, inserează oricine autentificat
CREATE POLICY "telemetry_select_auth" ON telemetry FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "telemetry_insert_auth" ON telemetry FOR INSERT WITH CHECK (auth.role() = 'authenticated');

-- Misiuni: toți văd, piloții implicați modifică
CREATE POLICY "missions_select_auth" ON missions FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "missions_insert_auth" ON missions FOR INSERT WITH CHECK (auth.role() = 'authenticated');
CREATE POLICY "missions_update_pilot" ON missions FOR UPDATE USING (auth.uid() = pilot_id);

-- Handoffs: văd owner și relay implicat
CREATE POLICY "handoffs_select" ON handoffs FOR SELECT
  USING (auth.uid() = from_pilot_id OR auth.uid() = to_pilot_id);
CREATE POLICY "handoffs_insert" ON handoffs FOR INSERT WITH CHECK (auth.uid() = from_pilot_id);
CREATE POLICY "handoffs_update" ON handoffs FOR UPDATE
  USING (auth.uid() = from_pilot_id OR auth.uid() = to_pilot_id);

-- Alerte: toți autentificați văd
CREATE POLICY "alerts_select_auth" ON alerts FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "alerts_insert_auth" ON alerts FOR INSERT WITH CHECK (auth.role() = 'authenticated');

-- Flight logs: toți autentificați văd
CREATE POLICY "flight_logs_select" ON flight_logs FOR SELECT USING (auth.role() = 'authenticated');

-- ── 11. REALTIME (activează pentru tabele cheie) ─────────────
-- Rulează în Supabase Dashboard → Database → Replication
-- Activează: drones, telemetry, handoffs, alerts
-- Sau prin SQL:
ALTER PUBLICATION supabase_realtime ADD TABLE drones;
ALTER PUBLICATION supabase_realtime ADD TABLE telemetry;
ALTER PUBLICATION supabase_realtime ADD TABLE handoffs;
ALTER PUBLICATION supabase_realtime ADD TABLE alerts;

-- ── 12. DATE INIȚIALE (seed) ─────────────────────────────────
-- Rulează după ce creezi primii utilizatori prin Auth
-- INSERT INTO drones (name, serial, status) VALUES
--   ('DRN-001 AGRO-ALFA', 'SN-001-2026', 'idle'),
--   ('DRN-002 INSP-BETA', 'SN-002-2026', 'idle'),
--   ('DRN-003 SURV-GAMMA', 'SN-003-2026', 'offline');
