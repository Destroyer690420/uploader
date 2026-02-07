import { createClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY

// Check if Supabase is configured
const isConfigured = supabaseUrl && supabaseAnonKey

if (!isConfigured) {
    console.warn('⚠️ Supabase not configured. Create a .env file with:')
    console.warn('VITE_SUPABASE_URL=your_supabase_url')
    console.warn('VITE_SUPABASE_ANON_KEY=your_supabase_anon_key')
}

// Create client with placeholder values if not configured (prevents crash)
export const supabase = isConfigured
    ? createClient(supabaseUrl, supabaseAnonKey)
    : null

export const isSupabaseConfigured = isConfigured
