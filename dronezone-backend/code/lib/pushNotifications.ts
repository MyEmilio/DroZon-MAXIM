// ═══════════════════════════════════════════════════════════
// PWA PUSH NOTIFICATIONS — DroneZone
// ═══════════════════════════════════════════════════════════
//
// SETUP:
// 1. Generează chei VAPID:
//    npx web-push generate-vapid-keys
//    → Pune în .env.local:
//      NEXT_PUBLIC_VAPID_PUBLIC_KEY=BPxxx...
//      VAPID_PRIVATE_KEY=xxx...
//      VAPID_EMAIL=mailto:admin@dronezone.ro
//
// 2. Instalează:
//    npm install web-push
//    npm install -D @types/web-push
//
// ═══════════════════════════════════════════════════════════


// ── public/sw.js (Service Worker — pune în /public/sw.js) ──
/*
self.addEventListener('push', (event) => {
  if (!event.data) return
  const data = event.data.json()

  const options = {
    body: data.body,
    icon: '/icons/drone-192.png',
    badge: '/icons/badge-72.png',
    vibrate: data.severity === 'critical' ? [200, 100, 200, 100, 200] : [200],
    data: data.data || {},
    actions: data.actions || [],
    requireInteraction: data.severity === 'critical',
    tag: data.tag || 'dronezone-notification',
    renotify: true,
  }

  event.waitUntil(
    self.registration.showNotification(data.title, options)
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const data = event.notification.data

  let url = '/'
  if (data.type === 'handoff_request') url = `/relay?handoff=${data.handoffId}`
  else if (data.type === 'alert') url = `/alerts?id=${data.alertId}`
  else if (data.droneId) url = `/drone/${data.droneId}`

  event.waitUntil(
    clients.matchAll({ type: 'window' }).then(clientList => {
      for (const client of clientList) {
        if (client.url === url && 'focus' in client) return client.focus()
      }
      if (clients.openWindow) return clients.openWindow(url)
    })
  )
})
*/


// ── lib/pushNotifications.ts ──────────────────────────────
import { supabase } from './supabase'

const VAPID_PUBLIC_KEY = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY!

// Convertește cheia VAPID din base64 în Uint8Array
function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = '='.repeat((4 - base64String.length % 4) % 4)
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
  const rawData = window.atob(base64)
  const outputArray = new Uint8Array(rawData.length)
  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i)
  }
  return outputArray
}

// Înregistrează Service Worker și obține subscripție push
export async function registerPushNotifications(userId: string): Promise<boolean> {
  try {
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
      console.warn('Push notifications nu sunt suportate în acest browser')
      return false
    }

    // Cere permisiune
    const permission = await Notification.requestPermission()
    if (permission !== 'granted') {
      console.warn('Permisiune push refuzată')
      return false
    }

    // Înregistrează Service Worker
    const registration = await navigator.serviceWorker.register('/sw.js')
    await navigator.serviceWorker.ready

    // Subscrie la push
    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY),
    })

    // Salvează subscripția în Supabase
    await supabase.from('profiles')
      .update({ push_token: JSON.stringify(subscription) })
      .eq('id', userId)

    console.log('✅ Push notifications activate')
    return true
  } catch (error) {
    console.error('Eroare la activarea push notifications:', error)
    return false
  }
}

// Trimite push notification (folosit local în browser)
export async function sendPushNotification(params: {
  title: string
  body: string
  severity?: 'info' | 'warning' | 'critical'
  data?: Record<string, string>
  actions?: Array<{ action: string; title: string }>
}) {
  // Dacă avem service worker activ, folosim direct Notification API ca fallback
  if ('Notification' in window && Notification.permission === 'granted') {
    if ('serviceWorker' in navigator) {
      const reg = await navigator.serviceWorker.getRegistration()
      if (reg) {
        await reg.showNotification(params.title, {
          body: params.body,
          icon: '/icons/drone-192.png',
          badge: '/icons/badge-72.png',
          vibrate: params.severity === 'critical' ? [300, 100, 300] : [200],
          data: params.data || {},
          requireInteraction: params.severity === 'critical',
        })
        return
      }
    }
    // Fallback simplu
    new Notification(params.title, { body: params.body, icon: '/icons/drone-192.png' })
  }
}


// ── api/push/send.ts (API Route — server side) ────────────
// pages/api/push/send.ts  SAU  app/api/push/send/route.ts

/*
import webpush from 'web-push'
import { supabaseAdmin } from '@/lib/supabase'
import type { NextRequest } from 'next/server'

webpush.setVapidDetails(
  process.env.VAPID_EMAIL!,
  process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY!,
  process.env.VAPID_PRIVATE_KEY!
)

export async function POST(req: NextRequest) {
  const { userIds, title, body, severity, data } = await req.json()

  // Obține subscripțiile utilizatorilor
  const { data: profiles } = await supabaseAdmin
    .from('profiles')
    .select('id, push_token')
    .in('id', userIds)
    .not('push_token', 'is', null)

  if (!profiles?.length) return Response.json({ sent: 0 })

  const payload = JSON.stringify({ title, body, severity, data })
  let sent = 0

  await Promise.allSettled(
    profiles.map(async (profile) => {
      try {
        const subscription = JSON.parse(profile.push_token!)
        await webpush.sendNotification(subscription, payload)
        sent++
      } catch (err: any) {
        // Subscripție expirată — șterge din DB
        if (err.statusCode === 410) {
          await supabaseAdmin.from('profiles')
            .update({ push_token: null })
            .eq('id', profile.id)
        }
      }
    })
  )

  return Response.json({ sent })
}
*/


// ── Utilizare în componente ───────────────────────────────
/*
// În layout.tsx sau pagina principală:
import { registerPushNotifications } from '@/lib/pushNotifications'
import { useAuth } from '@/hooks/useAuth'
import { useEffect } from 'react'

function PushSetup() {
  const { user } = useAuth()
  useEffect(() => {
    if (user) registerPushNotifications(user.id)
  }, [user])
  return null
}
*/
