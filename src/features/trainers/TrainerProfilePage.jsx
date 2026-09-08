import TrainerAvailabilityEditor from './TrainerAvailabilityEditor.jsx'
import { useEffect, useMemo, useState } from 'react'
import { APPROVAL_FIELDS, DAYS } from '../../app/constants.js'
import { activeTrainers, remainingTrainerSessions } from '../../app/status.js'
import ApprovalSetting from '../../components/ApprovalSetting.jsx'
import ConfirmDialog from '../../components/ConfirmDialog.jsx'
import Panel from '../../components/Panel.jsx'
import StatusBadge from '../../components/StatusBadge.jsx'
import ProfileAvatar from '../../components/ProfileAvatar.jsx'
import ProfileNavigation from '../../components/ProfileNavigation.jsx'
import { useActionConfirmation } from '../../components/ActionConfirmationProvider.jsx'
import { useEditGuard } from '../../components/EditGuardProvider.jsx'
import PaginationControls from '../../components/PaginationControls.jsx'
import usePagination from '../../hooks/usePagination.js'
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
  policy,
  viewer,
  trainer,
  trainers,
  clients,
  sessions,
  onBack,
  onOpenClient,
  onSaveAutonomy,
  onSaveAvailability,
  onUpdate,
  onDeactivate,
  onReactivate,
}) {
  const confirmAction = useActionConfirmation()
  const { guardNavigation, setActiveEdit } = useEditGuard()
  const isOwner = viewer.role === 'owner'
  const [tab, setTab] = useState('overview')
  const [activeEditor, setActiveEditor] = useState(null)
  const [generalDraft, setGeneralDraft] = useState(trainer)
  const [ratesDraft, setRatesDraft] = useState(trainer.rates)
  const [autonomyDraft, setAutonomyDraft] = useState(trainer.approvalNeeded)
  const [deactivateOpen, setDeactivateOpen] = useState(false)
  const [replacements, setReplacements] = useState({})
  const [assignedQuery, setAssignedQuery] = useState('')
  const [assignedType, setAssignedType] = useState('')
  const [assignedFrequency, setAssignedFrequency] = useState('')

  useEffect(() => {
    setGeneralDraft(trainer)
    setRatesDraft(trainer.rates)
    setAutonomyDraft(trainer.approvalNeeded)
    setActiveEditor(null)
  }, [trainer])

  useEffect(() => { setTab('overview') }, [trainer.id, isOwner])

  useEffect(() => {
    const label = ({ general: 'Trainer information', rates: 'Trainer rates', autonomy: 'Autonomy controls', availability: 'Trainer availability' })[activeEditor] ?? null
    setActiveEdit(label)
    return () => setActiveEdit(null)
  }, [activeEditor, setActiveEdit])

  const supervised = Object.values(trainer.approvalNeeded).filter(Boolean).length
  const assignedClients = clients
    .filter(client =>
      (client.status ?? 'active') === 'active' &&
      client.trainerId === trainer.id
    )
    .sort((a, b) => (b.startDate ?? '').localeCompare(a.startDate ?? ''))

  const filteredAssignedClients = useMemo(() => {
    const search = assignedQuery.trim().toLowerCase()
    return assignedClients.filter(client => {
      if (search && !client.name.toLowerCase().includes(search) && !client.email.toLowerCase().includes(search)) return false
      if (assignedType && client.type !== assignedType) return false
      if (assignedFrequency && String(client.package.sessionsPerWeek) !== assignedFrequency) return false
      return true
    })
  }, [assignedClients, assignedFrequency, assignedQuery, assignedType])

  const remaining = useMemo(
    () => remainingTrainerSessions(trainer.id, sessions),
    [trainer.id, sessions]
  )
  const assignedClientPagination = usePagination(filteredAssignedClients, `${trainer.id}|${assignedQuery}|${assignedType}|${assignedFrequency}`)
  const remainingPagination = usePagination(remaining, `${trainer.id}|${deactivateOpen}`)

  const selectableReplacements = activeTrainers(trainers).filter(item => item.id !== trainer.id)
  const allAssigned = remaining.every(session => replacements[session.id])

  const saveGeneral = async () => {
    const confirmed = await confirmAction({
      title: 'Save trainer information?',
      message: 'This will update the trainer’s contact, profile and qualification details.',
      confirmLabel: 'Save Changes',
    })
    if (!confirmed) return
    try {
      await onUpdate({
        phone: generalDraft.phone,
        email: generalDraft.email,
        birthday: generalDraft.birthday,
        gender: generalDraft.gender,
        trainerType: generalDraft.trainerType,
        qualifications: generalDraft.qualifications,
        publicProfile: generalDraft.publicProfile,
      })
      setActiveEditor(null)
    } catch { /* The action banner reports failure; keep the draft open. */ }
  }

  const saveRates = async () => {
    const confirmed = await confirmAction({
      title: 'Save trainer rates?',
      message: 'This will replace the trainer’s current peak and off-peak session rates.',
      confirmLabel: 'Save Rates',
    })
    if (!confirmed) return
    try {
      await onUpdate({
        rates: {
          peak: Number(ratesDraft.peak),
          offPeak: Number(ratesDraft.offPeak),
        },
      })
      setActiveEditor(null)
    } catch { /* The action banner reports failure; keep the draft open. */ }
  }

  return (
    <>
      <div className="page-head profile-identity-card">
        <div className="profile-identity-main">
          <ProfileAvatar name={trainer.name} />

          <div>
            <span className="eyebrow">Trainer</span>
            <h1>{trainer.name}</h1>
          </div>
        </div>

        <div className="profile-card-statuses" aria-label="Trainer status">
          <StatusBadge className="profile-autonomy-badge" tone={trainer.status === 'inactive' ? 'amber' : supervised ? 'amber' : 'green'}>
            {trainer.status === 'inactive'
              ? 'Inactive'
              : supervised
                ? `${supervised} approval controls`
                : 'Fully autonomous'}
          </StatusBadge>

          <StatusBadge tone={trainer.status === 'inactive' ? 'amber' : 'green'}>
            {trainer.status === 'inactive' ? 'Inactive' : 'Active'}
          </StatusBadge>
        </div>
      </div>

      <ProfileNavigation
        items={[
          ['overview', 'Overview'],
          ['availability', 'Availability'],
          ...(isOwner ? [['clients', 'Assigned Clients']] : []),
          ['activity', 'Monthly Activity'],
        ]}
        activeKey={tab}
        onSelect={key => guardNavigation(() => {
          setActiveEditor(null)
          setTab(key)
        })}
      >

          {isOwner && trainer.status !== 'inactive' && (
            <button type="button" className="profile-menu-danger" disabled={Boolean(activeEditor)} onClick={() => setDeactivateOpen(true)}>
              Deactivate Trainer
            </button>
          )}

          {isOwner && trainer.status === 'inactive' && (
            <button type="button" className="profile-menu-reactivate" disabled={Boolean(activeEditor)} onClick={async () => {
              const confirmed = await confirmAction({
                title: `Reactivate ${trainer.name}?`,
                message: 'The trainer will return to active trainer lists and can be assigned to sessions again.',
                confirmLabel: 'Reactivate Trainer',
              })
              if (confirmed) {
                try { await onReactivate() } catch { /* Failure is shown in the action banner. */ }
              }
            }}>
              Reactivate Trainer
            </button>
          )}
      </ProfileNavigation>

      {tab === 'overview' && (
        <div className="profile-overview-stack">
          <Panel className={activeEditor === 'general' ? 'editing-section' : ''}>
            <div className="section-head">
              <div><h2>General Information</h2></div>
              {isOwner && (activeEditor !== 'general' ? (
                <button type="button" className="text-action" disabled={Boolean(activeEditor)} onClick={() => setActiveEditor('general')}>Edit</button>
              ) : (
                <div className="inline-actions">
                  <button type="button" className="text-action muted-action" onClick={() => {
                    setGeneralDraft(trainer)
                    setActiveEditor(null)
                  }}>Cancel</button>
                  <button type="button" className="text-action" onClick={saveGeneral}>Save</button>
                </div>
              ))}
            </div>

            <div className="info-list profile-info-grid">
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
                  {activeEditor === 'general'
                    ? <input aria-label={label} type={type} value={generalDraft[key]} onChange={event => setGeneralDraft(current => ({ ...current, [key]: event.target.value }))} />
                    : <strong>{key === 'birthday' ? formatDate(trainer[key]) : trainer[key]}</strong>}
                </div>
              ))}

              <div className="info-row">
                <span>Public profile</span>
                {activeEditor === 'general'
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

          <Panel className={activeEditor === 'rates' ? 'editing-section' : ''}>
            <div className="section-head">
              <h2>Training & Rates</h2>

              {isOwner && (activeEditor !== 'rates' ? (
                <button type="button" className="text-action" disabled={Boolean(activeEditor)} onClick={() => setActiveEditor('rates')}>Edit</button>
              ) : (
                <div className="inline-actions">
                  <button
                    type="button"
                    className="text-action muted-action"
                    onClick={() => {
                      setRatesDraft(trainer.rates)
                      setActiveEditor(null)
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
                <span>Peak rate</span>
                {activeEditor === 'rates'
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
                {activeEditor === 'rates'
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

          <Panel className={activeEditor === 'autonomy' ? 'editing-section' : ''}>
            <div className="section-head">
              <div>
                <h2>Owner Approval Needed</h2>
              </div>

              {isOwner && (activeEditor !== 'autonomy' ? (
                <button type="button" className="text-action" disabled={Boolean(activeEditor)} onClick={() => setActiveEditor('autonomy')}>Edit</button>
              ) : (
                <div className="inline-actions">
                  <button type="button" className="text-action muted-action" onClick={() => {
                    setAutonomyDraft(trainer.approvalNeeded)
                    setActiveEditor(null)
                  }}>Cancel</button>
                  <button type="button" className="text-action" onClick={async () => {
                    const confirmed = await confirmAction({
                      title: 'Save autonomy controls?',
                      message: 'This will change which trainer actions require owner approval.',
                      confirmLabel: 'Save Controls',
                    })
                    if (!confirmed) return
                    try {
                      await onSaveAutonomy(autonomyDraft)
                      setActiveEditor(null)
                    } catch { /* The action banner reports failure; keep the draft open. */ }
                  }}>Save</button>
                </div>
              ))}
            </div>

            <div className="approval-grid">
              {APPROVAL_FIELDS.map(([field, label]) => (
                <ApprovalSetting
                  key={field}
                  label={label}
                  checked={(activeEditor === 'autonomy' ? autonomyDraft : trainer.approvalNeeded)[field]}
                  disabled={!isOwner || activeEditor !== 'autonomy'}
                  onChange={checked => setAutonomyDraft(current => ({ ...current, [field]: checked }))}
                />
              ))}
            </div>
          </Panel>
        </div>
      )}

      {tab === 'availability' && (
        <Panel className={activeEditor === 'availability' ? 'editing-section' : ''}>
          {activeEditor === 'availability' ? (
            <TrainerAvailabilityEditor policy={policy} availability={trainer.availability} approvalNeeded={trainer.approvalNeeded?.availability !== false}
              onCancel={() => setActiveEditor(null)}
              onSave={async blocks => {
                await onSaveAvailability(blocks)
                setActiveEditor(null)
              }} />
          ) : <>
            <div className="section-head">
              <h2>Approved Availability</h2>
              {!isOwner && viewer.trainerId === trainer.id && trainer.status === 'active' && <button type="button" className="text-action" disabled={Boolean(activeEditor)} onClick={() => { setActiveEditor('availability') }}>{trainer.approvalNeeded?.availability !== false ? 'Request Change' : 'Edit'}</button>}
            </div>
            <AvailabilityGrid availability={trainer.availability} />
          </>}
        </Panel>
      )}

      {isOwner && tab === 'clients' && (
        <Panel>
          <div className="section-head">
            <div><h2>Assigned Clients</h2></div>
          </div>

          <div className="list-controls assigned-client-controls">
            <input
              aria-label="Search assigned clients"
              value={assignedQuery}
              onChange={event => setAssignedQuery(event.target.value)}
              placeholder="Search name or email"
            />
            <select aria-label="Filter assigned clients by type" value={assignedType} onChange={event => setAssignedType(event.target.value)}>
              <option value="">All types</option>
              <option value="Individual">Individual</option>
              <option value="Couple">Couple</option>
            </select>
            <select aria-label="Filter assigned clients by frequency" value={assignedFrequency} onChange={event => setAssignedFrequency(event.target.value)}>
              <option value="">All frequencies</option>
              <option value="1">Once per week</option>
              <option value="2">Twice per week</option>
            </select>
          </div>

          <div className="quick-list" aria-label="Assigned client list">
            {assignedClientPagination.items.map(client => (
              <div className="quick-row" key={client.id}>
                <div><strong>{client.name}</strong><span>{client.type} • {client.package.total} sessions • {client.package.sessionsPerWeek === 2 ? 'Twice' : 'Once'} per week</span></div>
                <button type="button" className="btn small" onClick={() => onOpenClient(client.id)}>View</button>
              </div>
            ))}
            {!filteredAssignedClients.length && <div className="empty">No matching assigned clients.</div>}
          </div>
          <PaginationControls {...assignedClientPagination} onPage={assignedClientPagination.setPage} />
        </Panel>
      )}

      {tab === 'activity' && (
        <div className="trainer-monthly-activity">
          <div className="trainer-activity-month">
            <span>Reporting month</span>
            <strong>{trainer.monthlyActivity.month ?? 'September 2026'}</strong>
          </div>
          <div className="stats-grid four">
            <Panel><span>Completed Sessions</span><strong>{trainer.monthlyActivity.sessions}</strong></Panel>
            <Panel><span>Training Hours</span><strong>{trainer.monthlyActivity.hours}</strong></Panel>
            <Panel><span>Peak Sessions</span><strong>{trainer.monthlyActivity.peak}</strong></Panel>
            <Panel><span>Off-Peak Sessions</span><strong>{trainer.monthlyActivity.offPeak}</strong></Panel>
          </div>
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
          try {
            await onDeactivate(replacements)
            setDeactivateOpen(false)
            setReplacements({})
          } catch { /* Failure is shown in the action banner; keep the dialog open. */ }
        }}
      >
        <p>
          An inactive trainer will immediately stop appearing in active trainer lists and availability matching.
          Any remaining tagged sessions must be reassigned first.
        </p>

        {remaining.length > 0 ? (
          <div className="reassign-list">
            {remainingPagination.items.map(session => {
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
            <PaginationControls {...remainingPagination} onPage={remainingPagination.setPage} />
          </div>
        ) : (
          <div className="notice">No remaining sessions are tagged to this trainer.</div>
        )}

        {!allAssigned && <p className="validation-copy">Choose an active replacement for every remaining session.</p>}
      </ConfirmDialog>
    </>
  )
}
