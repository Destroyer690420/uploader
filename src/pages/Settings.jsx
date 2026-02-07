import { useState, useEffect } from 'react'
import { Youtube, Instagram, Save, CheckCircle, AlertCircle, Eye, EyeOff, Loader2 } from 'lucide-react'
import { supabase, isSupabaseConfigured } from '../lib/supabase'
import AuthForm from '../components/AuthForm'

export default function Settings() {
    const [user, setUser] = useState(null)
    const [youtube, setYoutube] = useState({
        clientId: '',
        clientSecret: '',
        refreshToken: ''
    })

    const [instagram, setInstagram] = useState({
        accessToken: '',
        pageId: ''
    })

    const [showSecrets, setShowSecrets] = useState({
        ytSecret: false,
        ytRefresh: false,
        igToken: false
    })

    const [saving, setSaving] = useState({ youtube: false, instagram: false })
    const [status, setStatus] = useState({ youtube: null, instagram: null })

    useEffect(() => {
        if (user) loadCredentials()
    }, [user])

    const loadCredentials = async () => {
        if (!isSupabaseConfigured || !supabase) return

        try {
            const { data: { user } } = await supabase.auth.getUser()
            if (!user) return

            const { data } = await supabase
                .from('api_credentials')
                .select('*')
                .eq('user_id', user.id)

            data?.forEach(cred => {
                if (cred.platform === 'youtube') {
                    setYoutube({
                        clientId: cred.account_id || '',
                        clientSecret: '',
                        refreshToken: cred.refresh_token || ''
                    })
                } else if (cred.platform === 'instagram') {
                    setInstagram({
                        accessToken: cred.access_token || '',
                        pageId: cred.account_id || ''
                    })
                }
            })
        } catch (error) {
            console.error('Error loading credentials:', error)
        }
    }

    const saveYouTube = async () => {
        if (!isSupabaseConfigured || !supabase || !user) {
            setStatus(s => ({ ...s, youtube: 'error' }))
            return
        }
        setSaving(s => ({ ...s, youtube: true }))
        setStatus(s => ({ ...s, youtube: null }))

        try {

            const { error } = await supabase
                .from('api_credentials')
                .upsert({
                    user_id: user.id,
                    platform: 'youtube',
                    account_id: youtube.clientId,
                    refresh_token: youtube.refreshToken,
                    access_token: youtube.clientSecret
                }, { onConflict: 'user_id,platform' })

            if (error) throw error
            setStatus(s => ({ ...s, youtube: 'success' }))
        } catch (error) {
            console.error('Error saving YouTube credentials:', error)
            setStatus(s => ({ ...s, youtube: 'error' }))
        } finally {
            setSaving(s => ({ ...s, youtube: false }))
        }
    }

    const saveInstagram = async () => {
        if (!isSupabaseConfigured || !supabase || !user) {
            setStatus(s => ({ ...s, instagram: 'error' }))
            return
        }
        setSaving(s => ({ ...s, instagram: true }))
        setStatus(s => ({ ...s, instagram: null }))

        try {

            const { error } = await supabase
                .from('api_credentials')
                .upsert({
                    user_id: user.id,
                    platform: 'instagram',
                    access_token: instagram.accessToken,
                    account_id: instagram.pageId
                }, { onConflict: 'user_id,platform' })

            if (error) throw error
            setStatus(s => ({ ...s, instagram: 'success' }))
        } catch (error) {
            console.error('Error saving Instagram credentials:', error)
            setStatus(s => ({ ...s, instagram: 'error' }))
        } finally {
            setSaving(s => ({ ...s, instagram: false }))
        }
    }

    const InputField = ({ label, value, onChange, showToggle, toggleKey }) => (
        <div style={{ marginBottom: '16px' }}>
            <label style={{
                display: 'block',
                fontSize: '0.9rem',
                color: '#9ca3af',
                marginBottom: '8px'
            }}>
                {label}
            </label>
            <div style={{ position: 'relative' }}>
                <input
                    type={showToggle && !showSecrets[toggleKey] ? 'password' : 'text'}
                    value={value}
                    onChange={(e) => onChange(e.target.value)}
                    className="input-field"
                    placeholder={`Enter ${label.toLowerCase()}`}
                    style={{ paddingRight: showToggle ? '48px' : undefined }}
                />
                {showToggle && (
                    <button
                        type="button"
                        onClick={() => setShowSecrets(s => ({ ...s, [toggleKey]: !s[toggleKey] }))}
                        style={{
                            position: 'absolute',
                            right: '14px',
                            top: '50%',
                            transform: 'translateY(-50%)',
                            background: 'none',
                            border: 'none',
                            color: '#6b7280',
                            padding: '4px',
                            cursor: 'pointer'
                        }}
                    >
                        {showSecrets[toggleKey]
                            ? <EyeOff style={{ width: 20, height: 20 }} />
                            : <Eye style={{ width: 20, height: 20 }} />
                        }
                    </button>
                )}
            </div>
        </div>
    )

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '28px' }}>
            {/* Header */}
            <div>
                <h2 style={{ fontSize: '2rem', fontWeight: 700, marginBottom: '8px' }}>API Settings</h2>
                <p style={{ color: '#9ca3af' }}>Configure your YouTube and Instagram API credentials for automatic video publishing.</p>
            </div>

            {/* Auth Section */}
            {isSupabaseConfigured && (
                <div>
                    <h3 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '12px', color: '#d1d5db' }}>
                        🔐 Authentication
                    </h3>
                    <AuthForm onAuthChange={setUser} />
                </div>
            )}

            {/* Warning Banner */}
            {!isSupabaseConfigured && (
                <div className="warning-banner" style={{ display: 'flex', alignItems: 'flex-start', gap: '14px' }}>
                    <AlertCircle style={{ width: 22, height: 22, color: '#fbbf24', flexShrink: 0, marginTop: 2 }} />
                    <div>
                        <p style={{ fontWeight: 600, color: '#fcd34d', marginBottom: '6px' }}>Supabase Not Configured</p>
                        <p style={{ color: '#fde68a', opacity: 0.8, fontSize: '0.9rem' }}>
                            Create a <code>.env</code> file with your Supabase credentials:
                        </p>
                        <pre style={{
                            marginTop: '10px',
                            padding: '10px 14px',
                            background: 'rgba(0,0,0,0.25)',
                            borderRadius: '8px',
                            color: '#fde68a',
                            opacity: 0.7,
                            fontSize: '0.8rem'
                        }}>
                            VITE_SUPABASE_URL=your_url{'\n'}VITE_SUPABASE_ANON_KEY=your_key
                        </pre>
                    </div>
                </div>
            )}

            {/* Platform Cards Grid */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '24px' }}>
                {/* YouTube Card */}
                <div className="card">
                    <div style={{ display: 'flex', alignItems: 'center', gap: '14px', marginBottom: '24px' }}>
                        <div className="icon-box icon-box-md youtube-red">
                            <Youtube style={{ width: 26, height: 26 }} />
                        </div>
                        <div>
                            <h3 style={{ fontWeight: 600, fontSize: '1.15rem' }}>YouTube</h3>
                            <p style={{ color: '#6b7280', fontSize: '0.85rem' }}>YouTube Data API v3</p>
                        </div>
                    </div>

                    <div>
                        <InputField
                            label="Client ID"
                            value={youtube.clientId}
                            onChange={(v) => setYoutube(s => ({ ...s, clientId: v }))}
                        />
                        <InputField
                            label="Client Secret"
                            value={youtube.clientSecret}
                            onChange={(v) => setYoutube(s => ({ ...s, clientSecret: v }))}
                            showToggle
                            toggleKey="ytSecret"
                        />
                        <InputField
                            label="Refresh Token"
                            value={youtube.refreshToken}
                            onChange={(v) => setYoutube(s => ({ ...s, refreshToken: v }))}
                            showToggle
                            toggleKey="ytRefresh"
                        />
                    </div>

                    <button
                        onClick={saveYouTube}
                        disabled={saving.youtube || !isSupabaseConfigured}
                        style={{
                            width: '100%',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            gap: '10px',
                            background: 'linear-gradient(135deg, #dc2626, #b91c1c)',
                            color: 'white',
                            fontWeight: 600,
                            padding: '14px 20px',
                            borderRadius: '12px',
                            border: 'none',
                            marginTop: '8px',
                            opacity: saving.youtube || !isSupabaseConfigured ? 0.5 : 1,
                            cursor: saving.youtube || !isSupabaseConfigured ? 'not-allowed' : 'pointer'
                        }}
                    >
                        {saving.youtube ? (
                            <Loader2 style={{ width: 20, height: 20 }} className="animate-spin" />
                        ) : (
                            <Save style={{ width: 20, height: 20 }} />
                        )}
                        <span>{saving.youtube ? 'Saving...' : 'Save YouTube Credentials'}</span>
                    </button>

                    {status.youtube && (
                        <div style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px',
                            marginTop: '14px',
                            fontSize: '0.9rem',
                            color: status.youtube === 'success' ? '#4ade80' : '#f87171'
                        }}>
                            {status.youtube === 'success'
                                ? <CheckCircle style={{ width: 18, height: 18 }} />
                                : <AlertCircle style={{ width: 18, height: 18 }} />
                            }
                            <span>{status.youtube === 'success' ? 'Credentials saved successfully!' : 'Failed to save credentials'}</span>
                        </div>
                    )}
                </div>

                {/* Instagram Card */}
                <div className="card">
                    <div style={{ display: 'flex', alignItems: 'center', gap: '14px', marginBottom: '24px' }}>
                        <div className="icon-box icon-box-md instagram-gradient">
                            <Instagram style={{ width: 26, height: 26 }} />
                        </div>
                        <div>
                            <h3 style={{ fontWeight: 600, fontSize: '1.15rem' }}>Instagram</h3>
                            <p style={{ color: '#6b7280', fontSize: '0.85rem' }}>Instagram Graph API</p>
                        </div>
                    </div>

                    <div>
                        <InputField
                            label="Access Token"
                            value={instagram.accessToken}
                            onChange={(v) => setInstagram(s => ({ ...s, accessToken: v }))}
                            showToggle
                            toggleKey="igToken"
                        />
                        <InputField
                            label="Instagram Business Account ID"
                            value={instagram.pageId}
                            onChange={(v) => setInstagram(s => ({ ...s, pageId: v }))}
                        />
                    </div>

                    <button
                        onClick={saveInstagram}
                        disabled={saving.instagram || !isSupabaseConfigured}
                        style={{
                            width: '100%',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            gap: '10px',
                            background: 'linear-gradient(135deg, #a855f7, #ec4899)',
                            color: 'white',
                            fontWeight: 600,
                            padding: '14px 20px',
                            borderRadius: '12px',
                            border: 'none',
                            marginTop: '8px',
                            opacity: saving.instagram || !isSupabaseConfigured ? 0.5 : 1,
                            cursor: saving.instagram || !isSupabaseConfigured ? 'not-allowed' : 'pointer'
                        }}
                    >
                        {saving.instagram ? (
                            <Loader2 style={{ width: 20, height: 20 }} className="animate-spin" />
                        ) : (
                            <Save style={{ width: 20, height: 20 }} />
                        )}
                        <span>{saving.instagram ? 'Saving...' : 'Save Instagram Credentials'}</span>
                    </button>

                    {status.instagram && (
                        <div style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px',
                            marginTop: '14px',
                            fontSize: '0.9rem',
                            color: status.instagram === 'success' ? '#4ade80' : '#f87171'
                        }}>
                            {status.instagram === 'success'
                                ? <CheckCircle style={{ width: 18, height: 18 }} />
                                : <AlertCircle style={{ width: 18, height: 18 }} />
                            }
                            <span>{status.instagram === 'success' ? 'Credentials saved successfully!' : 'Failed to save credentials'}</span>
                        </div>
                    )}
                </div>
            </div>

            {/* Help Section */}
            <div className="card">
                <h3 style={{ fontSize: '1.15rem', fontWeight: 600, marginBottom: '20px' }}>
                    📘 How to Get Your API Credentials
                </h3>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '32px' }}>
                    <div>
                        <h4 style={{ fontWeight: 600, marginBottom: '12px', color: '#f5f5f7' }}>YouTube Data API v3</h4>
                        <ol style={{
                            listStyle: 'decimal',
                            paddingLeft: '20px',
                            color: '#9ca3af',
                            fontSize: '0.9rem',
                            lineHeight: 1.8
                        }}>
                            <li>Go to <a href="https://console.cloud.google.com" target="_blank" rel="noreferrer">Google Cloud Console</a></li>
                            <li>Create a new project or select existing</li>
                            <li>Enable YouTube Data API v3</li>
                            <li>Create OAuth 2.0 credentials</li>
                            <li>Use <a href="https://developers.google.com/oauthplayground" target="_blank" rel="noreferrer">OAuth Playground</a> to get refresh token</li>
                        </ol>
                    </div>
                    <div>
                        <h4 style={{ fontWeight: 600, marginBottom: '12px', color: '#f5f5f7' }}>Instagram Graph API</h4>
                        <ol style={{
                            listStyle: 'decimal',
                            paddingLeft: '20px',
                            color: '#9ca3af',
                            fontSize: '0.9rem',
                            lineHeight: 1.8
                        }}>
                            <li>Go to <a href="https://developers.facebook.com" target="_blank" rel="noreferrer">Meta for Developers</a></li>
                            <li>Create an app with Instagram Graph API</li>
                            <li>Connect your Instagram Business account</li>
                            <li>Generate a long-lived access token</li>
                            <li>Copy your Instagram Business Account ID</li>
                        </ol>
                    </div>
                </div>
            </div>
        </div>
    )
}
