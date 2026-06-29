// lib/supabase.ts
// ═══════════════════════════════════════════════════════════
// INSTALARE:
//   npm install @supabase/supabase-js
//   npm install @supabase/auth-helpers-nextjs
//
// .env.local:
//   NEXT_PUBLIC_SUPABASE_URL=https://xxxx.supabase.co
//   NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
//   SUPABASE_SERVICE_ROLE_KEY=eyJ...  (doar server-side!)
// ═══════════════════════════════════════════════════════════

import { createClient } from '@supabase/supabase-js'
import type { Database } from './database.types'

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!

// Client pentru browser (folosit în componente React)
export const supabase = createClient<Database>(supabaseUrl, supabaseAnonKey)

// Client cu service role (DOAR în API routes / server actions)
export const supabaseAdmin = createClient<Database>(
  supabaseUrl,
  process.env.SUPABASE_SERVICE_ROLE_KEY!
)
