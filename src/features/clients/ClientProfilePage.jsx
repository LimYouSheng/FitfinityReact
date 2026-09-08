import { COUNTRY_CODES, RELATIONSHIPS, GENDER_PREFERENCES } from '../../app/contact.js'
import { useEffect, useState } from 'react'
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
  onBack,
  onUpdate,
  onSaveFixedWeeklySchedule,
  onDeactivate,
  onReactivate,
}) {
  const confirmAction = useActionConfirmation()
  const { guardNavigation, setActiveEdit } = useEditGuard()
  const [tab, setTab] = useState('overview')
  const [activeEditor, setActiveEditor] = useState(null)
  const [draft, setDraft] = useState(client)
  const [deactivateOpen, setDeactivateOpen] = useState(false)

  useEffect(() => {
    setDraft(client)
    setActiveEditor(null)
    setTab('overview')
  }, [client.id])

  useEffect(() => {
    if (!activeEditor) setDraft(client)
  }, [activeEditor, client])

  useEffect(() => {
    const label = ({ general: 'Client information', schedule: 'Fixed weekly schedule', health: 'Health notes', remarks: 'Client remarks' })[activeEditor] ?? null
    setActiveEdit(label)
    return () => setActiveEdit(null)
  }, [activeEditor, setActiveEdit])

  const ownerEditable = canEditClientGeneral(user)
  const notesEditable = canEditClientCoachingNotes(user, client)

  const assignedTrainerEditable =
    user.role === 'trainer' &&
    user.trainerId === client.trainerId &&
    client.status !== 'inactive'

  const scheduleEditable =
    user.role === 'owner' ||
    assignedTrainerEditable

  const saveGeneral = async () => {
    const confirmed = await confirmAction({
      title: 'Save client information?',
      message: 'This will update the client’s contact and personal information.',
      confirmLabel: 'Save Changes',
    })
    if (!confirmed) return
    try {
      await onUpdate({
        phone: draft.phone,
        email: draft.email,
        birthday: draft.birthday,
        gender: draft.gender,
        emergencyContact: draft.emergencyContact,
        genderPreference: draft.genderPreference,
      })
      setActiveEditor(null)
    } catch { /* The action banner reports failure; keep the draft open. */ }
  }

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
                  message: 'The client will return to active client lists and can be scheduled for sessions again.',
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
                onClick={() => setActiveEditor('general')}
              >
                Edit
              </button>
            ) : (
              <div className="inline-actions">
                <button
                  type="button"
                  className="text-action muted-action"
                  onClick={() => {
                    setDraft(client)
                    setActiveEditor(null)
                  }}
                >
                  Cancel
                </button>
                <button type="button" className="text-action" onClick={saveGeneral}>Save</button>
              </div>
            ))}
          </div>

          <div className="info-list profile-info-grid">
            <div className="info-row">
              <span>Phone</span>
              {activeEditor === 'general' ? (
                <div className="contact-number-fields">
                  <select
                    aria-label="Phone country extension"
                    value={draft.phone.countryCode}
                    onChange={event => setDraft(current => ({
                      ...current,
                      phone: { ...current.phone, countryCode: event.target.value },
                    }))}
                  >
                    {COUNTRY_CODES.map(code => <option key={code}>{code}</option>)}
                  </select>
                  <input
                    aria-label="Phone number"
                    inputMode="tel"
                    value={draft.phone.number}
                    onChange={event => setDraft(current => ({
                      ...current,
                      phone: { ...current.phone, number: event.target.value },
                    }))}
                  />
                </div>
              ) : <strong>{displayPhone(client.phone)}</strong>}
            </div>

            {[
              ['Email', 'email', 'email'],
              ['Birthday', 'birthday', 'date'],
              ['Gender', 'gender', 'text'],
            ].map(([label, key, type]) => (
              <div className="info-row" key={key}>
                <span>{label}</span>

                {activeEditor === 'general'
                  ? (
                    <input
                      aria-label={label}
                      type={type}
                      value={draft[key]}
                      onChange={event =>
                        setDraft(current => ({
                          ...current,
                          [key]: event.target.value,
                        }))
                      }
                    />
                  )
                  : <strong>{key === 'birthday' ? formatDate(client[key]) : client[key]}</strong>}
              </div>
            ))}

            <div className="info-row emergency-contact-row">
              <span>Emergency contact</span>
              {activeEditor === 'general' ? (
                <div className="emergency-contact-fields">
                  <input
                    aria-label="Emergency contact name"
                    value={draft.emergencyContact.name}
                    onChange={event => setDraft(current => ({
                      ...current,
                      emergencyContact: { ...current.emergencyContact, name: event.target.value },
                    }))}
                  />
                  <select
                    aria-label="Emergency contact relationship"
                    value={draft.emergencyContact.relationship}
                    onChange={event => setDraft(current => ({
                      ...current,
                      emergencyContact: { ...current.emergencyContact, relationship: event.target.value },
                    }))}
                  >
                    {RELATIONSHIPS.map(relationship => <option key={relationship}>{relationship}</option>)}
                  </select>
                  <select
                    aria-label="Emergency contact country extension"
                    value={draft.emergencyContact.countryCode}
                    onChange={event => setDraft(current => ({
                      ...current,
                      emergencyContact: { ...current.emergencyContact, countryCode: event.target.value },
                    }))}
                  >
                    {COUNTRY_CODES.map(code => <option key={code}>{code}</option>)}
                  </select>
                  <input
                    aria-label="Emergency contact phone number"
                    inputMode="tel"
                    value={draft.emergencyContact.number}
                    onChange={event => setDraft(current => ({
                      ...current,
                      emergencyContact: { ...current.emergencyContact, number: event.target.value },
                    }))}
                  />
                </div>
              ) : <strong>{displayEmergency(client.emergencyContact)}</strong>}
            </div>

            <div className="info-row">
              <span>Gender preference</span>
              {activeEditor === 'general' ? (
                <select
                  aria-label="Gender preference"
                  value={draft.genderPreference}
                  onChange={event => setDraft(current => ({ ...current, genderPreference: event.target.value }))}
                >
                  {GENDER_PREFERENCES.map(preference => <option key={preference}>{preference}</option>)}
                </select>
              ) : <strong>{client.genderPreference}</strong>}
            </div>

            <div className="info-row">
              <span>Start date</span>
              <strong>{formatDate(client.startDate)}</strong>
            </div>

            <div className="info-row">
              <span>Trainer</span>
              <strong>{trainer?.name ?? '—'}</strong>
            </div>

          </div>
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
          tab={tab}
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
          The client will become inactive, move to the bottom of All Clients,
          and disappear from the assigned trainer's active client view.
        </p>
      </ConfirmDialog>
    </>
  )
}
