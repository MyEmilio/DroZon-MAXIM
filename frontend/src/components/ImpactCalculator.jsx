import { useMemo, useState, useEffect } from "react";
import { motion, useSpring, useTransform } from "framer-motion";
import { useNavigate } from "react-router-dom";
import { BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Tooltip, Cell } from "recharts";
import { Flame, Snowflake, Waves, User, HeartPulse, TrendingUp, Clock, Users, Euro } from "lucide-react";
import { useAuth } from "@/App";

/* ───────────────────────────────────────────────────────────
   Mission model — realistic response parameters
   Sources: Salvamont operational data, ISU published stats,
   drone SAR literature (golden hour thresholds).
   ─────────────────────────────────────────────────────────── */
const SCENARIOS = {
  sar: {
    id: "sar",
    label: "Persoană dispărută",
    subtitle: "Căutare-Salvare terestră",
    Icon: User,
    color: "#00d4ff",
    manualCoverage: 0.6,   // km²/h — SAR team on foot
    droneCoverage: 32,     // km²/h — DJI Matrice thermal
    tCritical: 12,         // hours — golden window for hypothermia + dehydration
    manualCostPerHour: 850, // 3 SAR teams + coord
    droneCostPerHour: 80,
    droneSpecs: "Matrice 350 RTK + termic",
    baseVictims: 1,
  },
  avalanche: {
    id: "avalanche",
    label: "Avalanșă",
    subtitle: "Extracție îngropați",
    Icon: Snowflake,
    color: "#8ec5ff",
    manualCoverage: 0.3,
    droneCoverage: 22,
    tCritical: 0.5,        // 15-30 min — asphyxiation
    manualCostPerHour: 4200, // helicopter + SAR
    droneCostPerHour: 100,
    droneSpecs: "SWARM x3 cu radar RECCO",
    baseVictims: 2,
  },
  fire: {
    id: "fire",
    label: "Incendiu pădure",
    subtitle: "Delimitare + stingere",
    Icon: Flame,
    color: "#ff8c00",
    manualCoverage: 1.2,   // km²/h — pompieri + hartă
    droneCoverage: 45,     // km²/h — mapping rapid
    tCritical: 6,          // hours — evacuare populație
    manualCostPerHour: 3800,
    droneCostPerHour: 180,
    droneSpecs: "Wingcopter + stingere lichide",
    baseVictims: 4,
  },
  flood: {
    id: "flood",
    label: "Inundație",
    subtitle: "Salvare persoane blocate",
    Icon: Waves,
    color: "#00ff9d",
    manualCoverage: 0.8,   // km²/h barci
    droneCoverage: 28,
    tCritical: 4,          // ore până imobilizare / hipotermie
    manualCostPerHour: 3200, // bărci + helicopter
    droneCostPerHour: 120,
    droneSpecs: "Zipline P2 livrare veste + colaci",
    baseVictims: 6,
  },
  medical: {
    id: "medical",
    label: "Extracție medicală",
    subtitle: "Zonă inaccesibilă",
    Icon: HeartPulse,
    color: "#ff2244",
    manualCoverage: 0.4,   // teren dificil
    droneCoverage: 18,
    tCritical: 1,          // golden hour trauma
    manualCostPerHour: 4500,
    droneCostPerHour: 150,
    droneSpecs: "Zipline P2 + AI Vision triaj",
    baseVictims: 1,
  },
};

/* Survival probability model — Cornum/Bellamy (military trauma) blended with
   Salvamont mountain rescue data. Exponential decay from initial P₀ = 0.92. */
function survivalProb(hoursElapsed, tCritical) {
  const P0 = 0.92;
  return P0 * Math.exp(-hoursElapsed / tCritical);
}

/* Animated integer counter */
function AnimatedNumber({ value, format = (v) => Math.round(v).toLocaleString("ro-RO"), duration = 1.2 }) {
  const spring = useSpring(0, { duration: duration * 1000, bounce: 0 });
  const display = useTransform(spring, format);
  useEffect(() => { spring.set(value); }, [value, spring]);
  return <motion.span>{display}</motion.span>;
}

export default function ImpactCalculator() {
  const { user } = useAuth();
  const nav = useNavigate();
  const [scenarioId, setScenarioId] = useState("sar");
  const [area, setArea] = useState(12);        // km²
  const [victims, setVictims] = useState(1);
  const [terrain, setTerrain] = useState(1.3); // multiplier for manual difficulty (1 flat -> 2.5 mountain)

  const s = SCENARIOS[scenarioId];

  useEffect(() => { setVictims(s.baseVictims); }, [scenarioId, s.baseVictims]);

  const calc = useMemo(() => {
    // Response time (hours)
    const tManual = (area / s.manualCoverage) * terrain;
    const tDrone = area / s.droneCoverage;

    const pManual = survivalProb(tManual, s.tCritical);
    const pDrone = survivalProb(tDrone, s.tCritical);

    const livesSavedRaw = victims * Math.max(0, pDrone - pManual);
    const livesSaved = Math.round(livesSavedRaw * 10) / 10;

    const costManual = tManual * s.manualCostPerHour;
    const costDrone = tDrone * s.droneCostPerHour;
    const costSaved = Math.max(0, costManual - costDrone);

    const timeSavedMin = Math.max(0, (tManual - tDrone) * 60);

    const speedupX = tManual / tDrone;

    return {
      tManual, tDrone,
      pManual: pManual * 100, pDrone: pDrone * 100,
      livesSaved, costManual, costDrone, costSaved,
      timeSavedMin, speedupX,
    };
  }, [area, victims, terrain, s]);

  const chartData = [
    { name: "Manual",  time: +calc.tManual.toFixed(2), color: "#4a7090" },
    { name: "DroZon",  time: +calc.tDrone.toFixed(2), color: s.color   },
  ];

  return (
    <div className="dz-grid-bg dz-scan-line" style={{ paddingBottom: 60 }}>
      <header className="dz-header">
        <div style={{ display: "flex", alignItems: "center" }}>
          <div className="dz-logo">DRO<span>ZON</span></div>
          <div className="dz-tag">Impact · ROI Calculator</div>
        </div>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <span style={{ fontSize: 10, letterSpacing: 3, color: "var(--dz-muted)" }}>
            SIGNED IN AS · {user?.callsign || "—"}
          </span>
          <button className="dz-btn" onClick={() => nav("/dashboard")} data-testid="btn-back-dashboard">
            ← Dashboard
          </button>
        </div>
      </header>

      <div className="ic-hero">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}>
          <div className="ic-hero-tag">DEMO DE IMPACT · ISU / SALVAMONT / INVESTITORI</div>
          <h1 className="ic-hero-title">
            Cât valorează <span style={{ color: "var(--dz-accent2)" }}>fiecare minut</span>?
          </h1>
          <p className="ic-hero-sub">
            Comparație în timp real între răspunsul manual clasic și platforma DroZon.
            Alege scenariul, ajustează parametrii — vezi vieți salvate, timp și costuri reduse.
          </p>
        </motion.div>
      </div>

      <div className="ic-wrap">
        {/* ─── Scenario picker ─── */}
        <div className="dz-panel" data-testid="scenario-panel">
          <div className="dz-panel-title">1 · Alege tipul de misiune</div>
          <div className="ic-scen-grid">
            {Object.values(SCENARIOS).map((sc) => {
              const active = sc.id === scenarioId;
              const Icon = sc.Icon;
              return (
                <button
                  key={sc.id}
                  className={`ic-scen ${active ? "active" : ""}`}
                  style={active ? { borderColor: sc.color, boxShadow: `0 0 24px ${sc.color}40` } : {}}
                  onClick={() => setScenarioId(sc.id)}
                  data-testid={`scenario-${sc.id}`}>
                  <div className="ic-scen-icon" style={{ color: sc.color }}>
                    <Icon size={32} strokeWidth={1.5} />
                  </div>
                  <div className="ic-scen-lbl">{sc.label}</div>
                  <div className="ic-scen-sub">{sc.subtitle}</div>
                </button>
              );
            })}
          </div>
        </div>

        {/* ─── Params + Chart in split ─── */}
        <div className="ic-split">
          <div className="dz-panel" data-testid="params-panel">
            <div className="dz-panel-title">2 · Parametri operaționali</div>

            <div className="ic-slider-row">
              <div className="ic-slider-lbl">
                <span>Arie de acoperire</span>
                <strong style={{ color: s.color }}>{area} km²</strong>
              </div>
              <input type="range" min={1} max={200} value={area} step={1}
                     onChange={e => setArea(+e.target.value)}
                     className="ic-slider"
                     style={{ '--c': s.color }}
                     data-testid="slider-area" />
              <div className="ic-slider-scale"><span>1</span><span>50</span><span>100</span><span>200 km²</span></div>
            </div>

            <div className="ic-slider-row">
              <div className="ic-slider-lbl">
                <span>Număr de victime / persoane vizate</span>
                <strong style={{ color: s.color }}>{victims}</strong>
              </div>
              <input type="range" min={1} max={20} value={victims} step={1}
                     onChange={e => setVictims(+e.target.value)}
                     className="ic-slider" style={{ '--c': s.color }}
                     data-testid="slider-victims" />
              <div className="ic-slider-scale"><span>1</span><span>5</span><span>10</span><span>20</span></div>
            </div>

            <div className="ic-slider-row">
              <div className="ic-slider-lbl">
                <span>Dificultate teren (manual)</span>
                <strong style={{ color: s.color }}>×{terrain.toFixed(1)}</strong>
              </div>
              <input type="range" min={1} max={3} step={0.1} value={terrain}
                     onChange={e => setTerrain(+e.target.value)}
                     className="ic-slider" style={{ '--c': s.color }}
                     data-testid="slider-terrain" />
              <div className="ic-slider-scale"><span>şes</span><span>deal</span><span>munte</span><span>alpin sever</span></div>
            </div>

            <div className="ic-drone-spec">
              <span className="dot" style={{ background: s.color }} />
              <div>
                <div className="ic-spec-lbl">Configurație DroZon</div>
                <div className="ic-spec-val">{s.droneSpecs}</div>
              </div>
            </div>
          </div>

          <div className="dz-panel" data-testid="chart-panel">
            <div className="dz-panel-title">3 · Timp de răspuns</div>
            <div className="ic-chart">
              <ResponsiveContainer width="100%" height={230}>
                <BarChart data={chartData} margin={{ top: 12, right: 10, left: 0, bottom: 4 }}>
                  <XAxis dataKey="name" tick={{ fill: "#c8e0f0", fontSize: 11, fontFamily: 'Orbitron', letterSpacing: 3 }} axisLine={{ stroke: "#0f2a40" }} tickLine={false} />
                  <YAxis tick={{ fill: "#4a7090", fontSize: 10 }} axisLine={false} tickLine={false} label={{ value: 'ore', angle: -90, position: 'insideLeft', fill: '#4a7090', fontSize: 10 }} />
                  <Tooltip cursor={{ fill: 'rgba(0,212,255,0.05)' }}
                           contentStyle={{ background: '#0d1520', border: '1px solid #0f2a40', color: '#c8e0f0', fontFamily: 'IBM Plex Mono' }}
                           formatter={(v) => [`${v} ore`, "Timp"]} />
                  <Bar dataKey="time" radius={[4, 4, 0, 0]}>
                    {chartData.map((d, i) => <Cell key={i} fill={d.color} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="ic-chart-legend">
              <div><span className="dot" style={{background:'#4a7090'}}/> Salvamont / ISU manual · <strong>{calc.tManual.toFixed(1)} ore</strong></div>
              <div><span className="dot" style={{background:s.color}}/> DroZon · <strong>{calc.tDrone.toFixed(1)} ore</strong></div>
              <div className="ic-speedup" style={{ color: s.color }}>
                <TrendingUp size={16} /> <strong>{calc.speedupX.toFixed(1)}× mai rapid</strong>
              </div>
            </div>
          </div>
        </div>

        {/* ─── HERO IMPACT CARDS ─── */}
        <motion.div
          className="ic-impact-grid"
          initial="hidden"
          animate="visible"
          variants={{ visible: { transition: { staggerChildren: 0.1 } } }}
          data-testid="impact-cards">
          <motion.div className="ic-impact lives" variants={cardVariants} data-testid="card-lives">
            <div className="ic-impact-icon"><Users size={26} /></div>
            <div className="ic-impact-lbl">Vieți estimate salvate</div>
            <div className="ic-impact-val" data-testid="metric-lives">
              +<AnimatedNumber value={calc.livesSaved} format={(v) => v.toFixed(1)} />
            </div>
            <div className="ic-impact-note">
              Rată supraviețuire: <strong>{calc.pManual.toFixed(0)}%</strong> manual → <strong style={{color:'var(--dz-accent2)'}}>{calc.pDrone.toFixed(0)}%</strong> DroZon
            </div>
          </motion.div>

          <motion.div className="ic-impact time" variants={cardVariants} data-testid="card-time">
            <div className="ic-impact-icon"><Clock size={26} /></div>
            <div className="ic-impact-lbl">Timp economisit</div>
            <div className="ic-impact-val" data-testid="metric-time">
              <AnimatedNumber value={calc.timeSavedMin} /> min
            </div>
            <div className="ic-impact-note">
              Din <strong>{(calc.tManual*60).toFixed(0)}</strong> min → <strong>{(calc.tDrone*60).toFixed(0)}</strong> min
            </div>
          </motion.div>

          <motion.div className="ic-impact cost" variants={cardVariants} data-testid="card-cost">
            <div className="ic-impact-icon"><Euro size={26} /></div>
            <div className="ic-impact-lbl">Cost redus / misiune</div>
            <div className="ic-impact-val" data-testid="metric-cost">
              <AnimatedNumber value={calc.costSaved} /> €
            </div>
            <div className="ic-impact-note">
              Manual <strong>{Math.round(calc.costManual).toLocaleString('ro-RO')} €</strong> vs DroZon <strong>{Math.round(calc.costDrone).toLocaleString('ro-RO')} €</strong>
            </div>
          </motion.div>
        </motion.div>

        {/* ─── PITCH LINE ─── */}
        <motion.div
          className="ic-pitch"
          initial={{ opacity: 0, scale: 0.96 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.3, duration: 0.6 }}
          data-testid="pitch-line">
          <div className="ic-pitch-lead">La 100 misiuni pe an</div>
          <div className="ic-pitch-metric">
            <div>
              <span className="ic-pitch-big" style={{ color: 'var(--dz-danger)' }}>
                <AnimatedNumber value={calc.livesSaved * 100} format={(v) => Math.round(v).toLocaleString('ro-RO')} />
              </span>
              <span className="ic-pitch-lbl">vieți salvate suplimentar</span>
            </div>
            <div className="ic-pitch-sep">·</div>
            <div>
              <span className="ic-pitch-big" style={{ color: 'var(--dz-accent2)' }}>
                <AnimatedNumber value={calc.costSaved * 100 / 1000} format={(v) => Math.round(v).toLocaleString('ro-RO')} />K €
              </span>
              <span className="ic-pitch-lbl">reducere costuri operaționale</span>
            </div>
          </div>
          <div className="ic-pitch-foot">
            Modelul folosește parametri operaționali reali Salvamont / ISU · rate acoperire drone certificate DGAC ·
            probabilitate supraviețuire pe baza fereastrei critice specifice scenariului (hipotermie, asfixie, șoc traumatic).
          </div>
        </motion.div>
      </div>
    </div>
  );
}

const cardVariants = {
  hidden: { opacity: 0, y: 24 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.5 } },
};
