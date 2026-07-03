# DroZon — Product Requirements Document

## Original problem statement (Ro)
Aplicație de comandă și control pentru drone de salvare, adresată instituțiilor românești (ISU, Salvamont). Utilizatorul pregătește o prezentare pentru investitori.

Prioritățile menționate:
- Ce funcționează bine acum (misiuni RESCUE, SWARM, waypoint, SOS, demo auto, meteo, hartă)
- Ce lipsește tehnic: conectivitate reală cu drona (DJI/MAVLink), streaming video, autentificare cu roluri stricte (Comandant / Pilot / Observator), mod offline

## Personas
- **Comandant Misiune** — decident, autorizează operațiuni, gestionează piloți/observatori, are acces total (ex: ofițer ISU / șef Salvamont).
- **Pilot Dronă** — execută misiuni, comandă drona, raportează telemetrie, lansează SOS.
- **Observator** — reprezentant instituțional care urmărește operațiunile în read-only (ex: reprezentanți autorități locale, presă, martori experți).

## Arhitectură
- **Frontend React** (`/app/frontend`) — shell de autentificare (login/register/dashboard/admin users) în stil tactic command center.
- **Aplicație tactică HTML** (`/app/frontend/public/drozon.html` — 11.000+ linii, Leaflet + vanilla JS) — hartă live, drone, misiuni RESCUE/SWARM, meteo, SOS, demo auto. Păstrată în forma originală, cu auth gate injectat.
- **Backend FastAPI + MongoDB** (`/app/backend/server.py`) — Auth JWT (httpOnly cookies), users, missions, telemetry, sos, drone-adapters.
- **Firmware/simulator** (`dronezone-firmware/`, `dronezone-backend/`) — cod C++/Python original DroZon-MAXIM, moștenit din repo.

## Implementat în Sprint 1 (Iulie 2026)
- ✅ Autentificare JWT + 3 roluri (Comandant / Pilot / Observator) cu ierarhii stricte
- ✅ Seed 3 conturi demo la startup (idempotent)
- ✅ Rate limiting brute-force (5 încercări → 15 min blocaj), tz-aware, X-Forwarded-For aware
- ✅ Register split în 2 flow-uri: self-signup observer (setează cookie), commander-only pilot/commander (NU rescrie sesiunea)
- ✅ Endpoints CRUD: /users (commander), /missions (commander+pilot), /telemetry, /sos, /drone-adapters
- ✅ React shell: Login (cu demo buttons), Dashboard (statistici, adaptoare, SOS panel), UserAdmin (CRUD users)
- ✅ Auth gate în drozon.html: verifică sesiunea, redirect la login dacă lipsă, injectează HUD sus-dreapta cu callsign + rol + Ieșire
- ✅ Observer read-only banner + role-gated CSS classes
- ✅ **ROI / Impact Calculator** — pagină dedicată pentru investitori (`/impact`):
  - 5 scenarii cu iconuri (SAR, avalanșă, incendiu, inundație, extracție medicală)
  - Slidere: arie km², nr. victime, dificultate teren
  - Comparație vizuală Manual (Salvamont/ISU) vs DroZon: timp răspuns, cost, rată supraviețuire
  - Chart bar animat (recharts) + carduri metrici animate (framer-motion)
  - Formula supraviețuire pe fereastră critică (t_critical exponential decay)
  - Pitch line "La 100 misiuni pe an" cu vieți salvate + € economisiți
- ✅ Backend: 30/30 pytest cases green
- ✅ Frontend: login + dashboard + user admin + drozon integration validated E2E

## Credențiale seedate
| Rol       | Email                | Parolă         | Callsign |
|-----------|----------------------|----------------|----------|
| commander | comandant@drozon.ro  | Comandant2026! | ACTUAL-6 |
| pilot     | pilot@drozon.ro      | Pilot2026!     | HAWK-1   |
| observer  | observer@drozon.ro   | Observer2026!  | EYE-1    |

## Backlog (Sprint 2)
- **P0** — Streaming video live (mock: WebRTC cu webcam sau video sample looping, per dronă)
- **P0** — Mod offline: service worker pentru drozon.html, IndexedDB pentru misiuni în așteptare, sync când revine internetul
- **P1** — Layer real drone integration: implementare concretă a adaptorului MAVLink (WebSocket bridge la mavproxy) și DJI Mobile SDK (companion mobile app)
- **P1** — Persistare telemetrie reală în MongoDB (acum in-memory în HTML)
- **P1** — Panel "Rapoarte de zbor" cu export PDF (după misiune)
- **P2** — Notificări push (SOS către comandanți)
- **P2** — Multi-language UI (EN pentru investitori străini)
- **P2** — Modularizare drozon.html (11k linii → componente)
- **P2** — Migrate FastAPI startup/shutdown la lifespan (deprecation)

## Note tehnice
- CORS setat la `*` cu `allow_credentials=True` — funcționează pentru same-origin preview. **Pentru producție**: setează origin explicit.
- Cookies `secure=False` acum. **Producție HTTPS**: `secure=True`.
- Auto-demo din drozon.html rulează 100% client-side; nu depinde de backend.
