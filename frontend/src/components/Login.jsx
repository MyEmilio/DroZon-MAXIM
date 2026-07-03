import { useState } from "react";
import axios from "axios";
import { API, useAuth } from "@/App";

function formatErr(detail) {
  if (!detail) return "A intervenit o eroare. Încearcă din nou.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail.map(e => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e))).join(" ");
  if (detail && typeof detail.msg === "string") return detail.msg;
  return String(detail);
}

export default function Login() {
  const { refresh } = useAuth();
  const [tab, setTab] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [callsign, setCallsign] = useState("");
  const [unit, setUnit] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (tab === "login") {
        await axios.post(`${API}/auth/login`, { email, password });
      } else {
        await axios.post(`${API}/auth/register`, {
          email, password, name,
          role: "observer",
          callsign: callsign || null,
          unit: unit || null,
        });
      }
      await refresh();
    } catch (err) {
      setError(formatErr(err?.response?.data?.detail) || err.message);
    } finally {
      setBusy(false);
    }
  };

  const fillDemo = (role) => {
    if (role === "commander") { setEmail("comandant@drozon.ro"); setPassword("Comandant2026!"); }
    if (role === "pilot") { setEmail("pilot@drozon.ro"); setPassword("Pilot2026!"); }
    if (role === "observer") { setEmail("observer@drozon.ro"); setPassword("Observer2026!"); }
    setTab("login");
  };

  return (
    <div className="dz-grid-bg dz-scan-line">
      <div className="dz-login-wrap">
        <div className="dz-login-card" data-testid="login-card">
          <div className="dz-login-brand">
            <h1>DRO<span>ZON</span></h1>
            <p>Command &amp; Control · ISU · Salvamont</p>
          </div>

          <div className="dz-tabs" role="tablist">
            <button className={`dz-tab ${tab === "login" ? "active" : ""}`}
              onClick={() => setTab("login")}
              data-testid="tab-login">Autentificare</button>
            <button className={`dz-tab ${tab === "register" ? "active" : ""}`}
              onClick={() => setTab("register")}
              data-testid="tab-register">Înregistrare observator</button>
          </div>

          {error && <div className="dz-error" data-testid="login-error">{error}</div>}

          <form onSubmit={submit}>
            {tab === "register" && (
              <div className="dz-field">
                <label>Nume complet</label>
                <input className="dz-input" required minLength={2}
                  value={name} onChange={(e) => setName(e.target.value)}
                  data-testid="register-name" />
              </div>
            )}
            <div className="dz-field">
              <label>Email</label>
              <input type="email" className="dz-input" required
                value={email} onChange={(e) => setEmail(e.target.value)}
                data-testid="login-email" />
            </div>
            <div className="dz-field">
              <label>Parolă</label>
              <input type="password" className="dz-input" required minLength={6}
                value={password} onChange={(e) => setPassword(e.target.value)}
                data-testid="login-password" />
            </div>
            {tab === "register" && (
              <>
                <div className="dz-field">
                  <label>Callsign (opțional)</label>
                  <input className="dz-input"
                    value={callsign} onChange={(e) => setCallsign(e.target.value)}
                    placeholder="ex: EAGLE-3"
                    data-testid="register-callsign" />
                </div>
                <div className="dz-field">
                  <label>Unitate (opțional)</label>
                  <input className="dz-input"
                    value={unit} onChange={(e) => setUnit(e.target.value)}
                    placeholder="ex: ISU Cluj / Salvamont Sinaia"
                    data-testid="register-unit" />
                </div>
              </>
            )}
            <button type="submit" className="dz-btn primary" disabled={busy}
              style={{ width: "100%", marginTop: 8 }}
              data-testid="login-submit">
              {busy ? "SE PROCESEAZĂ…" : tab === "login" ? "ACCES SISTEM" : "CREEAZĂ CONT"}
            </button>
          </form>

          <div className="dz-hint">
            <div style={{marginBottom: 10, letterSpacing: 3, color: 'var(--dz-accent2)'}}>▸ CONTURI DEMO ‹ CLICK →</div>
            <div style={{display: 'flex', gap: 6, justifyContent: 'center', flexWrap: 'wrap'}}>
              <button type="button" className="dz-btn" style={{padding: '6px 12px', fontSize: 9}}
                onClick={() => fillDemo("commander")} data-testid="demo-commander">
                Comandant
              </button>
              <button type="button" className="dz-btn" style={{padding: '6px 12px', fontSize: 9}}
                onClick={() => fillDemo("pilot")} data-testid="demo-pilot">
                Pilot
              </button>
              <button type="button" className="dz-btn" style={{padding: '6px 12px', fontSize: 9}}
                onClick={() => fillDemo("observer")} data-testid="demo-observer">
                Observator
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
