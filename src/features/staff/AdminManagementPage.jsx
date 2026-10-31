import { useEffect, useEffectEvent, useState } from 'react'
import ProfileAvatar from '../../components/ProfileAvatar.jsx'
import Panel from '../../components/Panel.jsx'
import ProfileNavigation from '../../components/ProfileNavigation.jsx'
import StatusBadge from '../../components/StatusBadge.jsx'
import StaffPersonalFields from '../../components/StaffPersonalFields.jsx'
import ApprovalSetting from '../../components/ApprovalSetting.jsx'
import { useEditGuard } from '../../components/EditGuardProvider.jsx'
import { useActionConfirmation } from '../../components/ActionConfirmationProvider.jsx'
import { ADMIN_APPROVAL_FIELDS } from '../../app/adminApprovals.js'
import { adminErrors, adminPayload } from '../../app/adminOnboarding.js'
import { formatDate } from '../../utils/date.js'

export default function AdminManagementPage({ services, selectedId, today, onNavigate, onBack, onCreate }) {
  const [records, setRecords] = useState(null)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  const load = useEffectEvent(() => selectedId ? services.staffService.getById({ id: selectedId }) : services.staffService.getAll())
  useEffect(() => {
    let current = true
    setRecords(null); setError('')
    load().then(value => { if (current) setRecords(value) }).catch(failure => { if (current) setError(failure.message) })
    return () => { current = false }
  }, [selectedId, revision])
  if (!records) return <section aria-busy={!error}>{error ? <><p role="alert">{error}</p><button type="button" onClick={() => setRevision(value => value + 1)}>Retry</button></> : <p>Loading Admin details…</p>}</section>
  if (selectedId) return <AdminProfile key={selectedId} record={records} today={today} onBack={onBack} onSave={body => services.staffService.update({ id: selectedId, body })} onSaved={setRecords} />
  return <>
    <div className="page-head"><h1>Admin</h1><button type="button" className="primary-button" onClick={onCreate}>Create Admin</button></div>
    <Panel><div className="info-list">{records.map(record => <div className="info-row" key={record.id}>
      <button type="button" className="text-action" onClick={() => onNavigate(`admins/${record.id}`)}>{record.details.name}</button>
      <span>{record.details.email}</span><StatusBadge tone={record.status === 'active' ? 'green' : 'amber'}>{record.status === 'active' ? 'Active' : 'Inactive'}</StatusBadge>
    </div>)}{!records.length && <p>No Admin accounts.</p>}</div></Panel>
  </>
}

function personalDraft(record) {
  const details = record.details
  return { ...details, phone: { countryCode: details.phone_country_code, number: details.phone_number } }
}

function AdminProfile({ record, today, onBack, onSave, onSaved }) {
  const [tab, setTab] = useState('general')
  const [editor, setEditor] = useState(null)
  const [draft, setDraft] = useState(() => personalDraft(record))
  const [requirements, setRequirements] = useState(record.approvalNeeded)
  const [busy, setBusy] = useState(false)
  const [errors, setErrors] = useState({})
  const [attempt, setAttempt] = useState(null)
  const { setActiveEdit, guardNavigation } = useEditGuard()
  const confirm = useActionConfirmation()
  useEffect(() => {
    setActiveEdit(editor || attempt ? 'Admin details' : null)
    return () => setActiveEdit(null)
  }, [editor, attempt, setActiveEdit])
  const begin = kind => {
    setErrors({}); setDraft(personalDraft(record)); setRequirements(record.approvalNeeded); setEditor(kind)
  }
  const save = async operation => {
    if (busy) return
    if (!attempt && operation === 'details') {
      const invalid = adminErrors(draft, today)
      if (Object.keys(invalid).length) { setErrors(invalid); return }
    }
    const body = attempt ?? { expectedVersion: record.version, operation,
      ...(operation === 'details' ? { details: adminPayload(draft) } : {}),
      ...(operation === 'approvals' ? { approvalNeeded: requirements } : {}),
    }
    if (!attempt && !await confirm({ title: `${operation === 'deactivate' ? 'Deactivate Admin' : operation === 'reactivate' ? 'Reactivate Admin' : 'Save changes'}?`,
      message: operation === 'deactivate' ? 'Existing sign-ins will end. The account and history will be retained.' : operation === 'reactivate' ? 'This Admin must sign in afresh. Existing approval requirements are retained.' : 'Save the reviewed Admin information?', confirmLabel: 'Confirm' })) return
    setBusy(true); setErrors({}); setAttempt(body)
    try {
      const saved = await onSave(body)
      onSaved(saved); setAttempt(null); setEditor(null)
    } catch (failure) {
      setErrors({ save: failure.message })
      if (failure.status >= 400 && failure.status < 500) setAttempt(null)
    } finally { setBusy(false) }
  }
  const heading = (label, kind) => <div className="section-heading"><h2>{label}</h2><div className="section-actions">
    {editor === kind ? <><button type="button" className="text-action" disabled={busy || Boolean(attempt)} onClick={() => { setEditor(null); setAttempt(null); setErrors({}) }}>Cancel</button>
      <button type="button" className="text-action" disabled={busy} onClick={() => save(kind)}>{busy ? 'Saving…' : attempt ? 'Retry Original Save' : 'Save'}</button></>
      : record.status === 'active' && <button type="button" className="text-action" disabled={Boolean(editor) || busy} onClick={() => begin(kind)}>Edit</button>}
  </div></div>
  return <>
    <button type="button" className="text-action" disabled={busy || Boolean(attempt)} onClick={() => guardNavigation(onBack)}>Back to Admin</button>
    <div className="page-head profile-identity-card"><div className="profile-identity-main"><ProfileAvatar name={record.details.name} /><div><span className="eyebrow">Admin</span><h1>{record.details.name}</h1></div></div>
      <div className="profile-card-statuses" aria-label="Admin status"><StatusBadge tone={record.status === 'active' ? 'green' : 'amber'}>{record.status === 'active' ? 'Active' : 'Inactive'}</StatusBadge></div>
    </div>
      <ProfileNavigation items={[["general", "General Details"], ["approvals", "Approval Requirements"], ["lifecycle", record.status === 'active' ? 'Deactivate' : 'Reactivate']]} activeKey={tab}
        onSelect={key => { if (!busy && !attempt) guardNavigation(() => { setEditor(null); setErrors({}); setTab(key) }) }} />
      <div className="stack-gap">
        {tab === 'general' && <Panel className={editor === 'details' ? 'editing-section' : ''}>
          {heading('General Information', 'details')}
          {editor === 'details' ? <fieldset className="onboarding-step-body" disabled={busy || Boolean(attempt)}><div className="onboarding-grid">
            <StaffPersonalFields label="Admin" draft={draft} errors={errors} emailReadOnly onChange={patch => setDraft(value => ({ ...value, ...patch }))} />
          </div><p className="helper">Login email cannot be changed through general details.</p></fieldset>
            : <div className="info-list profile-info-grid">{[['Admin name', record.details.name], ['Mobile Number', `${record.details.phone_country_code} ${record.details.phone_number}`], ['Email', record.details.email], ['Birthday', formatDate(record.details.birthday)], ['Gender', record.details.gender]].map(([label, value]) => <div className="info-row" key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>}
        </Panel>}
        {tab === 'approvals' && <Panel className={editor === 'approvals' ? 'editing-section' : ''}>
          {heading('Approval Requirements', 'approvals')}<p>Role: Admin. New Admins require approval for Exercise Library and Content by default. Downloads and uploads do not require approval. Checked actions require Owner approval. Read access and Owner-only restrictions remain unchanged.</p>
          {ADMIN_APPROVAL_FIELDS.map(([key, label]) => <ApprovalSetting key={key} label={label} checked={editor === 'approvals' ? requirements[key] : record.approvalNeeded[key]} disabled={editor !== 'approvals' || busy || Boolean(attempt)} onChange={checked => setRequirements(value => ({ ...value, [key]: checked }))} />)}
        </Panel>}
        {tab === 'lifecycle' && <Panel><h2>{record.status === 'active' ? 'Deactivate Admin' : 'Reactivate Admin'}</h2>
          <p>The account and its recorded history are retained. Reactivation requires a fresh sign-in.</p>
          <button type="button" className="secondary-button" disabled={busy} onClick={() => save(record.status === 'active' ? 'deactivate' : 'reactivate')}>{attempt ? 'Retry Original Save' : record.status === 'active' ? 'Deactivate Admin' : 'Reactivate Admin'}</button>
        </Panel>}
        {errors.save && <p role="alert">{errors.save}</p>}
      </div>
  </>
}
