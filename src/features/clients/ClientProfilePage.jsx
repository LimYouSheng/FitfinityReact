import ClientGeneralFields from './ClientGeneralFields.jsx'
import { clientProfileDraft, clientStepErrors } from '../../app/clientOnboarding.js'
import ReassignTrainerDialog from './ReassignTrainerDialog.jsx'
import usePageState from '../../hooks/usePageState.js'
import { useEffect, useRef, useState } from 'react'
import Panel from '../../components/Panel.jsx'
import StatusBadge from '../../components/StatusBadge.jsx'
import ConfirmDialog from '../../components/ConfirmDialog.jsx'
import ProfileAvatar from '../../components/ProfileAvatar.jsx'
import ProfileNavigation from '../../components/ProfileNavigation.jsx'
import { useActionConfirmation } from '../../components/ActionConfirmationProvider.jsx'
import { useEditGuard } from '../../components/EditGuardProvider.jsx'
import FixedWeeklySchedule from './FixedWeeklySchedule.jsx'
import ClientProfileTabs from './ClientProfileTabs.jsx'
import { canEditClientCoachingNotes, canEditClientGeneral } from '../../app/permissions.js'
import { formatDate } from '../../utils/date.js'

function displayPhone(phone) {
  if (!phone) return '—'
  return typeof phone === 'string' ? phone : `${phone.countryCode} ${phone.number}`.trim()
}

function displayEmergency(contact) {
  if (!contact) return '—'
  if (typeof contact === 'string') return contact
  return [contact.name, contact.relationship, displayPhone(contact)].filter(Boolean).join(' · ')
}

function EditableText({ title, value, editable, multiline = false, editing, editDisabled, onBeginEdit, onEndEdit, onSave }) {
  const confirmAction = useActionConfirmation()
  const [draft, setDraft] = useState(value)

  useEffect(() => setDraft(value), [value])

  const save = async () => {
    const confirmed = await confirmAction({
      title: `Save ${title.toLowerCase()}?`,
      message: `This will replace the client’s current ${title.toLowerCase()}.`,
      confirmLabel: 'Save Changes',
    })
    if (!confirmed) return
    try {
      await onSave(draft)
      onEndEdit()
    } catch { /* The action banner reports failure; keep the draft open. */ }
  }

  return (
    <Panel className={editing ? 'editing-section' : ''}>
      <div className="section-head">
        <h2>{title}</h2>

        {editable && (!editing ? (
          <button type="button" className="text-action" disabled={editDisabled} onClick={onBeginEdit}>
            Edit
          </button>
        ) : (
          <div className="inline-actions">
            <button
              type="button"
              className="text-action muted-action"
              onClick={() => {
                setDraft(value)
                onEndEdit()
              }}
            >
              Cancel
            </button>
            <button type="button" className="text-action" onClick={save}>Save</button>
          </div>
        ))}
      </div>

      {editing
        ? (
          multiline
            ? <textarea value={draft} onChange={event => setDraft(event.target.value)} />
            : <input value={draft} onChange={event => setDraft(event.target.value)} />
        )
        : <div className="notice">{value}</div>}
    </Panel>
  )
}

export default function ClientProfilePage({
  user,
  client,
  trainer,
  trainers,
  sessions,
  today,
  onOpenSession,
  progressRoute = false,
  progressPackageId,
  onOpenProgressPackage,
  onSelectProfileTab,
  onBack,
  onUpdate,
  timeZone,
  onRecordProgressReport,
  onLoadProgressReportHistory,
  onSaveFixedWeeklySchedule,
  onReassignTrainer,
  onDeactivate,
  onReactivate,
  packages,
  policy,
  onRenewPackage,
  onDeactivatePackage,
  onDeletePackageSessions,
  packageCreditTransactions,
}) {
  const confirmAction = useActionConfirmation()
  const { guardNavigation, setActiveEdit } = useEditGuard()
  const [savedTab, setTab] = usePageState(`client.${client.id}.tab`, 'overview')
  const tab = progressRoute ? 'progress' : savedTab
  const [activeEditor, setActiveEditor] = useState(null)
  const [draft, setDraft] = useState(() => clientProfileDraft(client, policy))
  const [activePerson, setActivePerson] = useState(0)
  const [generalErrors, setGeneralErrors] = useState({})
  const generalFields = useRef(null)
  const [deactivateOpen, setDeactivateOpen] = useState(false)

  useEffect(() => {
    setDraft(clientProfileDraft(client, policy))
    setActiveEditor(null)
  }, [client.id, client.status])

  useEffect(() => {
    if (!activeEditor) setDraft(clientProfileDraft(client, policy))
  }, [activeEditor, client])

  useEffect(() => {
    const label = ({ general: 'Client information', trainer: 'Trainer reassignment', schedule: 'Fixed weekly schedule', health: 'Health notes', remarks: 'Client remarks' })[activeEditor] ?? null
    setActiveEdit(label)
    return () => setActiveEdit(null)
  }, [activeEditor, setActiveEdit])

  const ownerEditable = canEditClientGeneral(user, client)
  const notesEditable = canEditClientCoachingNotes(user, client)

  const assignedTrainerEditable =
    user.role === 'trainer' &&
    user.trainerId === client.trainerId &&
    client.status !== 'inactive'

  const scheduleEditable =
    client.status !== 'inactive' && (user.role === 'owner' || assignedTrainerEditable)

  const saveGeneral = async () => {
    const errors = clientStepErrors(draft, 'general', { requireComplete: false })
    if (Object.keys(errors).length) {
      setGeneralErrors(errors)
      setActivePerson(Number(Object.keys(errors)[0].split('.')[1]) || 0)
      return
    }
    const confirmed = await confirmAction({
      title: 'Save client information?',
      message: 'This will update the client’s contact and personal information.',
      confirmLabel: 'Save Changes',
    })
    if (!confirmed) return
    try {
      await onUpdate({
        people: draft.people,
        remarks: draft.remarks,
        genderPreference: draft.genderPreference,
      })
      setActiveEditor(null)
    } catch (error) { setGeneralErrors({ save: error.message || 'Client information could not be saved.' }) }
  }

  useEffect(() => {
    if (Object.keys(generalErrors).length) generalFields.current?.querySelector('[aria-invalid="true"]')?.focus()
  }, [generalErrors, activePerson])

  return (
    <>
      <div className="page-head profile-identity-card">
        <div className="profile-identity-main">
          <ProfileAvatar name={client.name} />

          <div>
            <span className="eyebrow">Client</span>
            <h1>{client.name}</h1>
          </div>
        </div>

        <div className="profile-card-statuses" aria-label="Client status">
          <StatusBadge tone={client.status === 'inactive' ? 'amber' : 'green'}>
            {client.status === 'inactive' ? 'Inactive' : 'Active'}
          </StatusBadge>
        </div>
      </div>

      <ProfileNavigation
        items={[
            ['overview', 'Overview'],
            ['package', 'Package'],
            ['history', 'Session History'],
            ['upcoming', 'Upcoming Sessions'],
            ['progress', 'Progress'],
        ]}
        activeKey={tab}
        onSelect={key => guardNavigation(() => {
          setActiveEditor(null)
          setTab(key)
          onSelectProfileTab?.(key)
        })}
      >

          {user.role === 'owner' && client.status !== 'inactive' && (
            <button
              type="button"
              className="profile-menu-danger"
              disabled={Boolean(activeEditor)}
              onClick={() => setDeactivateOpen(true)}
            >
              Deactivate Client
            </button>
          )}

          {user.role === 'owner' && client.status === 'inactive' && (
            <button
              type="button"
              className="profile-menu-reactivate"
              disabled={Boolean(activeEditor)}
              onClick={async () => {
                const confirmed = await confirmAction({
                  title: `Reactivate ${client.name}?`,
                  message: 'Packages disabled with this client and their retained sessions will become active again. Separately deactivated packages stay inactive; deleted sessions cannot be restored.',
                  confirmLabel: 'Reactivate Client',
                })
                if (confirmed) {
                  try { await onReactivate() } catch { /* Failure is shown in the action banner. */ }
                }
              }}
            >
              Reactivate Client
            </button>
          )}
      </ProfileNavigation>

      {activeEditor === 'trainer' && ownerEditable && <ReassignTrainerDialog client={client} trainers={trainers} sessions={sessions}
        packageCreditTransactions={packageCreditTransactions} timeZone={timeZone} onSave={onReassignTrainer} onClose={() => setActiveEditor(null)} />}

      {tab === 'overview' && <>
      <div className="profile-overview-stack">
        <Panel className={activeEditor === 'general' ? 'editing-section' : ''}>
          <div className="section-head">
            <h2>General Information</h2>

            {ownerEditable && (activeEditor !== 'general' ? (
              <button
                type="button"
                className="text-action"
                disabled={Boolean(activeEditor)}
                onClick={() => { setGeneralErrors({}); setActivePerson(0); setActiveEditor('general') }}
              >
                Edit
              </button>
            ) : (
              <div className="inline-actions">
                <button
                  type="button"
                  className="text-action muted-action"
                  onClick={() => {
                    setDraft(clientProfileDraft(client, policy))
                    setActiveEditor(null)
                  }}
                >
                  Cancel
                </button>
                <button type="button" className="text-action" onClick={saveGeneral}>Save</button>
              </div>
            ))}
          </div>

          {activeEditor === 'general' ? <div ref={generalFields}>
            {client.type === 'Couple' && client.people?.length !== 2 && <p className="helper">This older couple profile has one combined record. Review both clients’ names and details before saving.</p>}
            <ClientGeneralFields editing draft={draft} errors={generalErrors} activePerson={activePerson} setActivePerson={setActivePerson}
              onChange={patch => { setDraft(current => ({ ...current, ...patch })); setGeneralErrors({}) }} />
            {generalErrors.save && <p role="alert">{generalErrors.save}</p>}
          </div> : <div className="info-list profile-info-grid">
            <div className="info-row"><span>Name</span><strong>{client.name}</strong></div>
            <div className="info-row"><span>Phone</span><strong>{displayPhone(client.phone)}</strong></div>
            {[['Email', 'email'], ['Birthday', 'birthday'], ['Gender', 'gender']].map(([label, key]) => (
              <div className="info-row" key={key}><span>{label}</span><strong>{key === 'birthday' ? formatDate(client[key]) : client[key]}</strong></div>
            ))}
            <div className="info-row emergency-contact-row"><span>Emergency contact</span><strong>{displayEmergency(client.emergencyContact)}</strong></div>
            <div className="info-row"><span>Gender preference</span><strong>{client.genderPreference}</strong></div>

            <div className="info-row">
              <span>Start date</span>
              <strong>{formatDate(client.startDate)}</strong>
            </div>

            <div className="info-row client-trainer-row">
              <span>Trainer</span>
              <div className="client-trainer-assignment"><strong>{trainer?.name ?? '—'}</strong>
                {ownerEditable && <button type="button" className="text-action" disabled={Boolean(activeEditor)} onClick={() => setActiveEditor('trainer')}>Reassign Trainer</button>}
              </div>
            </div>

          </div>}
        </Panel>

        <FixedWeeklySchedule
          slots={client.fixedWeeklySchedule}
          editable={scheduleEditable}
          editing={activeEditor === 'schedule'}
          editDisabled={Boolean(activeEditor)}
          onBeginEdit={() => setActiveEditor('schedule')}
          onEndEdit={() => setActiveEditor(null)}
          onSave={onSaveFixedWeeklySchedule}
        />
      </div>

      <div className="stack-gap">
        <EditableText
          title="Health / Limitation Notes"
          value={client.healthNotes}
          editable={notesEditable}
          multiline
          editing={activeEditor === 'health'}
          editDisabled={Boolean(activeEditor)}
          onBeginEdit={() => setActiveEditor('health')}
          onEndEdit={() => setActiveEditor(null)}
          onSave={healthNotes => onUpdate({ healthNotes })}
        />

        <EditableText
          title="Remarks"
          value={client.remarks}
          editable={notesEditable}
          multiline
          editing={activeEditor === 'remarks'}
          editDisabled={Boolean(activeEditor)}
          onBeginEdit={() => setActiveEditor('remarks')}
          onEndEdit={() => setActiveEditor(null)}
          onSave={remarks => onUpdate({ remarks })}
        />
      </div>
      </>}

      {tab !== 'overview' && (
        <ClientProfileTabs
          progressPackageId={progressPackageId}
          onOpenProgressPackage={onOpenProgressPackage}
          packages={packages}
          policy={policy}
          onRenewPackage={onRenewPackage}
          onDeactivatePackage={onDeactivatePackage}
          onDeletePackageSessions={onDeletePackageSessions}
          packageCreditTransactions={packageCreditTransactions}
          tab={tab}
          user={user}
          timeZone={timeZone}
          onRecordProgressReport={onRecordProgressReport}
          onLoadProgressReportHistory={onLoadProgressReportHistory}
          client={client}
          sessions={sessions}
          today={today}
          trainers={trainers}
          onOpenSession={onOpenSession}
        />
      )}

      <ConfirmDialog
        open={deactivateOpen}
        title={`Deactivate ${client.name}?`}
        confirmLabel="Deactivate Client"
        danger
        onCancel={() => setDeactivateOpen(false)}
        onConfirm={async () => {
          try {
            await onDeactivate()
            setDeactivateOpen(false)
          } catch { /* Failure is shown in the action banner; keep the dialog open. */ }
        }}
      >
        <p>
          The client will become inactive, move to the bottom of Clients,
          and remain visible to the assigned trainer. All packages are deactivated. Client information and sessions become read-only.
        </p>
      </ConfirmDialog>
    </>
  )
}
