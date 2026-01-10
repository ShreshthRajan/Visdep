/**
 * Supabase client for frontend
 *
 * Handles:
 * - User authentication (GitHub OAuth)
 * - Session management
 * - User repository access
 */

import { createClient } from '@supabase/supabase-js'

const supabaseUrl = process.env.REACT_APP_SUPABASE_URL
const supabaseAnonKey = process.env.REACT_APP_SUPABASE_ANON_KEY

if (!supabaseUrl || !supabaseAnonKey) {
  const errorMsg = 'Missing Supabase environment variables. Required: REACT_APP_SUPABASE_URL and REACT_APP_SUPABASE_ANON_KEY'
  console.error('❌ ' + errorMsg)
  // Throw to fail fast with clear error instead of cryptic runtime failures
  throw new Error(errorMsg)
}

export const supabase = createClient(supabaseUrl, supabaseAnonKey, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true
  }
})

// Helper to get current user
export const getCurrentUser = async () => {
  const { data: { user }, error } = await supabase.auth.getUser()
  if (error) {
    console.error('Error getting user:', error)
    return null
  }
  return user
}

// Helper to sign out
export const signOut = async () => {
  const { error } = await supabase.auth.signOut()
  if (error) {
    console.error('Error signing out:', error)
  }
}
