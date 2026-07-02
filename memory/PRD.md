# DroZon — PRD & Progress Log

## Problem Statement (original)
> "Salut am o aplicatie DroZon care se vrea a fi dirijarea unei flote de drone pentru interventii umanitare. Vreau sa o dezvoltam si sa o fixam cat mai bine."

Aplicație complexă de tip dispatch pentru flote de drone în misiuni umanitare (incendii, avalanșe, inundații, seismic, salvare supraviețuitori, evacuare). Cod inițial primit ca arhivă `.rar` cu **5 aplicații HTML monolitice** (~600KB fiecare, vanilla JS + Leaflet) + backend TypeScript-Supabase scaffolding + firmware embedded.

## Architecture Actual
- **Frontend principal**: `/app/frontend/public/drozon.html` (~11K linii vanilla JS servit prin React redirect)
- **Redirect wrapper**: `/app/frontend/src/App.js` → `window.location.replace('/drozon.html')`
- **Backend FastAPI**: `/app/backend/server.py` — REST API pe `/api/*` cu MongoDB (`test_database`)
- **Endpoints active**:
  - `GET|POST /api/drones` — list & create
  - `GET|PUT|DELETE /api/drones/{id}` — read/update/delete
  - `POST /api/drones/bulk-seed` — seed inițial dacă DB gol (idempotent)
  - `GET|POST /api/missions` — misiuni
  - `PUT /api/missions/{id}` — update
  - `GET|POST /api/alerts` + `POST /api/alerts/{id}/ack`
  - `GET /api/stats` — dashboard live
- **Fișiere adiacente păstrate**: `/app/drozon_original/` conține variantele HTML alternative (PRO, kamikaze, rescue-FINAL, drone-schematic)

## User Personas
- **Coordonator flotă**: monitorizează live toate dronele, alocă misiuni, primește alerte SOS
- **Pilot dronă**: primește comenzi, navighează pe hartă, urmărește telemetrie proprie
- **Autorități umanitare (IGSU, 112)**: primesc rapoarte, generează NOTAM

## Core Requirements (static)
1. Hartă live cu poziții drone + zone autonomie + traiectorii
2. Fleet dashboard: status, baterie, tanc, meteo per dronă
3. Module misiuni: incendii, avalanșe, inundații, seismic, salvare, evacuare
4. Alerte SOS + integrare 112/IGSU + NOTAM
5. Simulator + rapoarte + export
6. PWA + push notifications + QR

## Session Log

### 2026-01 · Iterația 1 — Migrare Hartă la MapLibre GL
- ✅ Arhiva RAR extrasă, servită prin React redirect
- ✅ **Adăugat MapLibre GL JS 4.7.1** — zoom 22, pitch/bearing 3D, ResizeObserver
- ✅ **Shim compatibil Leaflet-API** (`DroZonMLMap`) — 11K linii cod existent rămân neatinse
- ✅ 4 base layers: Esri Satellite / CartoDB Dark / OpenTopoMap Terrain / Esri Labels
- ✅ Butoane noi: `⛰️ Teren`, `🎮 3D View`
- ✅ Eliminat debug elements (bar `innerH=...`, cutia lime "MC AREA", outline-uri cyan)
- ✅ Fixed `<div>` extra la linia 1974 → `.rp` sibling → dispărut "bandă neagră"

### 2026-01 · Iterația 2 — Backend + Live Data + UX
- ✅ **P0.1**: SOS monitoring & threat detection nu mai pornesc automat — doar în DEMO mode (`startDemo()` pornește `startSOSMonitoring()` + `startThreatDetection()`)
- ✅ **P0.2**: `.movl` reformat în grid 2×N cu backdrop-blur — 11 butoane compacte, nu se mai suprapun cu right panel
- ✅ **P1.2 RainViewer Radar**: buton `🌧️ Radar` — layer raster live cu precipitații ultimele 2h (fără API key, `api.rainviewer.com`)
- ✅ **P1.2 NASA EONET Fires**: buton `🔥 FIRMS` — 198 incendii forestiere active globale ca markere MapLibre pulsante (fără API key, `eonet.gsfc.nasa.gov`) + popup detalii + link sursă
- ✅ **P2 Backend**: FastAPI cu 12 endpoint-uri (`/api/drones`, `/api/missions`, `/api/alerts`, `/api/stats`) + MongoDB models (Drone, Mission, Alert)
- ✅ **P2 Frontend sync**: la load fetch `/api/drones`, dacă e gol → bulk-seed cu drone hardcodate; dacă are date → înlocuiește array local + toast "☁️ N drone sincronizate din MongoDB"
- ✅ **P2 addDrone persistență**: POST `/api/drones` fire-and-forget la crearea unei drone noi din UI

### Confirmări prin curl
```
POST /api/drones → 201 + drone JSON cu UUID
GET /api/drones → 8 drone (seedul funcționează)
PUT /api/drones/{id} → update battery/status funcționează
DELETE /api/drones/{id} → success
GET /api/stats → {"drones":{"total":8,"activ":2,"misiune":2,"standby":3,"pericol":1},...}
```

## Backlog Rămas

### P1 · Feature-uri hartă avansate
- [ ] Migrarea hărților secundare (Waypoint editor `WP.map`, Rescue `RSC.map`, Kamikaze `KMK.map`, Swarm `SW.map`) la MapLibre — funcționează în Leaflet acum, refactor amânat (risc vs. valoare)
- [ ] **Rază autonomie 3D** — cilindru volumetric (nu doar cerc plat)
- [ ] **Traiectorie 3D** cu altitudine reală — line-gradient / extrusion
- [ ] **MapTiler DEM terrain 3D real** (necesită API key)

### P2 · Backend extins
- [ ] Autentificare — JWT sau Emergent Google OAuth (necesită decizie utilizator)
- [ ] WebSocket telemetrie live (real-time drone position streaming)
- [ ] Persistență periodică (auto-sync PUT la fiecare N secunde pentru drone activate)
- [ ] Persistență DELETE la ștergere dronă din UI
- [ ] Endpoints rapoarte + export CSV

### P3 · Integrări externe (viitor)
- [ ] **MAVLink parser** pentru drone reale (backend WebSocket bridge)
- [ ] **Twilio SMS** pentru notificări SOS la operatori
- [ ] **Telegram bot** pentru alerte în teren
- [ ] **NASA FIRMS API key** (mai multe date decât EONET, VIIRS + MODIS 375m rezoluție)
- [ ] Consolidare variante HTML (`DroZon-PRO`, `kamikaze`, `rescue-FINAL`) într-o singură app cu tab-uri

### P3 · Growth / Monetizare
- [ ] Public read-only dashboard (`live.drozon.ro`) pentru vizibilitate publică misiuni umanitare
- [ ] Modul rapoarte PDF cu export → contracte guvernamentale

## Next Actions
1. Confirmă că totul funcționează după rescan
2. La approve → orice item din backlog P1/P2/P3
