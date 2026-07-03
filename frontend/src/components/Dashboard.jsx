import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { API, useAuth } from "@/App";

const ROLE_LABEL = {
  commander: "Comandant Misiune",
  pilot: "Pilot Dronă",
  observer: "Observator",
};

const ROLE_DESC = {
  commander:
    "Acces total. Poți crea/edita misiuni, gestiona piloți și observatori, controla flota, revizui rapoarte, autoriza operațiuni SAR/RESCUE.",
  pilot:
    "Poți executa misiuni active, comanda direct drona alocată, raporta telemetrie și lansa SOS. NU poți crea utilizatori.",
  observer:
    "Acces read-only: vezi harta operațională, misiunile în derulare, alertele SOS și rapoartele publice. NU poți controla drone.",
};

export default function Dashboard() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const [stats, setStats] = useState({ missions: 0, sos: 0, adapters: 0 });
  const [adapters, setAdapters] = useState([]);
  const [missions, setMissions] = useState([]);
  const [sos, setSos] = useState([]);

  useEffect(() => {
    (async () => {
      try {
        const [a, m, s] = await Promise.all([
          axios.get(`${API}/drone-adapters`),
          axios.get(`${API}/missions`),
          axios.get(`${API}/sos`),
        ]);
        setAdapters(a.data.adapters || []);
        setMissions(m.data || []);
        setSos(s.data || []);
        setStats({
          missions: (m.data || []).length,
          sos: (s.data || []).filter(x => !x.ack).length,
          adapters: (a.data.adapters || []).filter(x => x.status === "ready").length,
        });
      } catch { /* ignore fetch errors */ }
    })();
  }, []);

  const launchDrozon = () => {
    // Opens the main tactical HTML application (served from /public)
    window.location.href = "/drozon.html";
  };

  return (
    <div className="dz-grid-bg dz-scan-line">
      <header className="dz-header">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="dz-logo" data-testid="dashboard-logo">DRO<span>ZON</span></div>
          <div className="dz-tag">COMMAND CENTER · v2.6</div>
        </div>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <div className="dz-user-badge" data-testid="user-badge">
            <span className="callsign">{user.callsign || "—"}</span>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <span className="name">{user.name}</span>
              <span className="name" style={{ fontSize: 9, color: 'var(--dz-muted)' }}>{user.unit || "—"}</span>
            </div>
            <span className={`role role-${user.role}`}>{ROLE_LABEL[user.role]}</span>
          </div>
          {user.role === "commander" && (
            <button className="dz-btn" onClick={() => nav("/users")} data-testid="btn-users">Utilizatori</button>
          )}
          <button className="dz-btn danger" onClick={logout} data-testid="btn-logout">Ieșire</button>
        </div>
      </header>

      <div className="dz-dashboard">
        <div className="dz-panel">
          <div className="dz-panel-title">Briefing operațional · {ROLE_LABEL[user.role]}</div>
          <p style={{ lineHeight: 1.7, color: 'var(--dz-text)', fontSize: 13 }}>
            {ROLE_DESC[user.role]}
          </p>
        </div>

        <div className="dz-grid">
          <div className="dz-stat ok" data-testid="stat-adapters">
            <div className="val">{stats.adapters}</div>
            <div className="lbl">Adaptoare drone active</div>
          </div>
          <div className="dz-stat" data-testid="stat-missions">
            <div className="val">{stats.missions}</div>
            <div className="lbl">Misiuni în sistem</div>
          </div>
          <div className={`dz-stat ${stats.sos ? 'danger' : 'ok'}`} data-testid="stat-sos">
            <div className="val">{stats.sos}</div>
            <div className="lbl">SOS neconfirmat</div>
          </div>
          <div className="dz-stat ok">
            <div className="val" style={{ fontSize: 22 }}>ONLINE</div>
            <div className="lbl">Sistem operațional</div>
          </div>
        </div>

        <div className="dz-launch" data-testid="launch-panel">
          <h2>DESCHIDE CENTRUL TACTIC</h2>
          <p>Hartă live · Telemetrie · Misiuni RESCUE / SWARM / Waypoint · SOS</p>
          <div style={{ display: 'flex', gap: 14, justifyContent: 'center', flexWrap: 'wrap' }}>
            <button className="dz-btn primary" onClick={launchDrozon} data-testid="btn-launch-drozon">
              ▸ Intră în DroZon
            </button>
            <button className="dz-btn" onClick={() => nav("/impact")} data-testid="btn-launch-impact"
              style={{ borderColor: 'var(--dz-accent2)', color: 'var(--dz-accent2)' }}>
              📊 Impact Calculator · Pentru investitori
            </button>
          </div>
        </div>

        <div className="dz-grid" style={{ gridTemplateColumns: '1fr 1fr' }}>
          <div className="dz-panel" data-testid="panel-adapters">
            <div className="dz-panel-title">Adaptoare hardware drone</div>
            {adapters.map(a => (
              <div key={a.id} style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 0', borderBottom: '1px solid var(--dz-border)' }}>
                <div>
                  <div style={{ fontFamily: 'Orbitron', fontSize: 13, letterSpacing: 2, color: 'var(--dz-text)' }}>{a.name}</div>
                  <div style={{ fontSize: 10, color: 'var(--dz-muted)', marginTop: 3 }}>
                    {(a.supported_models || []).slice(0, 3).join(" · ")}
                  </div>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 3 }}>
                  <span style={{ fontSize: 10, letterSpacing: 2, color: a.status === 'ready' ? 'var(--dz-accent2)' : 'var(--dz-muted)' }}>
                    ● {a.status.toUpperCase()}
                  </span>
                  <span style={{ fontSize: 9, color: 'var(--dz-muted)', letterSpacing: 1 }}>
                    MOD: {a.mode}
                  </span>
                </div>
              </div>
            ))}
            <p style={{ fontSize: 10, color: 'var(--dz-muted)', marginTop: 14, letterSpacing: 1, lineHeight: 1.6 }}>
              Firmware C++ (DroZon-MAXIM) suportă MAVLink/ArduPilot și DJI Mobile SDK. În producție, aceste adaptoare comunică direct cu drona.
            </p>
          </div>

          <div className="dz-panel" data-testid="panel-recent-sos">
            <div className="dz-panel-title">Alerte SOS recente</div>
            {sos.length === 0 ? (
              <p style={{ color: 'var(--dz-muted)', fontSize: 12, letterSpacing: 1 }}>
                Fără evenimente SOS. Sistemul este stabil.
              </p>
            ) : (
              sos.slice(0, 5).map(s => (
                <div key={s.id} style={{ padding: '10px 0', borderBottom: '1px solid var(--dz-border)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                    <strong style={{ color: 'var(--dz-danger)', fontFamily: 'Orbitron', fontSize: 12, letterSpacing: 2 }}>
                      🆘 {s.drone_id}
                    </strong>
                    <span style={{ fontSize: 10, color: s.ack ? 'var(--dz-accent2)' : 'var(--dz-warn)', letterSpacing: 2 }}>
                      {s.ack ? "CONFIRMAT" : "NECONFIRMAT"}
                    </span>
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--dz-text)', marginTop: 4 }}>{s.reason}</div>
                  <div style={{ fontSize: 10, color: 'var(--dz-muted)', marginTop: 4 }}>
                    {s.lat.toFixed(4)}, {s.lng.toFixed(4)} · {new Date(s.ts).toLocaleString('ro-RO')}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
