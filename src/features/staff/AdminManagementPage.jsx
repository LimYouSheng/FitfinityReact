import { useEffect, useEffectEvent, useState } from 'react'
import AdminDirectory from './AdminDirectory.jsx'
import ProfileAvatar from '../../components/ProfileAvatar.jsx'
import Panel from '../../components/Panel.jsx'
import ProfileNavigation from '../../components/ProfileNavigation.jsx'
import StatusBadge from '../../components/StatusBadge.jsx'
import StaffPersonalFields from '../../components/StaffPersonalFields.jsx'
import ApprovalSetting from '../../components/ApprovalSetting.jsx'
import { useEditGuard } from '../../components/EditGuardProvider.jsx'
import { useActionConfirmation } from '../../components/ActionConfirmationProvider.jsx'
import { ADMIN_APPROVAL_GROUPS } from '../../app/adminApprovals.js'
import { adminErrors, adminPayload } from '../../app/adminOnboarding.js'
import { formatDate } from '../../utils/date.js'

export default function AdminManagementPage({ services, selectedId, today, onNavigate, onBack, onCreate, creating = false }) {
  const [loaded, setLoaded] = useState(null)
  const selection = `${selectedId ?? 'list'}/${creating}`
  const records = loaded?.selection === selection ? loaded.value : null
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  const load = useEffectEvent(() => selectedId ? services.staffService.getById({ id: selectedId }) : services.staffService.getAll())
  useEffect(() => {
    let current = true
    setLoaded(null); setError('')
    load().then(value => { if (current) setLoaded({ selection, value }) }).catch(failure => { if (current) setError(failure.message) })
    return () => { current = false }
  }, [selectedId, revision, selection])
  if (!records) return <section aria-busy={!error}>{error ? <><p role="alert">{error}</p><button type="button" onClick={() => setRevision(value => value + 1)}>Retry</button></> : <p>Loading Admin details…</p>}</section>
  if (selectedId) return <AdminProfile key={selectedId} record={records} today={today} onBack={onBack} onSave={body => services.staffService.update({ id: selectedId, body })} onSaved={value => setLoaded({ selection, value })} />
  return <AdminDirectory records={records} onNavigate={onNavigate} onCreate={onCreate} />
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
      message: operation === 'deactivate' ? 'Existing sign-ins will end. The account and history will be retained.' : operation === 'reactivate' ? 'This Admin must sign in afresh. Existing approval requirements are retained.' : 'Save the reviewed Admin information?', confirmLabel: 'Confirm', danger: operation === 'deactivate' })) return
    setBusy(true); setErrors({}); setAttempt(body)
    try {
      const saved = await onSave(body)
      onSaved(saved); setAttempt(null); setEditor(null)
    } catch (failure) {
      setErrors({ save: failure.message })
      if (failure.status >= 400 && failure.status < 500) setAttempt(null)
    } finally { setBusy(false) }
  }
  const supervised = Object.values(record.approvalNeeded).filter(Boolean).length
  const heading = (label, kind) => <div className="section-head"><h2>{label}</h2><div className="inline-actions">
    {editor === kind ? <><button type="button" className="text-action" disabled={busy || Boolean(attempt)} onClick={() => { setEditor(null); setAttempt(null); setErrors({}) }}>Cancel</button>
      <button type="button" className="text-action" disabled={busy} onClick={() => save(kind)}>{busy ? 'Saving…' : attempt ? 'Retry Original Save' : 'Save'}</button></>
      : record.status === 'active' && <button type="button" className="text-action" disabled={Boolean(editor) || busy} onClick={() => begin(kind)}>Edit</button>}
  </div></div>
  return <>
    <button type="button" className="text-action" disabled={busy || Boolean(attempt)} onClick={() => guardNavigation(onBack)}>Back to Admin</button>
    <div className="page-head profile-identity-card"><div className="profile-identity-main"><ProfileAvatar name={record.details.name} /><div><span className="eyebrow">Admin</span><h1>{record.details.name}</h1></div></div>
      <div className="profile-card-statuses" aria-label="Admin status"><StatusBadge className="profile-autonomy-badge" tone={supervised ? 'amber' : 'green'}>{supervised ? `${supervised} approval controls` : 'Fully autonomous'}</StatusBadge><StatusBadge tone={record.status === 'active' ? 'green' : 'amber'}>{record.status === 'active' ? 'Active' : 'Inactive'}</StatusBadge></div>
    </div>
      <ProfileNavigation items={[["general", "General Details"], ["approvals", "Approval Requirements"], ["lifecycle", record.status === 'active' ? 'Deactivate' : 'Reactivate', record.status === 'active' ? 'profile-menu-danger' : '']]} activeKey={tab}
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
          {heading('Approval Requirements', 'approvals')}
          <div className="stack-gap">{ADMIN_APPROVAL_GROUPS.map(([group, fields]) => <section key={group} aria-label={group}>
            <h3>{group}</h3><div className="approval-grid">{fields.map(([key, label]) => <ApprovalSetting key={key} label={label} checked={editor === 'approvals' ? requirements[key] : record.approvalNeeded[key]} disabled={editor !== 'approvals' || busy || Boolean(attempt)} onChange={checked => setRequirements(value => ({ ...value, [key]: checked }))} />)}</div>
          </section>)}</div>
        </Panel>}
        {tab === 'lifecycle' && <Panel><h2>{record.status === 'active' ? 'Deactivate Admin' : 'Reactivate Admin'}</h2>
          <p>The account and its recorded history are retained. Reactivation requires a fresh sign-in.</p>
          <button type="button" className={record.status === 'active' ? 'danger-button' : 'secondary-button'} disabled={busy} onClick={() => save(record.status === 'active' ? 'deactivate' : 'reactivate')}>{attempt ? 'Retry Original Save' : record.status === 'active' ? 'Deactivate Admin' : 'Reactivate Admin'}</button>
        </Panel>}
        {errors.save && <p role="alert">{errors.save}</p>}
      </div>
  </>
}
