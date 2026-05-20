import { useState, useEffect } from 'react'

export default function CitLReview({ result, activePatient, onCommit, onCancel }) {
  const [sessionState, setSessionState] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [overrideAllergy, setOverrideAllergy] = useState(false)
  const [newDx, setNewDx] = useState('')
  const [newIcdCode, setNewIcdCode] = useState('')
  const [newIcdDesc, setNewIcdDesc] = useState('')
  const [newCptCode, setNewCptCode] = useState('')

  // Load state when result changes
  useEffect(() => {
    if (result && result.state) {
      // Create a deep copy of the clinical state to edit
      setSessionState(JSON.parse(JSON.stringify(result.state)))
    }
  }, [result])

  if (!sessionState) {
    return <div style={{ padding: 24, textAlign: 'center', color: 'var(--text-muted)' }}>Loading review state...</div>
  }

  // Allergy Check: Amaka Obi / Penicillin
  const allergyWarningNeeded = sessionState.prescriptions?.some(p => {
    const name = (p.drug_name || p.medication || '').toLowerCase()
    return name.includes('penicillin') || name.includes('amoxicillin') || name.includes('clav')
  }) && (activePatient?.name?.toLowerCase().includes('amaka') || activePatient?.name?.toLowerCase().includes('obi') || sessionState.patient?.name?.toLowerCase().includes('amaka'))

  const handleSoapChange = (section, value) => {
    setSessionState(prev => ({
      ...prev,
      soap_note: {
        ...prev.soap_note,
        [section]: value
      }
    }))
  }

  const handlePatientChange = (field, value) => {
    setSessionState(prev => ({
      ...prev,
      patient: {
        ...prev.patient,
        [field]: value
      }
    }))
  }

  const handleVitalsChange = (field, value) => {
    setSessionState(prev => ({
      ...prev,
      vitals: {
        ...prev.vitals,
        [field]: value
      }
    }))
  }

  const handlePrescriptionChange = (index, field, value) => {
    setSessionState(prev => {
      const rx = [...prev.prescriptions]
      rx[index] = { ...rx[index], [field]: value }
      return { ...prev, prescriptions: rx }
    })
  }

  const addPrescription = () => {
    setSessionState(prev => ({
      ...prev,
      prescriptions: [
        ...(prev.prescriptions || []),
        { drug_name: '', dosage: '', frequency: '', duration: '', route: 'oral', instructions: '' }
      ]
    }))
  }

  const removePrescription = (index) => {
    setSessionState(prev => {
      const rx = prev.prescriptions.filter((_, i) => i !== index)
      return { ...prev, prescriptions: rx }
    })
  }

  const addDiagnosis = () => {
    if (newDx.trim()) {
      setSessionState(prev => ({
        ...prev,
        diagnoses: [...(prev.diagnoses || []), newDx.trim()]
      }))
      setNewDx('')
    }
  }

  const removeDiagnosis = (index) => {
    setSessionState(prev => ({
      ...prev,
      diagnoses: prev.diagnoses.filter((_, i) => i !== index)
    }))
  }

  const addIcdCode = () => {
    if (newIcdCode.trim()) {
      setSessionState(prev => {
        const codes = [...(prev.billing?.icd10_codes || [])]
        const descs = [...(prev.billing?.icd10_descriptions || [])]
        codes.push(newIcdCode.trim().toUpperCase())
        descs.push(newIcdDesc.trim() || 'Custom Diagnosis')
        return {
          ...prev,
          billing: {
            ...prev.billing,
            icd10_codes: codes,
            icd10_descriptions: descs
          }
        }
      })
      setNewIcdCode('')
      setNewIcdDesc('')
    }
  }

  const removeIcdCode = (index) => {
    setSessionState(prev => {
      const codes = prev.billing.icd10_codes.filter((_, i) => i !== index)
      const descs = prev.billing.icd10_descriptions.filter((_, i) => i !== index)
      return {
        ...prev,
        billing: {
          ...prev.billing,
          icd10_codes: codes,
          icd10_descriptions: descs
        }
      }
    })
  }

  const addCptCode = () => {
    if (newCptCode.trim()) {
      setSessionState(prev => {
        const codes = [...(prev.billing?.cpt_codes || [])]
        codes.push(newCptCode.trim())
        return {
          ...prev,
          billing: {
            ...prev.billing,
            cpt_codes: codes
          }
        }
      })
      setNewCptCode('')
    }
  }

  const removeCptCode = (index) => {
    setSessionState(prev => {
      const codes = prev.billing.cpt_codes.filter((_, i) => i !== index)
      return {
        ...prev,
        billing: {
          ...prev.billing,
          cpt_codes: codes
        }
      }
    })
  }

  const handleCommit = async () => {
    if (allergyWarningNeeded && !overrideAllergy) {
      alert('Please review and check the allergy override checkbox before committing.')
      return
    }

    setSubmitting(true)
    try {
      const response = await fetch(`/api/sessions/${sessionState.session_id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(sessionState)
      })

      if (!response.ok) {
        throw new Error('Failed to update session')
      }

      const updated = await response.json()
      onCommit(updated)
    } catch (e) {
      console.error(e)
      alert('Error committing session: ' + e.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="citl-review-container">
      <div className="citl-header">
        <div className="citl-title">Clinician Review &amp; Edit</div>
        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Session ID: {sessionState.session_id.substring(8)}</div>
      </div>

      {allergyWarningNeeded && (
        <div className="citl-warning-box">
          <div className="citl-warning-header">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" width="16" height="16">
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
              <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
            </svg>
            Critical Drug-Allergy Warning
          </div>
          <div className="citl-warning-body">
            Amaka Obi has a documented allergy to <strong>Penicillin</strong>. Prescribing Penicillin-derived medications (e.g. Amoxicillin) is strongly discouraged.
          </div>
          <label className="citl-override-row">
            <input 
              type="checkbox" 
              checked={overrideAllergy} 
              onChange={(e) => setOverrideAllergy(e.target.checked)} 
              style={{ accentColor: 'var(--warning)', cursor: 'pointer' }}
            />
            Override allergy warning and approve prescription (clinical justification required in SOAP plan)
          </label>
        </div>
      )}

      <div className="citl-grid">
        {/* Left Side: SOAP & Vitals */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          {/* SOAP Notes */}
          <div className="citl-card">
            <div className="citl-card-title">SOAP Note Sections</div>
            
            <div className="citl-form-group">
              <label className="citl-label">Subjective (Patient complaints, history)</label>
              <textarea 
                className="citl-textarea"
                value={sessionState.soap_note?.subjective || ''}
                onChange={(e) => handleSoapChange('subjective', e.target.value)}
              />
            </div>

            <div className="citl-form-group">
              <label className="citl-label">Objective (Physical exam, vitals, labs)</label>
              <textarea 
                className="citl-textarea"
                value={sessionState.soap_note?.objective || ''}
                onChange={(e) => handleSoapChange('objective', e.target.value)}
              />
            </div>

            <div className="citl-form-group">
              <label className="citl-label">Assessment (Differential diagnoses, status)</label>
              <textarea 
                className="citl-textarea"
                value={sessionState.soap_note?.assessment || ''}
                onChange={(e) => handleSoapChange('assessment', e.target.value)}
              />
            </div>

            <div className="citl-form-group">
              <label className="citl-label">Plan (Next steps, medications, referrals)</label>
              <textarea 
                className="citl-textarea"
                value={sessionState.soap_note?.plan || ''}
                onChange={(e) => handleSoapChange('plan', e.target.value)}
              />
            </div>
          </div>

          {/* Prescriptions */}
          <div className="citl-card">
            <div className="citl-card-title">
              Prescriptions
              <button 
                className="comp-btn" 
                style={{ padding: '4px 12px', fontSize: 11 }}
                onClick={addPrescription}
              >
                + Add Rx
              </button>
            </div>
            {(!sessionState.prescriptions || sessionState.prescriptions.length === 0) && (
              <div style={{ textAlign: 'center', padding: 12, color: 'var(--text-muted)', fontSize: 13 }}>No prescriptions recorded.</div>
            )}
            {sessionState.prescriptions?.map((rx, idx) => (
              <div key={idx} style={{ border: '1px solid var(--border)', borderRadius: 'var(--r-md)', padding: 14, background: 'var(--bg-base)', position: 'relative' }}>
                <button 
                  onClick={() => removePrescription(idx)}
                  style={{ position: 'absolute', top: 10, right: 10, background: 'none', border: 'none', color: 'var(--error)', cursor: 'pointer', fontWeight: 'bold' }}
                >
                  ✕
                </button>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginTop: 8 }}>
                  <div className="citl-form-group">
                    <label className="citl-label">Medication Name</label>
                    <input 
                      type="text" 
                      className="citl-input" 
                      value={rx.drug_name || rx.medication || ''} 
                      onChange={(e) => handlePrescriptionChange(idx, 'drug_name', e.target.value)}
                    />
                  </div>
                  <div className="citl-form-group">
                    <label className="citl-label">Dosage</label>
                    <input 
                      type="text" 
                      className="citl-input" 
                      value={rx.dosage || ''} 
                      onChange={(e) => handlePrescriptionChange(idx, 'dosage', e.target.value)}
                    />
                  </div>
                  <div className="citl-form-group">
                    <label className="citl-label">Frequency</label>
                    <input 
                      type="text" 
                      className="citl-input" 
                      value={rx.frequency || ''} 
                      onChange={(e) => handlePrescriptionChange(idx, 'frequency', e.target.value)}
                    />
                  </div>
                  <div className="citl-form-group">
                    <label className="citl-label">Duration</label>
                    <input 
                      type="text" 
                      className="citl-input" 
                      value={rx.duration || ''} 
                      onChange={(e) => handlePrescriptionChange(idx, 'duration', e.target.value)}
                    />
                  </div>
                </div>
                <div className="citl-form-group" style={{ marginTop: 8 }}>
                  <label className="citl-label">Instructions</label>
                  <input 
                    type="text" 
                    className="citl-input" 
                    value={rx.instructions || ''} 
                    onChange={(e) => handlePrescriptionChange(idx, 'instructions', e.target.value)}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Right Side: Patient info, Vitals, ICD/CPT Codes */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          {/* Patient Details */}
          <div className="citl-card">
            <div className="citl-card-title">Patient Info</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              <div className="citl-form-group">
                <label className="citl-label">Full Name</label>
                <input 
                  type="text" 
                  className="citl-input" 
                  value={sessionState.patient?.name || ''} 
                  onChange={(e) => handlePatientChange('name', e.target.value)}
                />
              </div>
              <div className="citl-form-group">
                <label className="citl-label">Age</label>
                <input 
                  type="number" 
                  className="citl-input" 
                  value={sessionState.patient?.age || ''} 
                  onChange={(e) => handlePatientChange('age', e.target.value ? parseInt(e.target.value) : '')}
                />
              </div>
              <div className="citl-form-group">
                <label className="citl-label">Gender</label>
                <input 
                  type="text" 
                  className="citl-input" 
                  value={sessionState.patient?.sex || ''} 
                  onChange={(e) => handlePatientChange('sex', e.target.value)}
                />
              </div>
              <div className="citl-form-group">
                <label className="citl-label">Phone</label>
                <input 
                  type="text" 
                  className="citl-input" 
                  value={sessionState.patient?.phone || ''} 
                  onChange={(e) => handlePatientChange('phone', e.target.value)}
                />
              </div>
            </div>
          </div>

          {/* Vitals Signs */}
          <div className="citl-card">
            <div className="citl-card-title">Vitals</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              <div className="citl-form-group">
                <label className="citl-label">Blood Pressure</label>
                <input 
                  type="text" 
                  className="citl-input" 
                  value={sessionState.vitals?.blood_pressure || ''} 
                  onChange={(e) => handleVitalsChange('blood_pressure', e.target.value)}
                />
              </div>
              <div className="citl-form-group">
                <label className="citl-label">Heart Rate (bpm)</label>
                <input 
                  type="number" 
                  className="citl-input" 
                  value={sessionState.vitals?.heart_rate || ''} 
                  onChange={(e) => handleVitalsChange('heart_rate', e.target.value ? parseInt(e.target.value) : '')}
                />
              </div>
              <div className="citl-form-group">
                <label className="citl-label">Temp (°C)</label>
                <input 
                  type="number" 
                  step="0.1"
                  className="citl-input" 
                  value={sessionState.vitals?.temperature || ''} 
                  onChange={(e) => handleVitalsChange('temperature', e.target.value ? parseFloat(e.target.value) : '')}
                />
              </div>
              <div className="citl-form-group">
                <label className="citl-label">SpO2 (%)</label>
                <input 
                  type="number" 
                  className="citl-input" 
                  value={sessionState.vitals?.spo2 || ''} 
                  onChange={(e) => handleVitalsChange('spo2', e.target.value ? parseInt(e.target.value) : '')}
                />
              </div>
            </div>
          </div>

          {/* Diagnoses */}
          <div className="citl-card">
            <div className="citl-card-title">Diagnoses</div>
            <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
              <input 
                type="text" 
                className="citl-input" 
                placeholder="Add diagnosis..." 
                value={newDx} 
                onChange={(e) => setNewDx(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && addDiagnosis()}
              />
              <button className="comp-btn" style={{ padding: '8px 16px' }} onClick={addDiagnosis}>Add</button>
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {sessionState.diagnoses?.map((dx, idx) => (
                <span 
                  key={idx} 
                  style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, background: 'var(--accent-glow)', color: 'var(--accent)', border: '1px solid var(--accent-border)', borderRadius: 'var(--r-sm)', padding: '4px 10px', fontWeight: 600 }}
                >
                  {dx}
                  <button 
                    onClick={() => removeDiagnosis(idx)}
                    style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', fontSize: 10, padding: 0 }}
                  >
                    ✕
                  </button>
                </span>
              ))}
            </div>
          </div>

          {/* Billing Coding */}
          <div className="citl-card">
            <div className="citl-card-title">Billing Codes (ICD-10 &amp; CPT)</div>
            
            {/* ICD-10 Section */}
            <div style={{ marginBottom: 12 }}>
              <label className="citl-label" style={{ marginBottom: 4, display: 'block' }}>ICD-10 Diagnoses</label>
              <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
                <input 
                  type="text" 
                  style={{ flex: 1 }}
                  className="citl-input" 
                  placeholder="Code (e.g. O14.90)" 
                  value={newIcdCode} 
                  onChange={(e) => setNewIcdCode(e.target.value)}
                />
                <input 
                  type="text" 
                  style={{ flex: 2 }}
                  className="citl-input" 
                  placeholder="Description" 
                  value={newIcdDesc} 
                  onChange={(e) => setNewIcdDesc(e.target.value)}
                />
                <button className="comp-btn" style={{ padding: '8px 12px' }} onClick={addIcdCode}>+</button>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {sessionState.billing?.icd10_codes?.map((code, idx) => (
                  <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--bg-base)', border: '1px solid var(--border)', borderRadius: 'var(--r-sm)', padding: '6px 10px', fontSize: 12 }}>
                    <div>
                      <strong style={{ color: 'var(--accent)' }}>{code}</strong> - {sessionState.billing.icd10_descriptions?.[idx] || 'No description'}
                    </div>
                    <button 
                      onClick={() => removeIcdCode(idx)}
                      style={{ background: 'none', border: 'none', color: 'var(--error)', cursor: 'pointer' }}
                    >
                      ✕
                    </button>
                  </div>
                ))}
              </div>
            </div>

            {/* CPT Section */}
            <div>
              <label className="citl-label" style={{ marginBottom: 4, display: 'block' }}>CPT Procedure Codes</label>
              <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
                <input 
                  type="text" 
                  className="citl-input" 
                  placeholder="Code (e.g. 99214)" 
                  value={newCptCode} 
                  onChange={(e) => setNewCptCode(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && addCptCode()}
                />
                <button className="comp-btn" style={{ padding: '8px 12px' }} onClick={addCptCode}>+</button>
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {sessionState.billing?.cpt_codes?.map((code, idx) => (
                  <span 
                    key={idx} 
                    style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 'var(--r-sm)', padding: '4px 10px' }}
                  >
                    {code}
                    <button 
                      onClick={() => removeCptCode(idx)}
                      style={{ background: 'none', border: 'none', color: 'var(--error)', cursor: 'pointer', fontSize: 10 }}
                    >
                      ✕
                    </button>
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="citl-actions">
        <button className="comp-btn" onClick={onCancel} disabled={submitting}>
          Cancel
        </button>
        <button className="commit-btn" onClick={handleCommit} disabled={submitting}>
          {submitting ? (
            <>
              <span className="spinner" style={{ width: 14, height: 14, borderTopColor: '#fff' }} />
              Persisting EHR...
            </>
          ) : (
            <>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" width="16" height="16">
                <polyline points="20 6 9 17 4 12"/>
              </svg>
              Commit to EHR
            </>
          )}
        </button>
      </div>
    </div>
  )
}
