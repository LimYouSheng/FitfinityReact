import { useEffect, useState } from 'react'
import Panel from '../../components/Panel.jsx'
import ProfileAvatar from '../../components/ProfileAvatar.jsx'
import StatusBadge from '../../components/StatusBadge.jsx'
import StaffPersonalFields from '../../components/StaffPersonalFields.jsx'
import LoadingIndicator from '../../components/LoadingIndicator.jsx'
import { useEditGuard } from '../../components/EditGuardProvider.jsx'
import { useActionConfirmation } from '../../components/ActionConfirmationProvider.jsx'
import { adminErrors, adminPayload } from '../../app/adminOnboarding.js'
import { formatDate } from '../../utils/date.js'
import OwnerEmailEditor from './OwnerEmailEditor.jsx'

export default function OwnerProfilePage({ user, services, today, emailAuth, onSaved }) {
  const [record, setRecord] = useState(null)
  const [draft, setDraft] = useState(null)
  const [error, setError] = useState('')
  const [errors, setErrors] = useState({})
  const [revision, setRevision] = useState(0)
  const [busy, setBusy] = useState(false)
  const [attempt, setAttempt] = useState(null)
  const confirm = useActionConfirmation()
  const { setActiveEdit } = useEditGuard()
  useEffect(() => {
    let current = true
    services.ownerService.getProfile().then(value => { if (current) setRecord(value) }).catch(reason => { if (current) setError(reason.message) })
    return () => { current = false }
  }, [services, user.id, revision])
  useEffect(() => {
    if (!draft) return
    setActiveEdit('Owner details')
    return () => setActiveEdit(value => value === 'Owner details' ? null : value)
  }, [draft, setActiveEdit])
  const save = async event => {
    event.preventDefault()
    if (busy) return
    const invalid = adminErrors(draft, today)
    setErrors(invalid)
    if (Object.keys(invalid).length) return
    const input = attempt ?? { id: user.id, expectedVersion: record.version, details: adminPayload(draft) }
    if (!attempt && !await confirm({ title: 'Save Owner details?', message: 'Update your contact profile. Login email is changed separately through verification.', confirmLabel: 'Save Changes' })) return
    setBusy(true); setError(''); setAttempt(input)
    try {
      const result = await services.ownerService.saveProfile(input)
      setRecord(result); setAttempt(null); setDraft(null)
      try { await onSaved() } catch { setError('Saved. Refresh to update the account heading.') }
    } catch (reason) {
      setError(reason.message)
      if (reason.status >= 400 && reason.status < 500) setAttempt(null)
    } finally { setBusy(false) }
  }
  return <>
    <div className="page-head profile-identity-card">
      <div className="profile-identity-main"><ProfileAvatar name={record?.name ?? user.name} /><div><span className="eyebrow">Owner Profile</span><h1>{record?.name ?? user.name}</h1></div></div>
      <div className="profile-card-statuses" aria-label="Account status"><StatusBadge tone={user.status === 'inactive' ? 'amber' : 'green'}>{user.status === 'inactive' ? 'Inactive' : 'Active'}</StatusBadge></div>
    </div>
    <Panel className={draft ? 'editing-section' : ''}>
      <div className="section-head"><h2>General Information</h2>{record && !draft && <button type="button" className="text-action" onClick={() => { setErrors({}); setError(''); setDraft({ ...record, phone: { countryCode: record.phone_country_code, number: record.phone_number } }) }}>Edit</button>}</div>
      {error && <p role="alert">{error}</p>}
      {!record ? error ? <button className="text-action" onClick={() => { setError(''); setRevision(value => value + 1) }}>Retry Profile</button> : <LoadingIndicator label="Loading Owner profile…" />
        : draft ? <form onSubmit={save} noValidate><fieldset disabled={busy || Boolean(attempt)} className="onboarding-step-body"><div className="onboarding-grid"><StaffPersonalFields label="Owner" draft={draft} errors={errors} emailReadOnly onChange={patch => setDraft(value => ({ ...value, ...patch }))} /></div></fieldset>
          <div className="inline-actions"><button className="onboarding-button" type="button" disabled={busy || Boolean(attempt)} onClick={() => setDraft(null)}>Cancel</button><button className="onboarding-button primary" disabled={busy}>{attempt ? 'Check Original Save' : 'Save Changes'}</button></div>
        </form> : <div className="info-list profile-info-grid">{[
          ['Name', record.name], ['Mobile Number', record.phone_number ? `${record.phone_country_code} ${record.phone_number}` : '—'],
          ['Email', record.email], ['Birthday', record.birthday ? formatDate(record.birthday) : '—'], ['Gender', record.gender || '—'], ['Role', 'Owner'],
        ].map(([label, value]) => <div className="info-row" key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>}
      {record && emailAuth && !draft && <OwnerEmailEditor auth={emailAuth} version={record.version} onCompleted={onSaved} />}
    </Panel>
  </>
}
