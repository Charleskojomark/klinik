import { useState, useEffect } from 'react'

const API = '/api'

const IconChevronLeft = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{width:16,height:16}}>
    <polyline points="15 18 9 12 15 6"/>
  </svg>
)
const IconUser = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{width:14,height:14}}>
    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
    <circle cx="12" cy="7" r="4"/>
  </svg>
)
const IconCalendar = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{width:14,height:14}}>
    <rect x="3" y="4" width="18" height="18" rx="2"/>
    <line x1="16" y1="2" x2="16" y2="6"/>
    <line x1="8" y1="2" x2="8" y2="6"/>
    <line x1="3" y1="10" x2="21" y2="10"/>
  </svg>
)
const IconPhone = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{width:14,height:14}}>
    <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/>
  </svg>
)

export default function PatientPanel({ patients, activePatient, setActivePatient, onBack, refreshPatients }) {
  const [tab, setTab] = useState('history')
  const [patientDetails, setPatientDetails] = useState(null)
  const [loading, setLoading] = useState(false)

  // Fetch full details when activePatient changes
  useEffect(() => {
    if (activePatient) {
      setLoading(true)
      fetch(`${API}/patients/${activePatient.id}`)
        .then(r => r.json())
        .then(data => {
          setPatientDetails(data)
          setLoading(false)
        })
        .catch(() => setLoading(false))
    }
  }, [activePatient])

  const TABS = [
    { key: 'history',      label: 'Visit History' },
    { key: 'relationship', label: 'Relationship' },
  ]

  // View 1: List all patients
  if (!activePatient) {
    return (
      <div>
        <div className="back-bar">
          <button className="back-btn" onClick={onBack}><IconChevronLeft /></button>
          <span className="back-bar-label">All Patients</span>
        </div>
        <div className="history-list" style={{ padding: '16px' }}>
          {patients.length === 0 && (
            <div style={{ textAlign: 'center', color: 'var(--text-muted)', marginTop: 40 }}>
              No patients found. Record a consultation to create one!
            </div>
          )}
          {patients.map(p => (
            <div 
              key={p.id} 
              className="patient-context-strip" 
              style={{ margin: '0 0 12px 0' }}
              onClick={() => setActivePatient(p)}
            >
              <div>
                <div className="context-label">{p.id.split('-')[0].toUpperCase()}</div>
                <div className="context-name">{p.name || 'Unknown Patient'}</div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                  {p.age ? `${p.age}yo` : ''} {p.sex ? p.sex : ''} • {p.encounter_count} encounters
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  // View 2: Patient Details
  const p = patientDetails || activePatient
  const initials = p.name ? p.name.split(' ').map(n=>n[0]).join('').substring(0,2).toUpperCase() : '?'

  return (
    <div>
      <div className="back-bar">
        <button className="back-btn" onClick={() => setActivePatient(null)}>
          <IconChevronLeft />
        </button>
        <span className="back-bar-label">Patient Details</span>
      </div>

      <div className="patient-hero-card">
        <div className="patient-hero-top">
          <div className="patient-initials-avatar">{initials}</div>
          <div>
            <div className="patient-hero-name">{p.name || 'Unknown Patient'}</div>
            <div className="patient-hero-sub">ID: {p.id.substring(0,8)}</div>
          </div>
        </div>

        <div className="patient-stats-grid">
          <div className="stat-box">
            <IconUser />
            <div className="stat-value">
              {p.age ? `${p.age} yrs` : '--'}
              {p.sex && p.sex !== 'Unknown' && p.sex !== 'unknown' ? <span> {p.sex}</span> : null}
            </div>
            <div className="stat-label">Age</div>
          </div>
          <div className="stat-box">
            <IconPhone />
            <div className="stat-value" style={{fontSize: 12}}>{p.phone || '--'}</div>
            <div className="stat-label">Contact</div>
          </div>
          <div className="stat-box">
            <IconCalendar />
            <div className="stat-value">{p.encounter_count || p.encounters?.length || 0}</div>
            <div className="stat-label">Encounters</div>
          </div>
        </div>
      </div>

      <div className="tabs-bar">
        {TABS.map(t => (
          <button
            key={t.key}
            className={`tab-btn ${tab === t.key ? 'active' : ''}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'history' && (
        <div className="history-list">
          {loading && <div style={{ textAlign: 'center', padding: 20 }}>Loading history...</div>}
          
          {!loading && p.encounters?.length === 0 && (
            <div style={{ textAlign: 'center', color: 'var(--text-muted)', marginTop: 20 }}>
              No encounters found.
            </div>
          )}

          {!loading && p.encounters?.map((enc, i) => (
            <div key={enc.id} className="history-card" style={{ paddingBottom: 16 }}>
              <div className="history-date">{new Date(enc.created_at).toLocaleString()}</div>
              <div className="history-title">Visit #{p.encounters.length - i}</div>
              <div className="history-sub" style={{ marginBottom: 12 }}>{enc.supervisor_summary || 'No summary'}</div>
              
              {/* Show SOAP Note if available */}
              {enc.soap_note && (enc.soap_note.subjective || enc.soap_note.objective) && (
                <div className="soap-sections" style={{ marginTop: 16 }}>
                  {enc.soap_note.subjective && (
                    <div className="soap-card">
                      <div className="soap-card-label"><div className="soap-card-dot" />Subjective</div>
                      <div className="soap-card-text">{enc.soap_note.subjective}</div>
                    </div>
                  )}
                  {enc.soap_note.objective && (
                    <div className="soap-card">
                      <div className="soap-card-label"><div className="soap-card-dot" />Objective</div>
                      <div className="soap-card-text">{enc.soap_note.objective}</div>
                    </div>
                  )}
                  {enc.soap_note.assessment && (
                    <div className="soap-card">
                      <div className="soap-card-label"><div className="soap-card-dot" />Assessment</div>
                      <div className="soap-card-text">{enc.soap_note.assessment}</div>
                    </div>
                  )}
                  {enc.soap_note.plan && (
                    <div className="soap-card">
                      <div className="soap-card-label"><div className="soap-card-dot" />Plan</div>
                      <div className="soap-card-text">{enc.soap_note.plan}</div>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
          <div style={{ height: 24 }} />
        </div>
      )}

      {tab === 'relationship' && (
        <div style={{ padding: '24px 16px', color: 'var(--text-muted)', fontSize: 14, textAlign: 'center' }}>
          This patient has {p.encounter_count || 0} recorded encounters in Klinik.
        </div>
      )}
    </div>
  )
}
