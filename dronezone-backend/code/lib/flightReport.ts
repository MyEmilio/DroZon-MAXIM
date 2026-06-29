// lib/flightReport.ts
// ═══════════════════════════════════════════════════════════
// Generator rapoarte PDF zbor — DroneZone
//
// INSTALARE:
//   npm install jspdf jspdf-autotable
//   npm install -D @types/jspdf
// ═══════════════════════════════════════════════════════════

import jsPDF from 'jspdf'
import autoTable from 'jspdf-autotable'
import type { FlightSummary } from '@/types/dronezone'

const BRAND_COLOR: [number, number, number] = [0, 200, 255]   // --accent #00c8ff
const DARK_BG: [number, number, number]     = [5, 8, 15]
const TEXT_COLOR: [number, number, number]  = [200, 220, 240]
const GREEN: [number, number, number]       = [0, 255, 157]
const ORANGE: [number, number, number]      = [255, 107, 53]
const RED: [number, number, number]         = [255, 58, 58]
const YELLOW: [number, number, number]      = [255, 215, 0]

export async function generateFlightReport(summary: FlightSummary): Promise<void> {
  const doc = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' })
  const W = doc.internal.pageSize.getWidth()
  const H = doc.internal.pageSize.getHeight()

  // ── HEADER ──────────────────────────────────────────────
  // Fundal header
  doc.setFillColor(...DARK_BG)
  doc.rect(0, 0, W, 45, 'F')

  // Linie accent cyan
  doc.setFillColor(...BRAND_COLOR)
  doc.rect(0, 0, W, 2, 'F')

  // Logo / Titlu
  doc.setTextColor(...BRAND_COLOR)
  doc.setFontSize(22)
  doc.setFont('helvetica', 'bold')
  doc.text('DRONEZONE', 15, 18)

  doc.setFontSize(9)
  doc.setFont('helvetica', 'normal')
  doc.setTextColor(...TEXT_COLOR)
  doc.text('RAPORT ZBOR COMPLET', 15, 25)
  doc.text(`Generat: ${new Date().toLocaleString('ro-RO')}`, 15, 31)

  // Badge misiune
  const missionLabel = summary.mission.type.toUpperCase()
  doc.setFillColor(255, 107, 53)
  doc.roundedRect(W - 55, 10, 40, 12, 2, 2, 'F')
  doc.setTextColor(255, 255, 255)
  doc.setFontSize(8)
  doc.setFont('helvetica', 'bold')
  doc.text(missionLabel, W - 35, 18, { align: 'center' })

  // ── INFO DRONĂ + PILOT ───────────────────────────────────
  let y = 55

  doc.setTextColor(0, 200, 255)
  doc.setFontSize(11)
  doc.setFont('helvetica', 'bold')
  doc.text('INFORMAȚII ZBOR', 15, y)

  y += 6
  doc.setDrawColor(...BRAND_COLOR)
  doc.setLineWidth(0.3)
  doc.line(15, y, W - 15, y)
  y += 6

  const infoRows = [
    ['Dronă', summary.drone.name, 'Serial', summary.drone.serial],
    ['Pilot', summary.pilot.full_name, 'Rol', summary.pilot.role.toUpperCase()],
    ['Misiune', summary.mission.title || summary.mission.type, 'ID', summary.mission.id.slice(0,8)],
    ['Start', new Date(summary.mission.started_at).toLocaleString('ro-RO'),
     'End', summary.mission.ended_at ? new Date(summary.mission.ended_at).toLocaleString('ro-RO') : 'N/A'],
  ]

  doc.setFontSize(9)
  for (const row of infoRows) {
    doc.setFont('helvetica', 'bold')
    doc.setTextColor(150, 180, 210)
    doc.text(row[0] + ':', 15, y)
    doc.setFont('helvetica', 'normal')
    doc.setTextColor(230, 240, 255)
    doc.text(row[1], 45, y)

    doc.setFont('helvetica', 'bold')
    doc.setTextColor(150, 180, 210)
    doc.text(row[2] + ':', W/2 + 5, y)
    doc.setFont('helvetica', 'normal')
    doc.setTextColor(230, 240, 255)
    doc.text(row[3], W/2 + 30, y)
    y += 7
  }

  // ── STATISTICI PRINCIPALE ────────────────────────────────
  y += 5
  doc.setTextColor(0, 200, 255)
  doc.setFontSize(11)
  doc.setFont('helvetica', 'bold')
  doc.text('STATISTICI ZBOR', 15, y)
  y += 6
  doc.setLineWidth(0.3)
  doc.line(15, y, W - 15, y)
  y += 8

  const stats = summary.stats
  const duration = formatDuration(stats.flight_duration_sec)

  // Carduri statistici (2 rânduri × 3)
  const statCards = [
    { label: 'DISTANȚĂ TOTALĂ', value: stats.total_distance_km.toFixed(2) + ' km', color: GREEN },
    { label: 'ALTITUDINE MAX', value: stats.max_altitude_m.toFixed(0) + ' m', color: BRAND_COLOR },
    { label: 'DURATĂ ZBOR', value: duration, color: YELLOW },
    { label: 'VITEZĂ MEDIE', value: stats.avg_speed_ms.toFixed(1) + ' m/s', color: BRAND_COLOR },
    { label: 'BATERIE MIN', value: stats.min_battery_pct.toFixed(0) + '%', color: stats.min_battery_pct < 20 ? RED : ORANGE },
    { label: 'CONSUM mAh', value: stats.mah_consumed + ' mAh', color: ORANGE },
  ]

  const cardW = (W - 30) / 3
  const cardH = 20
  let cardX = 15

  for (let i = 0; i < statCards.length; i++) {
    if (i === 3) { cardX = 15; y += cardH + 5 }
    const card = statCards[i]
    const cx = cardX + (i % 3) * (cardW + 5)

    doc.setFillColor(10, 20, 40)
    doc.roundedRect(cx, y, cardW, cardH, 2, 2, 'F')
    doc.setDrawColor(...card.color)
    doc.setLineWidth(0.5)
    doc.roundedRect(cx, y, cardW, cardH, 2, 2, 'S')

    doc.setFontSize(7)
    doc.setFont('helvetica', 'normal')
    doc.setTextColor(100, 140, 170)
    doc.text(card.label, cx + 3, y + 6)

    doc.setFontSize(13)
    doc.setFont('helvetica', 'bold')
    doc.setTextColor(...card.color)
    doc.text(card.value, cx + 3, y + 16)
  }

  y += cardH + 10

  // Statistici extra
  const extraStats = [
    ['Transferuri relay', stats.handoffs_count.toString()],
    ['Waypoints completate', stats.waypoints_completed.toString()],
    ['Alerte generate', stats.alerts_count.toString()],
  ]
  doc.setFontSize(9)
  for (const [label, val] of extraStats) {
    doc.setFont('helvetica', 'normal')
    doc.setTextColor(150, 180, 210)
    doc.text(`${label}:`, 15, y)
    doc.setFont('helvetica', 'bold')
    doc.setTextColor(230, 240, 255)
    doc.text(val, 80, y)
    y += 6
  }

  // ── ALERTE ───────────────────────────────────────────────
  y += 5
  if (summary.alerts.length > 0) {
    doc.setTextColor(0, 200, 255)
    doc.setFontSize(11)
    doc.setFont('helvetica', 'bold')
    doc.text('ALERTE ȘI EVENIMENTE', 15, y)
    y += 4

    autoTable(doc, {
      startY: y,
      head: [['Timp', 'Severitate', 'Tip', 'Mesaj']],
      body: summary.alerts.slice(0, 15).map(a => [
        new Date(a.created_at).toLocaleTimeString('ro-RO'),
        a.severity.toUpperCase(),
        a.type.replace(/_/g, ' ').toUpperCase(),
        a.message,
      ]),
      theme: 'plain',
      headStyles: {
        fillColor: [10, 20, 40],
        textColor: [0, 200, 255],
        fontSize: 8,
        fontStyle: 'bold',
      },
      bodyStyles: { fontSize: 8, textColor: [200, 220, 240], fillColor: [5, 12, 25] },
      alternateRowStyles: { fillColor: [8, 18, 35] },
      columnStyles: {
        0: { cellWidth: 22 },
        1: { cellWidth: 22 },
        2: { cellWidth: 40 },
        3: { cellWidth: 'auto' },
      },
      didParseCell: (data) => {
        if (data.column.index === 1) {
          const sev = data.cell.raw as string
          if (sev.includes('CRITICAL')) data.cell.styles.textColor = [255, 58, 58]
          else if (sev.includes('WARNING')) data.cell.styles.textColor = [255, 215, 0]
          else data.cell.styles.textColor = [0, 200, 255]
        }
      },
      margin: { left: 15, right: 15 },
    })
    y = (doc as any).lastAutoTable.finalY + 8
  }

  // ── TRANSFERURI RELAY ────────────────────────────────────
  if (summary.handoffs.length > 0) {
    // Verifică dacă mai e loc pe pagina curentă
    if (y > H - 60) { doc.addPage(); y = 20 }

    doc.setTextColor(0, 200, 255)
    doc.setFontSize(11)
    doc.setFont('helvetica', 'bold')
    doc.text('TRANSFERURI CONTROL (RELAY)', 15, y)
    y += 4

    autoTable(doc, {
      startY: y,
      head: [['Timp', 'De la', 'Către', 'Status', 'Baterie', 'Alt.']],
      body: summary.handoffs.map(h => [
        new Date(h.initiated_at).toLocaleTimeString('ro-RO'),
        h.from_pilot?.full_name || h.from_pilot_id.slice(0,8),
        h.to_pilot?.full_name || h.to_pilot_id.slice(0,8),
        h.status.toUpperCase(),
        h.battery_at_handoff ? h.battery_at_handoff.toFixed(0) + '%' : '-',
        h.alt_at_handoff ? h.alt_at_handoff.toFixed(0) + 'm' : '-',
      ]),
      theme: 'plain',
      headStyles: { fillColor: [10, 20, 40], textColor: [0, 255, 157], fontSize: 8, fontStyle: 'bold' },
      bodyStyles: { fontSize: 8, textColor: [200, 220, 240], fillColor: [5, 12, 25] },
      alternateRowStyles: { fillColor: [8, 18, 35] },
      margin: { left: 15, right: 15 },
    })
    y = (doc as any).lastAutoTable.finalY + 8
  }

  // ── FOOTER ───────────────────────────────────────────────
  const pageCount = doc.getNumberOfPages()
  for (let i = 1; i <= pageCount; i++) {
    doc.setPage(i)
    doc.setFillColor(...DARK_BG)
    doc.rect(0, H - 12, W, 12, 'F')
    doc.setFillColor(...BRAND_COLOR)
    doc.rect(0, H - 12, W, 0.5, 'F')
    doc.setFontSize(7)
    doc.setFont('helvetica', 'normal')
    doc.setTextColor(80, 120, 160)
    doc.text('DRONEZONE © 2026 — Document confidențial', 15, H - 5)
    doc.text(`Pagina ${i} / ${pageCount}`, W - 15, H - 5, { align: 'right' })
  }

  // ── SALVEAZĂ PDF ─────────────────────────────────────────
  const filename = `DroneZone_Zbor_${summary.drone.serial}_${
    new Date(summary.mission.started_at).toISOString().slice(0,10)
  }.pdf`
  doc.save(filename)
}

// ── UTILITAR ─────────────────────────────────────────────
function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  if (h > 0) return `${h}h ${m}m ${s}s`
  if (m > 0) return `${m}m ${s}s`
  return `${s}s`
}


// ── API ROUTE pentru generare server-side ─────────────────
// app/api/reports/[missionId]/route.ts
/*
import { supabaseAdmin } from '@/lib/supabase'
import type { NextRequest } from 'next/server'

export async function GET(req: NextRequest, { params }: { params: { missionId: string } }) {
  const { data: mission } = await supabaseAdmin
    .from('missions')
    .select('*, drone:drones(*), pilot:profiles(*)')
    .eq('id', params.missionId)
    .single()

  if (!mission) return Response.json({ error: 'Mission not found' }, { status: 404 })

  // Obține datele pentru raport
  const [telemetry, alerts, handoffs] = await Promise.all([
    supabaseAdmin.from('telemetry').select('lat,lon,altitude_m,ts')
      .eq('drone_id', mission.drone_id)
      .gte('ts', mission.started_at)
      .lte('ts', mission.ended_at || new Date().toISOString())
      .order('ts'),
    supabaseAdmin.from('alerts').select('*, drone:drones(name)')
      .eq('drone_id', mission.drone_id)
      .gte('created_at', mission.started_at),
    supabaseAdmin.from('handoffs').select('*, from_pilot:profiles!from_pilot_id(*), to_pilot:profiles!to_pilot_id(*)')
      .eq('mission_id', params.missionId),
  ])

  const summary: FlightSummary = {
    mission,
    drone: mission.drone,
    pilot: mission.pilot,
    stats: {
      total_distance_km: mission.distance_km,
      max_altitude_m: mission.max_altitude || 0,
      avg_speed_ms: mission.avg_speed || 0,
      flight_duration_sec: mission.flight_sec,
      mah_consumed: mission.mah_consumed,
      min_battery_pct: 0, // calculat din telemetrie
      handoffs_count: handoffs.data?.length || 0,
      alerts_count: alerts.data?.length || 0,
      waypoints_completed: mission.waypoints?.length || 0,
    },
    telemetry_path: telemetry.data || [],
    alerts: alerts.data || [],
    handoffs: handoffs.data || [],
  }

  // Salvează în flight_logs
  await supabaseAdmin.from('flight_logs').insert({
    mission_id: params.missionId,
    drone_id: mission.drone_id,
    pilot_id: mission.pilot_id,
    summary,
  })

  return Response.json(summary)
}
*/
