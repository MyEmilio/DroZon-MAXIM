import { useEffect, useState, createContext, useContext } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate, useNavigate } from "react-router-dom";
import axios from "axios";
import Login from "@/components/Login";
import Dashboard from "@/components/Dashboard";
import UserAdmin from "@/components/UserAdmin";
import ImpactCalculator from "@/components/ImpactCalculator";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

axios.defaults.withCredentials = true;

export const AuthContext = createContext(null);
export const useAuth = () => useContext(AuthContext);

function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const refresh = async () => {
    try {
      const { data } = await axios.get(`${API}/auth/me`);
      setUser(data);
    } catch (_) {
      setUser(false);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { refresh(); }, []);

  const logout = async () => {
    try { await axios.post(`${API}/auth/logout`); } catch { /* ignore */ }
    setUser(false);
  };

  return (
    <AuthContext.Provider value={{ user, setUser, loading, refresh, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

function Protected({ children, roles }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="fullscreen-loading" data-testid="loading-screen">SISTEM SE INIȚIALIZEAZĂ…</div>;
  if (!user) return <Navigate to="/" replace />;
  if (roles && !roles.includes(user.role)) return <Navigate to="/dashboard" replace />;
  return children;
}

function LandingSwitch() {
  const { user, loading } = useAuth();
  if (loading) return <div className="fullscreen-loading">SISTEM SE INIȚIALIZEAZĂ…</div>;
  if (user) return <Navigate to="/dashboard" replace />;
  return <Login />;
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<LandingSwitch />} />
          <Route path="/dashboard" element={<Protected><Dashboard /></Protected>} />
          <Route path="/users" element={<Protected roles={["commander"]}><UserAdmin /></Protected>} />
          <Route path="/impact" element={<Protected><ImpactCalculator /></Protected>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
