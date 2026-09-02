import { useEffect, useState } from 'react'
import Panel from '../../components/Panel.jsx'
import StatusBadge from '../../components/StatusBadge.jsx'
import ConfirmDialog from '../../components/ConfirmDialog.jsx'
import FixedWeeklySchedule from './FixedWeeklySchedule.jsx'
import { canEditClientCoachingNotes, canEditClientGeneral } from '../../app/permissions.js'
import { formatDate, packageDayProgress } from '../../utils/date.js'

function EditableText({ title, value, editable, multiline = false, onSave }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value)

  useEffect(() => setDraft(value), [value])

  const save = () => {
    onSave(draft)
    setEditing(false)
  }

  return (
    <Panel>
      <div className="section-head">
        <h2>{title}</h2>

        {editable && (!editing ? (
          <button type="button" className="text-action" onClick={() => setEditing(true)}>
            Edit
          </button>
        ) : (
          <div className="inline-actions">
            <button
              type="button"
              className="text-action muted-action"
              onClick={() => {
                setDraft(value)
                setEditing(false)
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
  onBack,
  onUpdate,
  onSaveFixedWeeklySchedule,
  onDeactivate,
  onReactivate,
}) {
  const [editingGeneral, setEditingGeneral] = useState(false)
  const [draft, setDraft] = useState(client)
  const [deactivateOpen, setDeactivateOpen] = useState(false)

  useEffect(() => {
    setDraft(client)
    setEditingGeneral(false)
  }, [client])

  const ownerEditable = canEditClientGeneral(user)
  const notesEditable = canEditClientCoachingNotes(user, client)

  const assignedTrainerEditable =
    user.role === 'trainer' &&
    user.trainerId === client.trainerId &&
    client.status !== 'inactive'

  const scheduleEditable =
    user.role === 'owner' ||
    assignedTrainerEditable

  const progress = packageDayProgress(
    client.package.startDate,
    client.package.validityDays,
  )

  const saveGeneral = () => {
    onUpdate({
      phone: draft.phone,
      email: draft.email,
      birthday: draft.birthday,
      gender: draft.gender,
      emergencyContact: draft.emergencyContact,
    })
    setEditingGeneral(false)
  }

  return (
    <>
      <div className="page-head profile-identity-card">
        <div>
          <span className="eyebrow">Client profile</span>
          <h1>{client.name}</h1>

          <div className="profile-status-line" aria-label="Client status">
            <StatusBadge tone={client.status === 'inactive' ? 'amber' : 'green'}>
              {client.status === 'inactive' ? 'Inactive' : 'Active'}
            </StatusBadge>
          </div>
        </div>
      </div>

      <details
        className="profile-menu"
        onClick={event => {
          if (
            event.target === event.currentTarget ||
            event.target.closest('button')
          ) {
            event.currentTarget.removeAttribute('open')
          }
        }}
      >
        <summary>Profile Menu</summary>

        <div className="profile-tabs">
          <button className="active" type="button">Overview</button>
          <button type="button" disabled>Package</button>
          <button type="button" disabled>Session History</button>
          <button type="button" disabled>Upcoming Sessions</button>
          <button type="button" disabled>Progress</button>

          {user.role === 'owner' && client.status !== 'inactive' && (
            <button
              type="button"
              className="profile-menu-danger"
              onClick={() => setDeactivateOpen(true)}
            >
              Deactivate Client
            </button>
          )}

          {user.role === 'owner' && client.status === 'inactive' && (
            <button
              type="button"
              className="profile-menu-reactivate"
              onClick={onReactivate}
            >
              Reactivate Client
            </button>
          )}
        </div>
      </details>

      <div className="two-column">
        <Panel>
          <div className="section-head">
            <h2>General Information</h2>

            {ownerEditable && (!editingGeneral ? (
              <button
                type="button"
                className="text-action"
                onClick={() => setEditingGeneral(true)}
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
                    setEditingGeneral(false)
                  }}
                >
                  Cancel
                </button>
                <button type="button" className="text-action" onClick={saveGeneral}>Save</button>
              </div>
            ))}
          </div>

          <div className="info-list">
            {[
              ['Phone', 'phone', 'text'],
              ['Email', 'email', 'email'],
              ['Birthday', 'birthday', 'date'],
              ['Gender', 'gender', 'text'],
              ['Emergency contact', 'emergencyContact', 'text'],
            ].map(([label, key, type]) => (
              <div className="info-row" key={key}>
                <span>{label}</span>

                {editingGeneral
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

            <div className="info-row">
              <span>Start date</span>
              <strong>{formatDate(client.startDate)}</strong>
            </div>

            <div className="info-row">
              <span>Trainer</span>
              <strong>{trainer?.name ?? '—'}</strong>
            </div>

            <div className="info-row">
              <span>Package validity</span>
              <strong>{progress} / {client.package.validityDays} days</strong>
            </div>

            <div className="info-row">
              <span>Trainer preference</span>
              <strong>{client.trainerPreference}</strong>
            </div>
          </div>
        </Panel>

        <FixedWeeklySchedule
          slots={client.fixedWeeklySchedule}
          editable={scheduleEditable}
          onSave={onSaveFixedWeeklySchedule}
        />
      </div>

      <div className="stack-gap">
        <EditableText
          title="Health / Limitation Notes"
          value={client.healthNotes}
          editable={notesEditable}
          multiline
          onSave={healthNotes => onUpdate({ healthNotes })}
        />

        <EditableText
          title="Remarks"
          value={client.remarks}
          editable={notesEditable}
          multiline
          onSave={remarks => onUpdate({ remarks })}
        />
      </div>

      <ConfirmDialog
        open={deactivateOpen}
        title={`Deactivate ${client.name}?`}
        confirmLabel="Deactivate Client"
        danger
        onCancel={() => setDeactivateOpen(false)}
        onConfirm={async () => {
          await onDeactivate()
          setDeactivateOpen(false)
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
