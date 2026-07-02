# DroZon — PRD & Progress Log

## Problem Statement (original)
> "Salut am o aplicatie DroZon care se vrea a fi dirijarea unei flote de drone pentru interventii umanitare. Vreau sa o dezvoltam si sa o fixam cat mai bine."

Aplicație complexă de tip dispatch pentru flote de drone în misiuni umanitare (incendii, avalanșe, inundații, seismic, salvare supraviețuitori, evacuare). Cod inițial primit ca arhivă `.rar` cu **5 aplicații HTML monolitice** (~600KB fiecare, vanilla JS + Leaflet) + backend TypeScript-Supabase scaffolding + firmware embedded.

## Architecture
- **Frontend principal**: `/app/frontend/public/drozon.html` (aplicație standalone vanilla JS, 10.8K linii, servită prin React redirect)
- **Redirect wrapper**: `/app/frontend/src/App.js` → `window.location.replace('/drozon.html')`
- **Backend Python/FastAPI**: nefolosit deocamdată (aplicația e client-only cu API-uri externe: open-meteo, Esri, OSM)
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
**Motivație**: harta principală era limitată (Leaflet zoom 19, container sizing bugs, debug elements vizibile pe pagină).

**Făcut**:
- ✅ Arhiva RAR primită de la user, extrasă, `index.html` copiată în `/app/frontend/public/drozon.html`
- ✅ React `App.js` transformat în redirect wrapper cu loader → `/drozon.html`
- ✅ Convertit line endings CRLF → LF pentru compatibilitate cu search_replace
- ✅ **Adăugat MapLibre GL JS 4.7.1** (CDN unpkg) lângă Leaflet (păstrat pentru hărțile secundare din modale)
- ✅ **Scris shim compatibil Leaflet-API** (`DroZonMLMap`) — permite ca `L.marker/L.circle/L.polyline/L.divIcon` existente să funcționeze fără să atingem restul codului (11K linii)
- ✅ Style MapLibre custom cu 4 surse raster: **Esri World Imagery** (sat), **CartoDB dark_all** (dark), **OpenTopoMap** (terrain), **Esri Boundaries and Places** (labels satelit)
- ✅ Eliminat debug elements (bar verde "innerH=... leafletH=...", cutia lime "MC AREA la y=260", outline-uri cyan/orange)
- ✅ Simplificat `fixMapHeight` — CSS flex face treaba, doar propagăm `resize()` la MapLibre
- ✅ `ResizeObserver` pe container pentru auto-adapt
- ✅ Adăugat butoane noi în meniul hartă: **⛰️ Teren** + **🎮 3D View** (pitch 55° / bearing -25°)
- ✅ CSS custom pentru MapLibre popups/controls în tema DroZon dark
- ✅ Queue de operații până la `map.on('load')` — evită "Style is not done loading"
- ✅ Expunere `window.map, window.toggleLayer, window.toggle3D, ...` pentru testare

**Rezultate confirmate prin screenshot**:
- Zoom 20 → mașini + drone vizibile pe pista (nivel sub-metru)
- Zoom 15 → blocuri, parcuri, "Cimitirul Izvorul Nou", "Sala Sport"
- 3D pitch 55° funcțional cu perspectivă tip Google Earth
- Toate 8 drone + zone + traiectorii + alerte SOS render corect
- 3 base layers switching funcțional (sat/dark/terrain)

**Fișiere modificate**:
- `/app/frontend/public/drozon.html` (~500 linii schimbate: shim MapLibre + CSS + butoane UI)
- `/app/frontend/src/App.js` (rewrite total: redirect wrapper)

**Fișiere adiacente create**:
- `/app/frontend/public/6c1282db-*.jpg` (asset original)
- `/app/frontend/public/.well-known/assetlinks.json`

## Backlog (P0 = următoarea sesiune)

### P0 · Fixuri UX rapide
- [ ] SOS alert popup apare automat prea repede la load — să nu se declanșeze pe demo până user nu apasă "🎬 DEMO"
- [ ] Overflow butoane în panoul dreapta la viewport-uri sub 900px — reduce padding sau fă grid 2×4
- [ ] Widget "METEO LIVE" bottom-left se suprapune cu scale control MapLibre — reposition

### P1 · Migrare completă la MapLibre
- [ ] Migrarea hărților secundare (Waypoint editor `WP.map`, Rescue `RSC.map`, Kamikaze `KMK.map`, Swarm `SW.map`) la MapLibre → un singur engine, mai puțin bundle
- [ ] Elimină dependința Leaflet complet dacă toate hărțile migrează

### P1 · Feature-uri hartă upgraded
- [ ] **NASA FIRMS** — hotspot-uri incendii live pe hartă (esențial pentru misiuni umanitare reale)
- [ ] **RainViewer radar** overlay — precipitații live
- [ ] **Rază autonomie 3D** — cilindru volumetric (nu doar cerc plat) pentru evidențierea altitudinii
- [ ] Traiectorie dronă cu **altitudine 3D** — line-gradient / extrusion după alt
- [ ] **Terrain 3D real** (via MapTiler DEM) — nu doar raster OpenTopoMap

### P2 · Backend real
- [ ] FastAPI backend: `/api/drones` CRUD, `/api/telemetry` WebSocket ingest, `/api/missions`, `/api/alerts`
- [ ] MongoDB models: `Drone`, `Mission`, `Alert`, `TelemetryPoint`, `FlightReport`
- [ ] Persistență drone (acum e hardcodat în JS)
- [ ] Autentificare (JWT sau Emergent Google OAuth) — decizie utilizator

### P2 · Integrări externe
- [ ] MAVLink parser pentru drone reale (backend WebSocket bridge)
- [ ] Twilio SMS pentru notificări SOS la operatori
- [ ] Telegram bot pentru alerte în teren
- [ ] Google Drive / Dropbox export automat rapoarte flight

### P2 · Consolidare variante HTML
- [ ] Merge `DroZon-PRO.html` + `drozon-kamikaze.html` + `drozon-rescue-FINAL.html` + `drone-schematic.html` într-o singură app cu tab-uri per modul

## Next Actions (immediate)
1. Așteptăm feedback user pe hartă (funcționează cum voia?)
2. La confirmare, atacăm P0 (fixuri UX rapide) sau trecem la P1 (feature-uri hartă)
