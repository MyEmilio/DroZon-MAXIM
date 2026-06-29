// ═══════════════════════════════════════════════════════════
// API ROUTE — Telemetrie ingest (trimite date de pe dronă)
// app/api/telemetry/route.ts
// ═══════════════════════════════════════════════════════════

/*
import { supabaseAdmin } from '@/lib/supabase'
import type { NextRequest } from 'next/server'
import type { TelemetryPoint } from '@/types/dronezone'

// Drona trimite date la: POST /api/telemetry
// Header: Authorization: Bearer <DRONE_SECRET_KEY>
// Body: JSON cu TelemetryPoint

export async function POST(req: NextRequest) {
  // Autentificare dronă prin secret key
  const auth = req.headers.get('Authorization')
  if (auth !== `Bearer ${process.env.DRONE_SECRET_KEY}`) {
    return Response.json({ error: 'Unauthorized' }, { status: 401 })
  }

  const data: TelemetryPoint = await req.json()

  // Inserează telemetrie
  const { error } = await supabaseAdmin.from('telemetry').insert(data)
  if (error) return Response.json({ error: error.message }, { status: 500 })

  // Update starea dronei
  await supabaseAdmin.from('drones').update({
    battery_pct: data.battery_pct,
    battery_voltage: data.voltage,
    lat: data.lat,
    lon: data.lon,
    altitude_m: data.altitude_m,
    speed_ms: data.speed_ms,
    heading_deg: data.heading_deg,
    signal_pct: data.signal_pct,
    last_telemetry: new Date().toISOString(),
    status: 'flying',
    updated_at: new Date().toISOString(),
  }).eq('id', data.drone_id)

  return Response.json({ ok: true })
}
*/


// ═══════════════════════════════════════════════════════════
// PAGINA DE LOGIN — app/login/page.tsx
// ═══════════════════════════════════════════════════════════

'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/hooks/useAuth'

export default function LoginPage() {
  const { signIn, signUp } = useAuth()
  const router = useRouter()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // Login
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  // Register extra
  const [fullName, setFullName] = useState('')
  const [role, setRole] = useState<'owner' | 'relay' | 'observer'>('relay')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')

    if (mode === 'login') {
      const { error } = await signIn(email, password)
      if (error) { setError(error); setLoading(false); return }
    } else {
      const { error } = await signUp(email, password, fullName, role)
      if (error) { setError(error); setLoading(false); return }
    }

    router.push('/')
  }

  return (
    <div style={{
      minHeight: '100vh', background: '#040810',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontFamily: "'Rajdhani', sans-serif",
    }}>
      <div style={{
        width: 380, background: '#080d18',
        border: '1px solid #1c3060', padding: 32,
        position: 'relative',
      }}>
        {/* Accent line top */}
        <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 2,
          background: 'linear-gradient(90deg, transparent, #00c8ff, transparent)' }} />

        <div style={{ textAlign: 'center', marginBottom: 28 }}>
          <div style={{ fontFamily: 'Orbitron, sans-serif', fontSize: 22, fontWeight: 900,
            background: 'linear-gradient(90deg, #fff, #00c8ff)',
            WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
            letterSpacing: 3, marginBottom: 6 }}>
            DRONEZONE
          </div>
          <div style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 9,
            color: '#00c8ff', letterSpacing: 3 }}>
            {mode === 'login' ? 'AUTENTIFICARE PILOT' : 'ÎNREGISTRARE CONT'}
          </div>
        </div>

        {/* Mode toggle */}
        <div style={{ display: 'flex', marginBottom: 20, border: '1px solid #142038' }}>
          {(['login', 'register'] as const).map(m => (
            <button key={m} onClick={() => setMode(m)} style={{
              flex: 1, padding: '8px 0', background: mode === m ? 'rgba(0,200,255,0.1)' : 'none',
              border: 'none', borderBottom: mode === m ? '2px solid #00c8ff' : '2px solid transparent',
              color: mode === m ? '#00c8ff' : '#4a6a8a', cursor: 'pointer',
              fontFamily: 'Share Tech Mono, monospace', fontSize: 10, letterSpacing: 2,
            }}>
              {m === 'login' ? 'LOGIN' : 'ÎNREGISTRARE'}
            </button>
          ))}
        </div>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {mode === 'register' && (
            <>
              <InputField label="NUME COMPLET" value={fullName} onChange={setFullName} placeholder="Ion Popescu" />
              <div>
                <label style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 9,
                  color: '#4a6a8a', letterSpacing: 2, display: 'block', marginBottom: 5 }}>
                  ROL
                </label>
                <select value={role} onChange={e => setRole(e.target.value as any)} style={{
                  width: '100%', padding: '9px 12px', background: '#0b1220',
                  border: '1px solid #142038', color: '#00c8ff',
                  fontFamily: 'Share Tech Mono, monospace', fontSize: 11, outline: 'none',
                }}>
                  <option value="owner">👨‍✈️ OWNER — Control complet</option>
                  <option value="relay">🧑‍🚒 RELAY — Pilot de teren</option>
                  <option value="observer">👁️ OBSERVER — Vizualizare</option>
                </select>
              </div>
            </>
          )}
          <InputField label="EMAIL" type="email" value={email} onChange={setEmail} placeholder="pilot@dronezone.ro" />
          <InputField label="PAROLĂ" type="password" value={password} onChange={setPassword} placeholder="••••••••" />

          {error && (
            <div style={{ padding: '8px 12px', border: '1px solid #ff3535',
              background: 'rgba(255,53,53,0.06)', color: '#ff3535',
              fontFamily: 'Share Tech Mono, monospace', fontSize: 10 }}>
              ✗ {error}
            </div>
          )}

          <button type="submit" disabled={loading} style={{
            padding: '12px', marginTop: 4,
            background: loading ? 'none' : 'rgba(0,200,255,0.08)',
            border: '2px solid #00c8ff', color: '#00c8ff',
            fontFamily: 'Orbitron, sans-serif', fontSize: 11, fontWeight: 700,
            letterSpacing: 2, cursor: loading ? 'not-allowed' : 'pointer',
            opacity: loading ? 0.6 : 1,
          }}>
            {loading ? 'SE PROCESEAZĂ...' : mode === 'login' ? '→ AUTENTIFICARE' : '→ CREARE CONT'}
          </button>
        </form>

        {/* Role descriptions */}
        <div style={{ marginTop: 20, padding: '10px 12px', background: 'rgba(255,255,255,0.02)',
          border: '1px solid #142038', fontFamily: 'Share Tech Mono, monospace', fontSize: 9,
          color: '#3a5878', lineHeight: 1.8 }}>
          <span style={{ color: '#00c8ff' }}>OWNER</span> · Control full + transfer relay<br/>
          <span style={{ color: '#00ff9d' }}>RELAY</span> · Preia control de la owner<br/>
          <span style={{ color: '#4a6a8a' }}>OBSERVER</span> · Telemetrie read-only
        </div>
      </div>
    </div>
  )
}

function InputField({ label, type = 'text', value, onChange, placeholder }: {
  label: string; type?: string; value: string
  onChange: (v: string) => void; placeholder?: string
}) {
  return (
    <div>
      <label style={{ fontFamily: 'Share Tech Mono, monospace', fontSize: 9,
        color: '#4a6a8a', letterSpacing: 2, display: 'block', marginBottom: 5 }}>
        {label}
      </label>
      <input type={type} value={value} onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        required
        style={{
          width: '100%', padding: '9px 12px', background: '#0b1220',
          border: '1px solid #142038', color: '#e0f0ff',
          fontFamily: 'Rajdhani, sans-serif', fontSize: 14, outline: 'none',
          transition: 'border-color 0.2s',
        }}
        onFocus={e => { e.target.style.borderColor = '#00c8ff' }}
        onBlur={e => { e.target.style.borderColor = '#142038' }}
      />
    </div>
  )
}


// ═══════════════════════════════════════════════════════════
// MIDDLEWARE — Protejează rutele autentificate
// middleware.ts (rădăcina proiectului)
// ═══════════════════════════════════════════════════════════

/*
import { createMiddlewareClient } from '@supabase/auth-helpers-nextjs'
import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

export async function middleware(req: NextRequest) {
  const res = NextResponse.next()
  const supabase = createMiddlewareClient({ req, res })
  const { data: { session } } = await supabase.auth.getSession()

  // Rute publice
  const publicRoutes = ['/login', '/register', '/api/telemetry']
  const isPublic = publicRoutes.some(r => req.nextUrl.pathname.startsWith(r))

  if (!session && !isPublic) {
    return NextResponse.redirect(new URL('/login', req.url))
  }

  // Observer nu poate accesa pagini de control
  if (session) {
    const { data: profile } = await supabase.from('profiles')
      .select('role').eq('id', session.user.id).single()

    const controlRoutes = ['/relay', '/control']
    const isControlRoute = controlRoutes.some(r => req.nextUrl.pathname.startsWith(r))

    if (isControlRoute && profile?.role === 'observer') {
      return NextResponse.redirect(new URL('/?error=access_denied', req.url))
    }
  }

  return res
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico|icons|sw.js).*)'],
}
*/
