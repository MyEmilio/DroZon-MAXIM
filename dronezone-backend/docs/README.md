# 🚁 DroneZone — Ghid Integrare Backend Complet

## Arhitectura aleasă: **Next.js + Supabase**

```
terenuri_app/
├── app/
│   ├── login/page.tsx          ← Autentificare
│   ├── page.tsx                ← Dashboard principal (harta + drone)
│   ├── relay/page.tsx          ← Pagina relay/handoff
│   ├── alerts/page.tsx         ← Alerte
│   └── api/
│       ├── telemetry/route.ts  ← Ingest date dronă
│       ├── push/send/route.ts  ← Trimite notificări push
│       └── reports/[id]/route.ts ← Generare rapoarte
├── lib/
│   ├── supabase.ts             ← Client Supabase
│   ├── pushNotifications.ts    ← PWA Push
│   └── flightReport.ts         ← Generator PDF
├── hooks/
│   ├── useAuth.ts              ← Auth + roluri
│   ├── useDrones.ts            ← Drone realtime
│   ├── useTelemetry.ts         ← Telemetrie live
│   ├── useHandoff.ts           ← Transfer control
│   └── useAlerts.ts            ← Alerte realtime
├── types/
│   └── dronezone.ts            ← Toate tipurile TS
├── public/
│   └── sw.js                   ← Service Worker PWA
└── middleware.ts               ← Protecție rute + roluri
```

---

## PASUL 1 — Creare proiect Supabase

1. Mergi la **https://supabase.com** → New Project
2. Alege un nume (ex: `dronezone`) și o parolă puternică
3. Selectează regiune **eu-central-1 (Frankfurt)** — cel mai aproape de România
4. Aștepți ~2 minute să pornească

---

## PASUL 2 — Rulează schema SQL

1. În Supabase Dashboard → **SQL Editor** → New Query
2. Copiază conținutul fișierului **`01_supabase_schema.sql`**
3. Click **Run** — va crea toate tabelele, politicile RLS și realtime

---

## PASUL 3 — Instalare pachete

```bash
cd terenuri_app

# Supabase
npm install @supabase/supabase-js @supabase/auth-helpers-nextjs

# PDF generator
npm install jspdf jspdf-autotable

# Push notifications (server-side)
npm install web-push
npm install -D @types/web-push

# Generare chei VAPID pentru push notifications
npx web-push generate-vapid-keys
# → Copiază cheile în .env.local (vezi mai jos)
```

---

## PASUL 4 — Variabile de mediu

Creează fișierul **`.env.local`** în rădăcina proiectului:

```env
# Supabase (le găsești în: Settings → API)
NEXT_PUBLIC_SUPABASE_URL=https://xxxxxxxxxxxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# Push Notifications VAPID (generate la Pasul 3)
NEXT_PUBLIC_VAPID_PUBLIC_KEY=BPxxxxxxxxxxxxxxxxxxxxxx...
VAPID_PRIVATE_KEY=xxxxxxxxxxxxxxxxxxxxxx...
VAPID_EMAIL=mailto:admin@dronezone.ro

# Secret pentru autentificare dronă fizică
DRONE_SECRET_KEY=dronezone_secret_2026_schimba_asta
```

---

## PASUL 5 — Copierea fișierelor

Copiază fișierele din pachetul livrat în proiectul tău:

```bash
# lib/
cp code/lib/supabase.ts          terenuri_app/lib/
cp code/lib/pushNotifications.ts terenuri_app/lib/
cp code/lib/flightReport.ts      terenuri_app/lib/

# types/
cp code/types/dronezone.ts       terenuri_app/types/

# hooks/ (desparte fișierul mare în fișiere separate)
# useAuth.ts, useDrones.ts, useTelemetry.ts, useHandoff.ts, useAlerts.ts

# API routes
# app/api/telemetry/route.ts
# app/api/push/send/route.ts

# Login page
# app/login/page.tsx

# Middleware
# middleware.ts (rădăcina proiectului)
```

---

## PASUL 6 — Service Worker pentru Push Notifications

Creează **`public/sw.js`** (copiază blocul comentat din `pushNotifications.ts`)

Adaugă în **`app/layout.tsx`**:
```tsx
// Înregistrare Service Worker la boot
useEffect(() => {
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js')
  }
}, [])
```

---

## PASUL 7 — Înlocuiește localStorage cu Supabase

În componentele existente din `terenuri_app`, înlocuiește:

```tsx
// ÎNAINTE (localStorage)
const drones = JSON.parse(localStorage.getItem('drones') || '[]')
localStorage.setItem('drones', JSON.stringify(drones))

// DUPĂ (Supabase)
import { useDrones } from '@/hooks/useDrones'
const { drones, loading } = useDrones()
// Datele se actualizează automat în realtime!
```

---

## PASUL 8 — Wrap app cu AuthProvider

În **`app/layout.tsx`**:
```tsx
import { AuthProvider } from '@/hooks/useAuth'

export default function RootLayout({ children }) {
  return (
    <html>
      <body>
        <AuthProvider>
          {children}
        </AuthProvider>
      </body>
    </html>
  )
}
```

---

## PASUL 9 — Activare Realtime în Supabase

Dashboard → **Database → Replication**:
- ✅ `drones`
- ✅ `telemetry`
- ✅ `handoffs`
- ✅ `alerts`

---

## PASUL 10 — Test final

```bash
npm run dev
```

1. Deschide `http://localhost:3000/login`
2. Creează cont cu rol **OWNER**
3. Deschide alt tab (incognito) → cont **RELAY**
4. Observă cum datele se sincronizează în realtime între tabs!

---

## Funcționalități activate după integrare

| Funcționalitate | Status | Detalii |
|---|---|---|
| 🔐 Autentificare | ✅ | Email/parolă, sesiuni persistente |
| 👥 Roluri | ✅ | OWNER / RELAY / OBSERVER |
| 📡 WebSocket Realtime | ✅ | Supabase Realtime |
| 🚁 Multi-dronă | ✅ | N drone simultane |
| 🔄 Sistem Relay | ✅ | Transfer securizat + timeout |
| 🔔 Push Notifications | ✅ | PWA, funcționează offline |
| 📊 Rapoarte PDF | ✅ | jsPDF, descărcare automată |
| 🗄️ Bază de date reală | ✅ | PostgreSQL (înlocuiește localStorage) |
| 🛡️ Protecție rute | ✅ | Middleware Next.js |
| 📱 Mobile ready | ✅ | PWA installable |

---

## Telemetrie de pe dronă fizică

Drona trimite date la:
```
POST https://dronezone.vercel.app/api/telemetry
Authorization: Bearer <DRONE_SECRET_KEY>
Content-Type: application/json

{
  "drone_id": "uuid-drona",
  "battery_pct": 78.5,
  "lat": 44.4268,
  "lon": 26.1025,
  "altitude_m": 87,
  "speed_ms": 12.3,
  "motor_rpm": {"m1": 4820, "m2": 4835},
  ...
}
```

---

## Deploy pe Vercel (gratuit)

```bash
npm install -g vercel
vercel --prod
# Adaugă variabilele din .env.local în Vercel Dashboard → Settings → Environment Variables
```

---

*DroneZone Backend Integration Guide — Rev 1.0 — 2026*
