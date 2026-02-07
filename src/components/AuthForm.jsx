import { useState, useEffect } from 'react'
import { Mail, Lock, LogIn, UserPlus, LogOut, Loader2 } from 'lucide-react'
import { supabase, isSupabaseConfigured } from '../lib/supabase'

export default function AuthForm({ onAuthChange }) {
    const [mode, setMode] = useState('login') // 'login' or 'signup'
    const [email, setEmail] = useState('')
    const [password, setPassword] = useState('')
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState(null)
    const [user, setUser] = useState(null)

    useEffect(() => {
        if (!isSupabaseConfigured || !supabase) return

        // Check current session
        supabase.auth.getUser().then(({ data: { user } }) => {
            setUser(user)
            onAuthChange?.(user)
        })

        // Listen for auth changes
        const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
            setUser(session?.user || null)
            onAuthChange?.(session?.user || null)
        })

        return () => subscription.unsubscribe()
    }, [onAuthChange])

    const handleSubmit = async (e) => {
        e.preventDefault()
        if (!isSupabaseConfigured || !supabase) return

        setLoading(true)
        setError(null)

        try {
            if (mode === 'signup') {
                const { error } = await supabase.auth.signUp({
                    email,
                    password
                })
                if (error) throw error
            } else {
                const { error } = await supabase.auth.signInWithPassword({
                    email,
                    password
                })
                if (error) throw error
            }
        } catch (err) {
            setError(err.message)
        } finally {
            setLoading(false)
        }
    }

    const handleSignOut = async () => {
        if (!supabase) return
        await supabase.auth.signOut()
    }

    if (!isSupabaseConfigured) return null

    // If logged in, show user info
    if (user) {
        return (
            <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '12px',
                padding: '10px 16px',
                background: 'rgba(34, 197, 94, 0.1)',
                border: '1px solid rgba(34, 197, 94, 0.2)',
                borderRadius: '10px'
            }}>
                <div style={{
                    width: '8px',
                    height: '8px',
                    borderRadius: '50%',
                    background: '#4ade80'
                }} />
                <span style={{ color: '#d1d5db', fontSize: '0.9rem', flex: 1 }}>
                    {user.email}
                </span>
                <button
                    onClick={handleSignOut}
                    style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                        padding: '6px 12px',
                        background: 'rgba(239, 68, 68, 0.15)',
                        border: '1px solid rgba(239, 68, 68, 0.3)',
                        borderRadius: '8px',
                        color: '#f87171',
                        fontSize: '0.85rem',
                        cursor: 'pointer'
                    }}
                >
                    <LogOut style={{ width: 14, height: 14 }} />
                    Sign Out
                </button>
            </div>
        )
    }

    // Login/Signup form
    return (
        <div className="card" style={{ maxWidth: '400px' }}>
            <h3 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '16px' }}>
                {mode === 'login' ? 'Sign In' : 'Create Account'}
            </h3>

            <form onSubmit={handleSubmit}>
                <div style={{ marginBottom: '14px' }}>
                    <label style={{
                        display: 'block',
                        fontSize: '0.85rem',
                        color: '#9ca3af',
                        marginBottom: '6px'
                    }}>
                        Email
                    </label>
                    <div style={{ position: 'relative' }}>
                        <Mail style={{
                            position: 'absolute',
                            left: '14px',
                            top: '50%',
                            transform: 'translateY(-50%)',
                            width: 18,
                            height: 18,
                            color: '#6b7280'
                        }} />
                        <input
                            type="email"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            className="input-field"
                            placeholder="your@email.com"
                            style={{ paddingLeft: '44px' }}
                            required
                        />
                    </div>
                </div>

                <div style={{ marginBottom: '18px' }}>
                    <label style={{
                        display: 'block',
                        fontSize: '0.85rem',
                        color: '#9ca3af',
                        marginBottom: '6px'
                    }}>
                        Password
                    </label>
                    <div style={{ position: 'relative' }}>
                        <Lock style={{
                            position: 'absolute',
                            left: '14px',
                            top: '50%',
                            transform: 'translateY(-50%)',
                            width: 18,
                            height: 18,
                            color: '#6b7280'
                        }} />
                        <input
                            type="password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            className="input-field"
                            placeholder="••••••••"
                            style={{ paddingLeft: '44px' }}
                            required
                            minLength={6}
                        />
                    </div>
                </div>

                {error && (
                    <div style={{
                        padding: '10px 14px',
                        background: 'rgba(239, 68, 68, 0.1)',
                        border: '1px solid rgba(239, 68, 68, 0.2)',
                        borderRadius: '8px',
                        color: '#f87171',
                        fontSize: '0.85rem',
                        marginBottom: '14px'
                    }}>
                        {error}
                    </div>
                )}

                <button
                    type="submit"
                    disabled={loading}
                    className="btn-primary"
                    style={{
                        width: '100%',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: '8px'
                    }}
                >
                    {loading ? (
                        <Loader2 style={{ width: 18, height: 18 }} className="animate-spin" />
                    ) : mode === 'login' ? (
                        <LogIn style={{ width: 18, height: 18 }} />
                    ) : (
                        <UserPlus style={{ width: 18, height: 18 }} />
                    )}
                    {loading ? 'Please wait...' : mode === 'login' ? 'Sign In' : 'Sign Up'}
                </button>
            </form>

            <div style={{ marginTop: '16px', textAlign: 'center' }}>
                <button
                    onClick={() => setMode(mode === 'login' ? 'signup' : 'login')}
                    style={{
                        background: 'none',
                        border: 'none',
                        color: '#818cf8',
                        fontSize: '0.9rem',
                        cursor: 'pointer'
                    }}
                >
                    {mode === 'login' ? "Don't have an account? Sign Up" : 'Already have an account? Sign In'}
                </button>
            </div>
        </div>
    )
}
