import { useState, useEffect } from 'react'

export default function AuditLogsPage({ authFetch }) {
  const [logs, setLogs]       = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState(null)

  useEffect(() => {
    authFetch('/api/admin/audit-logs')
      .then(r => r.json())
      .then(d => { setLogs(d.logs || []); setLoading(false) })
      .catch(e => { setError(e.message); setLoading(false) })
  }, [])

  const statusColor = (code) => {
    if (!code) return 'var(--text-muted)'
    if (code < 300) return 'var(--success)'
    if (code < 400) return 'var(--warning)'
    return 'var(--error)'
  }

  return (
    <div style={{ padding: '0 0 24px' }}>
      <div style={{
        padding: '16px 18px 8px', fontWeight: 700, fontSize: 13,
        color: 'var(--text-muted)', letterSpacing: '0.08em', textTransform: 'uppercase',
        display: 'flex', alignItems: 'center', gap: 8,
      }}>
        <span>🛡️</span> Audit Logs
        <span style={{
          fontSize: 10, padding: '2px 8px', borderRadius: 99,
          background: 'rgba(245,158,11,0.1)', color: '#F59E0B',
          border: '1px solid rgba(245,158,11,0.25)', fontWeight: 700,
        }}>ADMIN ONLY</span>
      </div>

      {loading && (
        <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
          <div style={{
            width: 32, height: 32, border: '3px solid var(--border)',
            borderTopColor: 'var(--accent)', borderRadius: '50%',
            animation: 'spin 0.9s linear infinite', margin: '0 auto 12px',
          }}/>
          Loading audit logs…
        </div>
      )}

      {error && (
        <div style={{
          margin: '0 16px', padding: '14px 18px',
          background: 'rgba(220,38,38,0.08)', border: '1px solid rgba(220,38,38,0.2)',
          borderRadius: 14, color: 'var(--error)', fontSize: 13,
        }}>⚠️ {error}</div>
      )}

      {!loading && !error && logs.length === 0 && (
        <div style={{ textAlign: 'center', padding: 48 }}>
          <div style={{ fontSize: 36, marginBottom: 8 }}>📋</div>
          <div style={{ color: 'var(--text-muted)', fontSize: 14 }}>No audit events recorded yet.</div>
          <div style={{ color: 'var(--text-muted)', fontSize: 12, marginTop: 4 }}>Events are logged as API requests are made.</div>
        </div>
      )}

      {!loading && logs.length > 0 && (
        <div style={{ padding: '0 16px', display: 'flex', flexDirection: 'column', gap: 8 }}>
          {logs.map((log) => (
            <div key={log.id} style={{
              background: 'var(--bg-card)', border: '1px solid var(--border)',
              borderRadius: 14, padding: '12px 16px', boxShadow: 'var(--shadow-card)',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{
                    fontSize: 10, fontWeight: 700, padding: '2px 8px',
                    borderRadius: 6, background: 'var(--bg-surface)',
                    color: 'var(--text-muted)', border: '1px solid var(--border)',
                    fontFamily: 'monospace', letterSpacing: '0.04em',
                  }}>{log.method}</span>
                  <span style={{
                    fontSize: 11, fontWeight: 700, color: statusColor(log.status_code),
                  }}>{log.status_code || '—'}</span>
                </div>
                <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                  {log.duration_ms ? `${log.duration_ms.toFixed(0)}ms` : ''}
                </span>
              </div>
              <div style={{
                fontSize: 12, fontFamily: 'monospace', color: 'var(--text-primary)',
                background: 'var(--bg-surface)', padding: '6px 10px',
                borderRadius: 8, border: '1px solid var(--border)', marginBottom: 6,
                wordBreak: 'break-all',
              }}>{log.endpoint}</div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text-muted)' }}>
                <span>📍 {log.ip_address || '—'}</span>
                <span>{log.timestamp ? new Date(log.timestamp).toLocaleString() : '—'}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
