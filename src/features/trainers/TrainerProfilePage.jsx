import { useEffect, useMemo, useState } from 'react'
import { APPROVAL_FIELDS, DAYS } from '../../app/constants.js'
import { activeTrainers, remainingTrainerSessions } from '../../app/status.js'
import ApprovalSetting from '../../components/ApprovalSetting.jsx'
import ConfirmDialog from '../../components/ConfirmDialog.jsx'
import Panel from '../../components/Panel.jsx'
import StatusBadge from '../../components/StatusBadge.jsx'
import { formatDate } from '../../utils/date.js'

function formatTime(value) {
  const [hour, minute] = value.split(':').map(Number)
  const period = hour >= 12 ? 'pm' : 'am'
  const h = hour % 12 || 12
  return `${h}:${String(minute).padStart(2, '0')}${period}`
}

function AvailabilityGrid({ availability }) {
  return (
    <div className="availability-grid">
      {DAYS.map(day => {
        const blocks = availability?.[day] ?? []
        return (
          <div className="availability-day" key={day}>
            <strong>{day.slice(0, 3).toUpperCase()}</strong>
            {blocks.length
              ? blocks.map(([from, to], index) => (
                  <span className="availability-block" key={`${day}-${index}`}>
                    {formatTime(from)}–{formatTime(to)}
                  </span>
                ))
              : <span className="availability-empty">Unavailable</span>}
          </div>
        )
      })}
    </div>
  )
}

export default function TrainerProfilePage({
  viewer,
  trainer,
  trainers,
  clients,
  sessions,
  onBack,
  onOpenClient,
  onSaveAutonomy,
  onUpdate,
  onDeactivate,
  onReactivate,
}) {
  const isOwner = viewer.role === 'owner'
  const [tab, setTab] = useState('overview')
  const [editingGeneral, setEditingGeneral] = useState(false)
  const [generalDraft, setGeneralDraft] = useState(trainer)
  const [editingRates, setEditingRates] = useState(false)
  const [ratesDraft, setRatesDraft] = useState(trainer.rates)
  const [editingAutonomy, setEditingAutonomy] = useState(false)
  const [autonomyDraft, setAutonomyDraft] = useState(trainer.approvalNeeded)
  const [deactivateOpen, setDeactivateOpen] = useState(false)
  const [replacements, setReplacements] = useState({})

  useEffect(() => {
    setGeneralDraft(trainer)
    setRatesDraft(trainer.rates)
    setAutonomyDraft(trainer.approvalNeeded)
    setTab('overview')
  }, [trainer])

  const supervised = Object.values(trainer.approvalNeeded).filter(Boolean).length
  const assignedClients = clients.filter(client =>
    (client.status ?? 'active') === 'active' &&
    client.trainerId === trainer.id
  )

  const remaining = useMemo(
    () => remainingTrainerSessions(trainer.id, sessions),
    [trainer.id, sessions]
  )

  const selectableReplacements = activeTrainers(trainers).filter(item => item.id !== trainer.id)
  const allAssigned = remaining.every(session => replacements[session.id])

  const saveGeneral = async () => {
    await onUpdate({
      phone: generalDraft.phone,
      email: generalDraft.email,
      birthday: generalDraft.birthday,
      gender: generalDraft.gender,
      trainerType: generalDraft.trainerType,
      qualifications: generalDraft.qualifications,
      publicProfile: generalDraft.publicProfile,
    })
    setEditingGeneral(false)
  }

  const saveRates = async () => {
    await onUpdate({
      rates: {
        peak: Number(ratesDraft.peak),
        offPeak: Number(ratesDraft.offPeak),
      },
    })
    setEditingRates(false)
  }

  return (
    <>
      <div className="page-head profile-identity-card">
        <div>
          <span className="eyebrow">{isOwner ? 'Trainer profile' : 'My profile'}</span>
          <h1>{trainer.name}</h1>

          <div className="profile-status-line" aria-label="Trainer status">
            <StatusBadge tone={trainer.status === 'inactive' ? 'amber' : 'green'}>
              {trainer.status === 'inactive' ? 'Inactive' : 'Active'}
            </StatusBadge>
          </div>
        </div>

        <div className="page-actions">
          <StatusBadge tone={trainer.status === 'inactive' ? 'amber' : supervised ? 'amber' : 'green'}>
            {trainer.status === 'inactive'
              ? 'Inactive'
              : supervised
                ? `${supervised} approval controls`
                : 'Fully autonomous'}
          </StatusBadge>
        </div>
      </div>

      <details className="profile-menu" onClick={event => { if (event.target === event.currentTarget || event.target.closest('button')) event.currentTarget.removeAttribute('open') }}>
        <summary>Profile Menu</summary>
        <div className="profile-tabs">
        {[
          ['overview', 'Overview'],
          ['availability', 'Availability'],
          ['clients', 'Assigned Clients'],
          ['autonomy', 'Autonomy & Approvals'],
          ['activity', 'Monthly Activity'],
        ].map(([key, label]) => (
          <button key={key} type="button" className={tab === key ? 'active' : ''} onClick={() => setTab(key)}>
            {label}
          </button>
        ))}
      
          {isOwner && trainer.status !== 'inactive' && (
            <button type="button" className="profile-menu-danger" onClick={() => setDeactivateOpen(true)}>
              Deactivate Trainer
            </button>
          )}

          {isOwner && trainer.status === 'inactive' && (
            <button type="button" className="profile-menu-reactivate" onClick={onReactivate}>
              Reactivate Trainer
            </button>
          )}
      </div>
      </details>

      {tab === 'overview' && (
        <div className="two-column">
          <Panel>
            <div className="section-head">
              <div><h2>General Information</h2></div>
              {isOwner && (!editingGeneral ? (
                <button type="button" className="text-action" onClick={() => setEditingGeneral(true)}>Edit</button>
              ) : (
                <div className="inline-actions">
                  <button type="button" className="text-action muted-action" onClick={() => {
                    setGeneralDraft(trainer)
                    setEditingGeneral(false)
                  }}>Cancel</button>
                  <button type="button" className="text-action" onClick={saveGeneral}>Save</button>
                </div>
              ))}
            </div>

            <div className="info-list">
              {[
                ['Mobile Number', 'phone', 'text'],
                ['Email', 'email', 'email'],
                ['Birthday', 'birthday', 'date'],
                ['Gender', 'gender', 'text'],
                ['Trainer type', 'trainerType', 'text'],
                ['Qualifications', 'qualifications', 'text'],
              ].map(([label, key, type]) => (
                <div className="info-row" key={key}>
                  <span>{label}</span>
                  {editingGeneral
                    ? <input aria-label={label} type={type} value={generalDraft[key]} onChange={event => setGeneralDraft(current => ({ ...current, [key]: event.target.value }))} />
                    : <strong>{key === 'birthday' ? formatDate(trainer[key]) : trainer[key]}</strong>}
                </div>
              ))}

              <div className="info-row">
                <span>Public profile</span>
                {editingGeneral
                  ? (
                    <select
                      aria-label="Public profile"
                      value={generalDraft.publicProfile}
                      onChange={event => setGeneralDraft(current => ({ ...current, publicProfile: event.target.value }))}
                    >
                      <option>Visible</option>
                      <option>Hidden</option>
                    </select>
                  )
                  : <strong>{trainer.publicProfile}</strong>}
              </div>
            </div>
          </Panel>

          <Panel>
            <div className="section-head">
              <h2>Training & Rates</h2>

              {isOwner && (!editingRates ? (
                <button type="button" className="text-action" onClick={() => setEditingRates(true)}>Edit</button>
              ) : (
                <div className="inline-actions">
                  <button
                    type="button"
                    className="text-action muted-action"
                    onClick={() => {
                      setRatesDraft(trainer.rates)
                      setEditingRates(false)
                    }}
                  >
                    Cancel
                  </button>
                  <button type="button" className="text-action" onClick={saveRates}>Save</button>
                </div>
              ))}
            </div>

            <div className="info-list">
              <div className="info-row">
                <span>Assigned clients</span>
                <strong>{assignedClients.length}</strong>
              </div>

              <div className="info-row">
                <span>Peak rate</span>
                {editingRates
                  ? (
                    <input
                      aria-label="Peak rate"
                      type="number"
                      min="0"
                      step="1"
                      value={ratesDraft.peak}
                      onChange={event => setRatesDraft(current => ({
                        ...current,
                        peak: event.target.value,
                      }))}
                    />
                  )
                  : <strong>${trainer.rates.peak} / session</strong>}
              </div>

              <div className="info-row">
                <span>Off-peak rate</span>
                {editingRates
                  ? (
                    <input
                      aria-label="Off-peak rate"
                      type="number"
                      min="0"
                      step="1"
                      value={ratesDraft.offPeak}
                      onChange={event => setRatesDraft(current => ({
                        ...current,
                        offPeak: event.target.value,
                      }))}
                    />
                  )
                  : <strong>${trainer.rates.offPeak} / session</strong>}
              </div>
            </div>
          </Panel>
        </div>
      )}

      {tab === 'availability' && (
        <Panel>
          <div className="section-head">
            <div>
              <h2>Approved Availability</h2>
            </div>
            {!isOwner && <button type="button" className="text-action" disabled>Request Change — later migration</button>}
          </div>
          <AvailabilityGrid availability={trainer.availability} />
          {isOwner && <p className="helper">Owner view is read-only by design. Trainer availability changes will route through Messages/request approval logic when that workflow is migrated.</p>}
        </Panel>
      )}

      {tab === 'clients' && (
        <Panel>
          <div className="section-head">
            <div><h2>Assigned Clients</h2></div>
          </div>

          <div className="quick-list">
            {assignedClients.map(client => (
              <div className="quick-row" key={client.id}>
                <div><strong>{client.name}</strong><span>{client.type} • {client.package.total} sessions</span></div>
                <button type="button" className="btn small" onClick={() => onOpenClient(client.id)}>View</button>
              </div>
            ))}
            {!assignedClients.length && <div className="empty">No active assigned clients.</div>}
          </div>
        </Panel>
      )}

      {tab === 'autonomy' && (
        <Panel>
          <div className="section-head">
            <div>
              <h2>Owner Approval Needed</h2>
            </div>

            {isOwner && (!editingAutonomy ? (
              <button type="button" className="text-action" onClick={() => setEditingAutonomy(true)}>Edit</button>
            ) : (
              <div className="inline-actions">
                <button type="button" className="text-action muted-action" onClick={() => {
                  setAutonomyDraft(trainer.approvalNeeded)
                  setEditingAutonomy(false)
                }}>Cancel</button>
                <button type="button" className="text-action" onClick={async () => {
                  await onSaveAutonomy(autonomyDraft)
                  setEditingAutonomy(false)
                }}>Save</button>
              </div>
            ))}
          </div>

          <div className="approval-grid">
            {APPROVAL_FIELDS.map(([field, label]) => (
              <ApprovalSetting
                key={field}
                label={label}
                checked={(editingAutonomy ? autonomyDraft : trainer.approvalNeeded)[field]}
                disabled={!isOwner || !editingAutonomy}
                onChange={checked => setAutonomyDraft(current => ({ ...current, [field]: checked }))}
              />
            ))}
          </div>

          <p className="helper">Uncheck and save = that change is allowed directly.</p>
        </Panel>
      )}

      {tab === 'activity' && (
        <div className="stats-grid four">
          <Panel><span>Completed Sessions</span><strong>{trainer.monthlyActivity.sessions}</strong></Panel>
          <Panel><span>Training Hours</span><strong>{trainer.monthlyActivity.hours}</strong></Panel>
          <Panel><span>Peak Sessions</span><strong>{trainer.monthlyActivity.peak}</strong></Panel>
          <Panel><span>Off-Peak Sessions</span><strong>{trainer.monthlyActivity.offPeak}</strong></Panel>
        </div>
      )}

      <ConfirmDialog
        open={deactivateOpen}
        title={`Deactivate ${trainer.name}?`}
        confirmLabel="Deactivate Trainer"
        danger
        confirmDisabled={!allAssigned}
        onCancel={() => {
          setDeactivateOpen(false)
          setReplacements({})
        }}
        onConfirm={async () => {
          await onDeactivate(replacements)
          setDeactivateOpen(false)
          setReplacements({})
        }}
      >
        <p>
          An inactive trainer will immediately stop appearing in active trainer lists and availability matching.
          Any remaining tagged sessions must be reassigned first.
        </p>

        {remaining.length > 0 ? (
          <div className="reassign-list">
            {remaining.map(session => {
              const client = clients.find(item => item.id === session.clientId)
              return (
                <div className="reassign-row" key={session.id}>
                  <div>
                    <strong>{client?.name ?? 'Client'}</strong>
                    <span>{formatDate(session.date)} • {formatTime(session.from)}–{formatTime(session.to)}</span>
                  </div>
                  <label>
                    <span>Reassign to</span>
                    <select
                      aria-label={`Reassign ${client?.name ?? session.id}`}
                      value={replacements[session.id] ?? ''}
                      onChange={event => setReplacements(current => ({
                        ...current,
                        [session.id]: event.target.value,
                      }))}
                    >
                      <option value="">Choose active trainer</option>
                      {selectableReplacements.map(item => (
                        <option key={item.id} value={item.id}>{item.name}</option>
                      ))}
                    </select>
                  </label>
                </div>
              )
            })}
          </div>
        ) : (
          <div className="notice">No remaining sessions are tagged to this trainer.</div>
        )}

        {!allAssigned && <p className="validation-copy">Choose an active replacement for every remaining session.</p>}
      </ConfirmDialog>
    </>
  )
}
