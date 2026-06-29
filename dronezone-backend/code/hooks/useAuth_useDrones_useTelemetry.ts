// hooks/useAuth.ts
// ═══════════════════════════════════════════════════════════
// Hook pentru autentificare și gestionare roluri
// ═══════════════════════════════════════════════════════════

'use client'

import { useEffect, useState, createContext, useContext } from 'react'
import { supabase } from '@/lib/supabase'
import type { User } from '@supabase/supabase-js'
import type { Profile, UserRole } from '@/types/dronezone'

interface AuthContextType {
  user: User | null
  profile: Profile | null
  role: UserRole | null
  loading: boolean
  signIn: (email: string, password: string) => Promise<{ error: string | null }>
  signUp: (email: string, password: string, fullName: string, role: UserRole) => Promise<{ error: string | null }>
  signOut: () => Promise<void>
  isOwner: boolean
  isRelay: boolean
  isObserver: boolean
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [profile, setProfile] = useState<Profile | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Verifică sesiunea curentă
    supabase.auth.getSession().then(({ data: { session } }) => {
      setUser(session?.user ?? null)
      if (session?.user) fetchProfile(session.user.id)
      else setLoading(false)
    })

    // Ascultă schimbările de auth
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      setUser(session?.user ?? null)
      if (session?.user) {
        fetchProfile(session.user.id)
        // Marchează utilizatorul ca online
        supabase.from('profiles').update({ is_online: true, last_seen: new Date().toISOString() })
          .eq('id', session.user.id)
      } else {
        setProfile(null)
        setLoading(false)
      }
    })

    // Marchează offline la închidere browser
    window.addEventListener('beforeunload', markOffline)
    return () => {
      subscription.unsubscribe()
      window.removeEventListener('beforeunload', markOffline)
    }
  }, [])

  const fetchProfile = async (userId: string) => {
    const { data, error } = await supabase
      .from('profiles')
      .select('*')
      .eq('id', userId)
      .single()
    if (!error && data) setProfile(data as Profile)
    setLoading(false)
  }

  const markOffline = async () => {
    if (user) {
      await supabase.from('profiles')
        .update({ is_online: false, last_seen: new Date().toISOString() })
        .eq('id', user.id)
    }
  }

  const signIn = async (email: string, password: string) => {
    const { error } = await supabase.auth.signInWithPassword({ email, password })
    return { error: error?.message ?? null }
  }

  const signUp = async (email: string, password: string, fullName: string, role: UserRole) => {
    const { error } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: { full_name: fullName, role }
      }
    })
    return { error: error?.message ?? null }
  }

  const signOut = async () => {
    await markOffline()
    await supabase.auth.signOut()
  }

  const role = profile?.role ?? null

  return (
    <AuthContext.Provider value={{
      user, profile, role, loading, signIn, signUp, signOut,
      isOwner: role === 'owner',
      isRelay: role === 'relay',
      isObserver: role === 'observer',
    }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth trebuie folosit în AuthProvider')
  return ctx
}


// ════════════════════════════════════════════════════════════
// hooks/useDrones.ts — Hook pentru drone în timp real
// ════════════════════════════════════════════════════════════

import { useEffect, useState, useCallback } from 'react'
import type { Drone } from '@/types/dronezone'

export function useDrones() {
  const [drones, setDrones] = useState<Drone[]>([])
  const [loading, setLoading] = useState(true)

  const fetchDrones = useCallback(async () => {
    const { data, error } = await supabase
      .from('drones')
      .select(`
        *,
        owner:profiles!drones_owner_id_fkey(id, full_name, avatar_url),
        pilot:profiles!drones_current_pilot_fkey(id, full_name, avatar_url, is_online)
      `)
      .order('name')
    if (!error && data) setDrones(data as Drone[])
    setLoading(false)
  }, [])

  useEffect(() => {
    fetchDrones()

    // Subscrie la update-uri realtime pentru toate dronele
    const channel = supabase
      .channel('drones_realtime')
      .on('postgres_changes', {
        event: '*',
        schema: 'public',
        table: 'drones',
      }, (payload) => {
        if (payload.eventType === 'UPDATE') {
          setDrones(prev => prev.map(d =>
            d.id === payload.new.id ? { ...d, ...payload.new } : d
          ))
        } else if (payload.eventType === 'INSERT') {
          fetchDrones() // Re-fetch cu join-uri
        } else if (payload.eventType === 'DELETE') {
          setDrones(prev => prev.filter(d => d.id !== payload.old.id))
        }
      })
      .subscribe()

    return () => { supabase.removeChannel(channel) }
  }, [fetchDrones])

  return { drones, loading, refetch: fetchDrones }
}


// ════════════════════════════════════════════════════════════
// hooks/useTelemetry.ts — Telemetrie live pentru o dronă
// ════════════════════════════════════════════════════════════

import type { TelemetryPoint } from '@/types/dronezone'

export function useTelemetry(droneId: string | null) {
  const [latest, setLatest] = useState<TelemetryPoint | null>(null)
  const [history, setHistory] = useState<TelemetryPoint[]>([])

  useEffect(() => {
    if (!droneId) return

    // Încarcă ultimele 50 puncte
    supabase
      .from('telemetry')
      .select('*')
      .eq('drone_id', droneId)
      .order('ts', { ascending: false })
      .limit(50)
      .then(({ data }) => {
        if (data) {
          setHistory(data.reverse() as TelemetryPoint[])
          setLatest(data[0] as TelemetryPoint)
        }
      })

    // Subscrie la telemetrie nouă în timp real
    const channel = supabase
      .channel(`telemetry_${droneId}`)
      .on('postgres_changes', {
        event: 'INSERT',
        schema: 'public',
        table: 'telemetry',
        filter: `drone_id=eq.${droneId}`,
      }, (payload) => {
        const point = payload.new as TelemetryPoint
        setLatest(point)
        setHistory(prev => [...prev.slice(-199), point])

        // Verifică praguri pentru alerte automate
        checkThresholds(point, droneId)
      })
      .subscribe()

    return () => { supabase.removeChannel(channel) }
  }, [droneId])

  return { latest, history }
}

// Verificare praguri și creare alerte automate
async function checkThresholds(t: TelemetryPoint, droneId: string) {
  const alerts = []

  if (t.battery_pct !== undefined) {
    if (t.battery_pct < 15) {
      alerts.push({ drone_id: droneId, severity: 'critical', type: 'battery_critical',
        message: `Baterie critică: ${t.battery_pct.toFixed(0)}% — RTH imediat!`,
        data: { battery_pct: t.battery_pct }
      })
    } else if (t.battery_pct < 30) {
      alerts.push({ drone_id: droneId, severity: 'warning', type: 'battery_low',
        message: `Baterie scăzută: ${t.battery_pct.toFixed(0)}%`,
        data: { battery_pct: t.battery_pct }
      })
    }
  }

  if (t.signal_pct !== undefined && t.signal_pct < 40) {
    alerts.push({ drone_id: droneId, severity: 'warning', type: 'signal_weak',
      message: `Semnal slab: ${t.signal_pct.toFixed(0)}%`,
      data: { signal_pct: t.signal_pct }
    })
  }

  // Verifică motoare — fault dacă curent > 18A pe un motor
  if (t.motor_amp) {
    for (const [motor, amp] of Object.entries(t.motor_amp)) {
      if (amp > 18) {
        alerts.push({ drone_id: droneId, severity: 'critical', type: 'motor_fault',
          message: `Avarie motor ${motor}: ${amp}A (suprasarcină)`,
          data: { motor, amp }
        })
      }
    }
  }

  if (alerts.length > 0) {
    await supabase.from('alerts').insert(alerts)
  }
}


// ════════════════════════════════════════════════════════════
// hooks/useHandoff.ts — Sistem relay / transfer control
// ════════════════════════════════════════════════════════════

import type { Handoff } from '@/types/dronezone'

export function useHandoff(userId: string | null) {
  const [pendingHandoff, setPendingHandoff] = useState<Handoff | null>(null)

  useEffect(() => {
    if (!userId) return

    // Subscrie la cereri de handoff destinate acestui pilot
    const channel = supabase
      .channel(`handoff_${userId}`)
      .on('postgres_changes', {
        event: 'INSERT',
        schema: 'public',
        table: 'handoffs',
        filter: `to_pilot_id=eq.${userId}`,
      }, (payload) => {
        const handoff = payload.new as Handoff
        if (handoff.status === 'pending') {
          setPendingHandoff(handoff)
          // Trimite push notification
          sendPushNotification({
            title: '🚁 Cerere Transfer Control',
            body: `O dronă îți este transferată. Acceptă în 15 secunde.`,
            data: { handoffId: handoff.id, type: 'handoff_request' }
          })
        }
      })
      .subscribe()

    return () => { supabase.removeChannel(channel) }
  }, [userId])

  const initiateHandoff = async (params: {
    droneId: string
    toPilotId: string
    missionId?: string
    droneState: { battery_pct: number; altitude_m: number; lat: number; lon: number }
  }) => {
    const { data, error } = await supabase
      .from('handoffs')
      .insert({
        drone_id: params.droneId,
        to_pilot_id: params.toPilotId,
        mission_id: params.missionId,
        from_pilot_id: userId,
        status: 'pending',
        battery_at_handoff: params.droneState.battery_pct,
        alt_at_handoff: params.droneState.altitude_m,
        lat_at_handoff: params.droneState.lat,
        lon_at_handoff: params.droneState.lon,
      })
      .select()
      .single()

    return { handoff: data as Handoff, error }
  }

  const respondToHandoff = async (handoffId: string, accepted: boolean, reason?: string) => {
    const update: Partial<Handoff> = {
      status: accepted ? 'accepted' : 'declined',
      responded_at: new Date().toISOString(),
      ...(reason && { declined_reason: reason })
    }

    const { error } = await supabase.from('handoffs').update(update).eq('id', handoffId)

    if (!error && accepted) {
      // Transferă controlul în tabelul drones
      const handoff = pendingHandoff
      if (handoff) {
        await supabase.from('drones')
          .update({ current_pilot: userId })
          .eq('id', handoff.drone_id)

        await supabase.from('handoffs')
          .update({ status: 'completed', completed_at: new Date().toISOString() })
          .eq('id', handoffId)
      }
    }

    setPendingHandoff(null)
    return { error }
  }

  return { pendingHandoff, initiateHandoff, respondToHandoff }
}


// ════════════════════════════════════════════════════════════
// hooks/useAlerts.ts — Alerte în timp real
// ════════════════════════════════════════════════════════════

import type { Alert } from '@/types/dronezone'

export function useAlerts(droneId?: string) {
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [unreadCount, setUnreadCount] = useState(0)

  useEffect(() => {
    // Încarcă alerte recente
    const query = supabase
      .from('alerts')
      .select('*')
      .order('created_at', { ascending: false })
      .limit(50)

    if (droneId) query.eq('drone_id', droneId)

    query.then(({ data }) => {
      if (data) {
        setAlerts(data as Alert[])
        setUnreadCount(data.filter(a => !a.acknowledged).length)
      }
    })

    // Subscrie la alerte noi în realtime
    const filter = droneId ? `drone_id=eq.${droneId}` : undefined
    const channel = supabase
      .channel('alerts_realtime')
      .on('postgres_changes', {
        event: 'INSERT',
        schema: 'public',
        table: 'alerts',
        ...(filter && { filter }),
      }, (payload) => {
        const alert = payload.new as Alert
        setAlerts(prev => [alert, ...prev.slice(0, 49)])
        setUnreadCount(c => c + 1)

        // Push notification pentru alerte critice
        if (alert.severity === 'critical') {
          sendPushNotification({
            title: `🚨 ALERTĂ CRITICĂ — ${alert.type.replace(/_/g, ' ').toUpperCase()}`,
            body: alert.message,
            data: { alertId: alert.id, droneId: alert.drone_id }
          })
        }
      })
      .subscribe()

    return () => { supabase.removeChannel(channel) }
  }, [droneId])

  const acknowledgeAlert = async (alertId: string, userId: string) => {
    await supabase.from('alerts')
      .update({ acknowledged: true, ack_by: userId, ack_at: new Date().toISOString() })
      .eq('id', alertId)
    setAlerts(prev => prev.map(a => a.id === alertId ? { ...a, acknowledged: true } : a))
    setUnreadCount(c => Math.max(0, c - 1))
  }

  return { alerts, unreadCount, acknowledgeAlert }
}
