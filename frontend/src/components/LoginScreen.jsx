import { useState } from 'react'

const API = import.meta.env.VITE_API_URL || ''

const DEMO_ACCOUNTS = [
  {
    username: 'doctor',
    password: 'doctorpassword123',
    name: 'Dr. Amadi Eze',
    role: 'doctor',
    roleLabel: 'Physician',
    icon: '🩺',
    color: 'var(--accent)',
    colorLight: 'var(--accent-light)',
    colorBorder: 'var(--accent-border)',
    desc: 'Full access — consult, prescribe, commit to EHR',
  },
  {
    username: 'nurse',
    password: 'nursepassword123',
    name: 'Nurse Jane Obi',
    role: 'nurse',
    roleLabel: 'Nurse',
    icon: '💊',
    color: '#8B5CF6',
    colorLight: 'rgba(139,92,246,0.08)',
    colorBorder: 'rgba(139,92,246,0.25)',
    desc: 'View & log vitals. Prescriptions/sign-off restricted.',
  },
  {
    username: 'admin',
    password: 'adminpassword123',
    name: 'System Administrator',
    role: 'admin',
    roleLabel: 'Admin',
    icon: '🛡️',
    color: '#F59E0B',
    colorLight: 'rgba(245,158,11,0.08)',
    colorBorder: 'rgba(245,158,11,0.25)',
    desc: 'Audit logs, settings, and full read access.',
  },
]

export default function LoginScreen({ onLogin }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError]       = useState('')
  const [loading, setLoading]   = useState(false)
  const [showPw, setShowPw]     = useState(false)

  const doLogin = async (u, p) => {
    setLoading(true)
    setError('')
    try {
      const res = await fetch(`${API}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: u, password: p }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Login failed')
      localStorage.setItem('klinik_token', data.access_token)
      localStorage.setItem('klinik_user', JSON.stringify(data.user))
      onLogin(data.user, data.access_token)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!username || !password) { setError('Please enter username and password.'); return }
    doLogin(username, password)
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 9998,
      background: 'var(--bg-base)',
      display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
      overflowY: 'auto',
      padding: '20px',
      animation: 'splash-in 0.4s ease-out both',
    }}>
      {/* Ambient glow */}
      <div style={{
        position: 'fixed', top: '-20%', left: '50%', transform: 'translateX(-50%)',
        width: 600, height: 600, borderRadius: '50%',
        background: 'radial-gradient(circle, var(--accent-glow) 0%, transparent 70%)',
        pointerEvents: 'none', zIndex: 0,
      }}/>

      <div style={{ width: '100%', maxWidth: 440, position: 'relative', zIndex: 1, margin: 'auto' }}>

        {/* Logo */}
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <div style={{
            width: 72, height: 72, borderRadius: 22, margin: '0 auto 16px',
            background: 'var(--accent-light)', border: '2px solid var(--accent-border)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: '0 0 40px var(--accent-glow)',
          }}>
            <svg viewBox="0 0 32 32" fill="none" width="38" height="38">
              <rect x="2" y="2" width="28" height="28" rx="10" fill="var(--accent-light)" stroke="var(--accent)" strokeWidth="2"/>
              <path d="M7 16 H12 L14 10 L18 22 L20 16 H25" stroke="var(--accent)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
              <circle cx="16" cy="16" r="2" fill="white"/>
            </svg>
          </div>
          <div style={{
            fontSize: 28, fontWeight: 900, letterSpacing: '0.18em',
            background: 'linear-gradient(135deg, var(--text-primary) 30%, var(--accent) 100%)',
            WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
          }}>KLINIK</div>
          <div style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 4 }}>
            AI-Powered Clinical Workflow
          </div>
        </div>

        {/* Login Card */}
        <div style={{
          background: 'var(--bg-card)', border: '1px solid var(--border)',
          borderRadius: 24, padding: 28, boxShadow: 'var(--shadow-raised)',
          marginBottom: 20,
        }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 18 }}>
            Sign in to your account
          </div>

          <form onSubmit={handleSubmit}>
            <div style={{ marginBottom: 12 }}>
              <label style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)', display: 'block', marginBottom: 6 }}>
                Username
              </label>
              <input
                id="login-username"
                type="text"
                value={username}
                onChange={e => setUsername(e.target.value)}
                placeholder="e.g. doctor"
                autoComplete="username"
                style={{
                  width: '100%', padding: '11px 14px',
                  background: 'var(--bg-input)', border: '1.5px solid var(--border)',
                  borderRadius: 12, color: 'var(--text-primary)',
                  fontSize: 14, fontFamily: 'var(--font)', outline: 'none',
                  transition: 'border-color 0.2s',
                  boxSizing: 'border-box',
                }}
                onFocus={e => e.target.style.borderColor = 'var(--accent)'}
                onBlur={e => e.target.style.borderColor = 'var(--border)'}
              />
            </div>

            <div style={{ marginBottom: 16 }}>
              <label style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)', display: 'block', marginBottom: 6 }}>
                Password
              </label>
              <div style={{ position: 'relative' }}>
                <input
                  id="login-password"
                  type={showPw ? 'text' : 'password'}
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="••••••••••••"
                  autoComplete="current-password"
                  style={{
                    width: '100%', padding: '11px 42px 11px 14px',
                    background: 'var(--bg-input)', border: '1.5px solid var(--border)',
                    borderRadius: 12, color: 'var(--text-primary)',
                    fontSize: 14, fontFamily: 'var(--font)', outline: 'none',
                    transition: 'border-color 0.2s', boxSizing: 'border-box',
                  }}
                  onFocus={e => e.target.style.borderColor = 'var(--accent)'}
                  onBlur={e => e.target.style.borderColor = 'var(--border)'}
                />
                <button type="button" onClick={() => setShowPw(p => !p)} style={{
                  position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)',
                  background: 'none', border: 'none', cursor: 'pointer',
                  color: 'var(--text-muted)', padding: 4, display: 'flex', alignItems: 'center',
                }}>
                  {showPw
                    ? <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
                    : <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                  }
                </button>
              </div>
            </div>

            {error && (
              <div style={{
                background: 'rgba(220,38,38,0.08)', border: '1px solid rgba(220,38,38,0.25)',
                borderRadius: 10, padding: '10px 14px', fontSize: 13,
                color: 'var(--error)', marginBottom: 14,
              }}>{error}</div>
            )}

            <button
              id="login-submit-btn"
              type="submit"
              disabled={loading}
              style={{
                width: '100%', padding: '13px',
                background: loading ? 'var(--bg-surface)' : 'linear-gradient(135deg, var(--accent-dim), var(--accent))',
                border: 'none', borderRadius: 14,
                color: loading ? 'var(--text-muted)' : '#fff',
                fontSize: 14, fontWeight: 700, fontFamily: 'var(--font)',
                cursor: loading ? 'not-allowed' : 'pointer',
                transition: 'all 0.2s',
                boxShadow: loading ? 'none' : '0 4px 20px var(--accent-glow)',
              }}
            >
              {loading ? 'Signing in…' : 'Sign in →'}
            </button>
          </form>
        </div>

        {/* Demo Accounts */}
        <div style={{ marginBottom: 8 }}>
          <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-muted)', textAlign: 'center', marginBottom: 12 }}>
            Quick Demo — one-click login
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {DEMO_ACCOUNTS.map(acc => (
              <button
                key={acc.username}
                id={`demo-login-${acc.username}`}
                onClick={() => doLogin(acc.username, acc.password)}
                disabled={loading}
                style={{
                  display: 'flex', alignItems: 'center', gap: 14,
                  padding: '14px 18px',
                  background: acc.colorLight,
                  border: `1px solid ${acc.colorBorder}`,
                  borderRadius: 16, cursor: loading ? 'not-allowed' : 'pointer',
                  textAlign: 'left', fontFamily: 'var(--font)',
                  transition: 'all 0.18s',
                  boxShadow: 'var(--shadow-card)',
                }}
                onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-1px)'; e.currentTarget.style.boxShadow = 'var(--shadow-raised)' }}
                onMouseLeave={e => { e.currentTarget.style.transform = 'none'; e.currentTarget.style.boxShadow = 'var(--shadow-card)' }}
              >
                <div style={{
                  width: 42, height: 42, borderRadius: 12, flexShrink: 0,
                  background: acc.colorLight, border: `1.5px solid ${acc.colorBorder}`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 20,
                }}>{acc.icon}</div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 2 }}>
                    <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)' }}>{acc.name}</span>
                    <span style={{
                      fontSize: 10, fontWeight: 700, letterSpacing: '0.06em',
                      padding: '2px 8px', borderRadius: 99,
                      background: acc.colorLight, color: acc.color,
                      border: `1px solid ${acc.colorBorder}`,
                      textTransform: 'uppercase',
                    }}>{acc.roleLabel}</span>
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.4 }}>{acc.desc}</div>
                </div>
                <svg viewBox="0 0 24 24" fill="none" stroke={acc.color} strokeWidth="2.5" width="16" height="16" style={{ flexShrink: 0 }}>
                  <polyline points="9 18 15 12 9 6"/>
                </svg>
              </button>
            ))}
          </div>
        </div>

      </div>
    </div>
  )
}
