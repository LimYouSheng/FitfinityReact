import TrainerAssignedClients from './TrainerAssignedClients.jsx'
import TrainerDeactivationDialog from './TrainerDeactivationDialog.jsx'
import TrainerAvailabilityGrid from './TrainerAvailabilityGrid.jsx'
import { managesOperations, canViewTrainerRates, canEditTrainerRates } from '../../app/permissions.js'
import TrainerGeneralFields from './TrainerGeneralFields.jsx'
import { trainerProfileDraft, trainerStepErrors } from '../../app/trainerOnboarding.js'
import { phoneText } from '../../app/contact.js'
import usePageState from '../../hooks/usePageState.js'
import TrainerAvailabilityEditor from './TrainerAvailabilityEditor.jsx'
import { useEffect, useRef, useState } from 'react'
import { APPROVAL_FIELDS } from '../../app/constants.js'
import ApprovalSetting from '../../components/ApprovalSetting.jsx'
import Panel from '../../components/Panel.jsx'
import StatusBadge from '../../components/StatusBadge.jsx'
import ProfileAvatar from '../../components/ProfileAvatar.jsx'
import ProfileNavigation from '../../components/ProfileNavigation.jsx'
import { useActionConfirmation } from '../../components/ActionConfirmationProvider.jsx'
import { useEditGuard } from '../../components/EditGuardProvider.jsx'
import { formatDate } from '../../utils/date.js'

export default function TrainerProfilePage({
  policy,
  readOnly = false,
  activityAvailable = true,
  viewer,
  trainer,
  trainers,
  clients,
  sessions,
  onOpenClient,
  onSaveAutonomy,
  onSaveAvailability,
  onUpdate,
  onDeactivate,
  onReactivate,
}) {
  const confirmAction = useActionConfirmation()
  const { guardNavigation, setActiveEdit } = useEditGuard()
  const canEditRates = canEditTrainerRates(viewer)
  const isManager = managesOperations(viewer)
  const [savedTab, setTab] = usePageState(`trainer.${trainer.id}.${viewer.role}.tab`, 'overview')
  const tab = !activityAvailable && savedTab === 'activity' ? 'overview' : savedTab
  const [activeEditor, setActiveEditor] = useState(null)
  const [generalDraft, setGeneralDraft] = useState(() => trainerProfileDraft(trainer, policy))
  const [generalErrors, setGeneralErrors] = useState({})
  const generalFields = useRef(null)
  const [ratesDraft, setRatesDraft] = useState(trainer.rates)
  const [ratesErrors, setRatesErrors] = useState({})
  const [autonomyDraft, setAutonomyDraft] = useState(trainer.approvalNeeded)
  const [deactivateOpen, setDeactivateOpen] = useState(false)


  const draftTrainerId = useRef(trainer.id)
  useEffect(() => {
    const changed = draftTrainerId.current !== trainer.id
    if (changed || !activeEditor) {
      setGeneralDraft(trainerProfileDraft(trainer, policy))
      setRatesDraft(trainer.rates)
      setAutonomyDraft(trainer.approvalNeeded)
    }
    if (changed) setActiveEditor(null)
    draftTrainerId.current = trainer.id
  }, [activeEditor, trainer, policy])

  useEffect(() => {
    const label = ({ general: 'Trainer information', rates: 'Trainer rates', autonomy: 'Autonomy controls', availability: 'Trainer availability' })[activeEditor] ?? null
    setActiveEdit(label)
    return () => setActiveEdit(null)
  }, [activeEditor, setActiveEdit])

  const supervised = Object.values(trainer.approvalNeeded).filter(Boolean).length
  const saveGeneral = async () => {
    const errors = trainerStepErrors(generalDraft, 'general', { requireComplete: false })
    if (Object.keys(errors).length) { setGeneralErrors(errors); return }
    const confirmed = await confirmAction({
      title: 'Save trainer information?',
      message: 'This will update the trainer’s contact, profile and qualification details.',
      confirmLabel: 'Save Changes',
    })
    if (!confirmed) return
    try {
      await onUpdate({
        name: generalDraft.name,
        phone: phoneText(generalDraft.phone),
        email: generalDraft.email,
        birthday: generalDraft.birthday,
        gender: generalDraft.gender,
        trainerType: generalDraft.trainerType,
        qualifications: generalDraft.qualifications,
        publicProfile: generalDraft.publicProfile,
      })
      setActiveEditor(null)
    } catch (error) { setGeneralErrors({ save: error.message || 'Trainer information could not be saved.' }) }
  }

  useEffect(() => {
    if (Object.keys(generalErrors).length) generalFields.current?.querySelector('[aria-invalid="true"]')?.focus()
  }, [generalErrors])

  const saveRates = async () => {
    if (readOnly || !canEditRates) return
    const errors = trainerStepErrors({ rates: ratesDraft }, 'rates')
    if (Object.keys(errors).length) { setRatesErrors(errors); return }
    setRatesErrors({})
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
          ...(isManager ? [['clients', 'Assigned Clients']] : []),
          ...(activityAvailable ? [['activity', 'Monthly Activity']] : []),
        ]}
        activeKey={tab}
        onSelect={key => guardNavigation(() => {
          setActiveEditor(null)
          setTab(key)
        })}
      >

          {!readOnly && isManager && trainer.status !== 'inactive' && (
            <button type="button" className="profile-menu-danger" disabled={Boolean(activeEditor)} onClick={() => setDeactivateOpen(true)}>
              Deactivate Trainer
            </button>
          )}

          {!readOnly && isManager && trainer.status === 'inactive' && (
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
              {!readOnly && isManager && (activeEditor !== 'general' ? (
                <button type="button" className="text-action" disabled={Boolean(activeEditor)} onClick={() => { setGeneralErrors({}); setActiveEditor('general') }}>Edit</button>
              ) : (
                <div className="inline-actions">
                  <button type="button" className="text-action muted-action" onClick={() => {
                    setGeneralDraft(trainerProfileDraft(trainer, policy))
                    setActiveEditor(null)
                  }}>Cancel</button>
                  <button type="button" className="text-action" onClick={saveGeneral}>Save</button>
                </div>
              ))}
            </div>

            {activeEditor === 'general' ? <div ref={generalFields}>
              <TrainerGeneralFields draft={generalDraft} errors={generalErrors} policy={policy} trainers={trainers}
                onChange={patch => { setGeneralDraft(current => ({ ...current, ...patch })); setGeneralErrors({}) }} />
              {generalErrors.save && <p role="alert">{generalErrors.save}</p>}
            </div> : <div className="info-list profile-info-grid">
              {[
                ['Trainer name', 'name'], ['Mobile Number', 'phone'], ['Email', 'email'], ['Birthday', 'birthday'],
                ['Gender', 'gender'], ['Trainer type', 'trainerType'], ['Qualifications', 'qualifications'], ['Public profile', 'publicProfile'],
              ].map(([label, key]) => <div className="info-row" key={key}><span>{label}</span>
                <strong>{key === 'birthday' ? formatDate(trainer[key]) : trainer[key]}</strong>
              </div>)}
            </div>}

          </Panel>

          {canViewTrainerRates(viewer) && <Panel className={activeEditor === 'rates' ? 'editing-section' : ''}>
            <div className="section-head">
              <h2>Training & Rates</h2>

              {!readOnly && canEditRates && (activeEditor !== 'rates' ? (
                <button type="button" className="text-action" disabled={Boolean(activeEditor)} onClick={() => { setRatesErrors({}); setActiveEditor('rates') }}>Edit</button>
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
                      aria-invalid={Boolean(ratesErrors.peak)}
                      type="number"
                      min="0"
                      step="0.01"
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
                      aria-invalid={Boolean(ratesErrors.offPeak)}
                      type="number"
                      min="0"
                      step="0.01"
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
            {activeEditor === 'rates' && Object.values(ratesErrors).map(error => <p role="alert" key={error}>{error}</p>)}
          </Panel>}

          <Panel className={activeEditor === 'autonomy' ? 'editing-section' : ''}>
            <div className="section-head">
              <div>
                <h2>Owner Approval Needed</h2>
              </div>

              {!readOnly && isManager && (activeEditor !== 'autonomy' ? (
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
                  disabled={!isManager || activeEditor !== 'autonomy'}
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
              {!readOnly && !isManager && viewer.trainerId === trainer.id && trainer.status === 'active' && <button type="button" className="text-action" disabled={Boolean(activeEditor)} onClick={() => { setActiveEditor('availability') }}>{trainer.approvalNeeded?.availability !== false ? 'Request Change' : 'Edit'}</button>}
            </div>
            <TrainerAvailabilityGrid availability={trainer.availability} />
          </>}
        </Panel>
      )}

      {isManager && tab === 'clients' && (
        <TrainerAssignedClients trainer={trainer} clients={clients} sessions={sessions} onOpenClient={onOpenClient} />
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

      <TrainerDeactivationDialog trainer={trainer} trainers={trainers} clients={clients} sessions={sessions}
        deactivateOpen={deactivateOpen} setDeactivateOpen={setDeactivateOpen} onDeactivate={onDeactivate} />
    </>
  )
}
