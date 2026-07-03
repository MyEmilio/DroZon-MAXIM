import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { API, useAuth } from "@/App";

const ROLES = [
  { value: "commander", label: "Comandant" },
  { value: "pilot", label: "Pilot" },
  { value: "observer", label: "Observator" },
];

export default function UserAdmin() {
  const { user } = useAuth();
  const nav = useNavigate();
  const [users, setUsers] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    email: "", password: "", name: "", role: "pilot", callsign: "", unit: "",
  });

  const load = async () => {
    try {
      const { data } = await axios.get(`${API}/users`);
      setUsers(data);
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    }
  };

  useEffect(() => { load(); }, []);

  const createUser = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await axios.post(`${API}/auth/register`, {
        email: form.email,
        password: form.password,
        name: form.name,
        role: form.role,
        callsign: form.callsign || null,
        unit: form.unit || null,
      });
      setForm({ email: "", password: "", name: "", role: "pilot", callsign: "", unit: "" });
      await load();
    } catch (e) {
      const d = e.response?.data?.detail;
      setError(typeof d === "string" ? d : JSON.stringify(d));
    } finally {
      setBusy(false);
    }
  };

  const changeRole = async (id, role) => {
    await axios.patch(`${API}/users/${id}/role`, { role });
    load();
  };

  const del = async (id) => {
    if (!window.confirm("Șterge acest utilizator?")) return;
    await axios.delete(`${API}/users/${id}`);
    load();
  };

  return (
    <div className="dz-grid-bg dz-scan-line">
      <header className="dz-header">
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <div className="dz-logo">DRO<span>ZON</span></div>
          <div className="dz-tag">User Admin</div>
        </div>
        <button className="dz-back" onClick={() => nav("/dashboard")} data-testid="back-dashboard">
          ← Înapoi la Dashboard
        </button>
      </header>

      <div className="dz-dashboard">
        <div className="dz-panel">
          <div className="dz-panel-title">Creează utilizator nou</div>
          {error && <div className="dz-error">{error}</div>}
          <form onSubmit={createUser} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
            <div className="dz-field">
              <label>Email</label>
              <input className="dz-input" type="email" required
                value={form.email} onChange={e => setForm({ ...form, email: e.target.value })}
                data-testid="admin-email" />
            </div>
            <div className="dz-field">
              <label>Parolă</label>
              <input className="dz-input" type="password" required minLength={6}
                value={form.password} onChange={e => setForm({ ...form, password: e.target.value })}
                data-testid="admin-password" />
            </div>
            <div className="dz-field">
              <label>Nume complet</label>
              <input className="dz-input" required
                value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}
                data-testid="admin-name" />
            </div>
            <div className="dz-field">
              <label>Rol</label>
              <select className="dz-select" value={form.role}
                onChange={e => setForm({ ...form, role: e.target.value })}
                data-testid="admin-role">
                {ROLES.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
              </select>
            </div>
            <div className="dz-field">
              <label>Callsign</label>
              <input className="dz-input"
                value={form.callsign} onChange={e => setForm({ ...form, callsign: e.target.value })}
                placeholder="ex: HAWK-2"
                data-testid="admin-callsign" />
            </div>
            <div className="dz-field">
              <label>Unitate</label>
              <input className="dz-input"
                value={form.unit} onChange={e => setForm({ ...form, unit: e.target.value })}
                placeholder="ex: ISU Cluj"
                data-testid="admin-unit" />
            </div>
            <div style={{ gridColumn: '1 / -1' }}>
              <button type="submit" className="dz-btn primary" disabled={busy}
                data-testid="admin-create-user">
                {busy ? "SE CREEAZĂ…" : "CREEAZĂ UTILIZATOR"}
              </button>
            </div>
          </form>
        </div>

        <div className="dz-panel" style={{ marginTop: 20 }}>
          <div className="dz-panel-title">Utilizatori înregistrați ({users.length})</div>
          <table className="dz-table" data-testid="users-table">
            <thead>
              <tr>
                <th>Callsign</th>
                <th>Nume</th>
                <th>Email</th>
                <th>Unitate</th>
                <th>Rol</th>
                <th>Acțiuni</th>
              </tr>
            </thead>
            <tbody>
              {users.map(u => (
                <tr key={u.id}>
                  <td style={{ fontFamily: 'Orbitron', letterSpacing: 2, color: 'var(--dz-accent)' }}>{u.callsign || "—"}</td>
                  <td>{u.name}</td>
                  <td style={{ color: 'var(--dz-muted)' }}>{u.email}</td>
                  <td>{u.unit || "—"}</td>
                  <td>
                    <select className="dz-select" style={{ padding: '4px 8px', fontSize: 11 }}
                      value={u.role}
                      onChange={e => changeRole(u.id, e.target.value)}
                      disabled={u.id === user.id}
                      data-testid={`role-select-${u.id}`}>
                      {ROLES.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
                    </select>
                  </td>
                  <td>
                    {u.id !== user.id && (
                      <button className="dz-btn danger" style={{ padding: '4px 10px', fontSize: 10 }}
                        onClick={() => del(u.id)}
                        data-testid={`delete-user-${u.id}`}>
                        Șterge
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
