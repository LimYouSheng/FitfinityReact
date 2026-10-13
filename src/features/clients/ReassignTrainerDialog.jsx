import SelectField from '../../components/SelectField.jsx'
import { useState } from 'react'
import ConfirmDialog from '../../components/ConfirmDialog.jsx'
import Field from '../../components/OnboardingField.jsx'
import { useActionConfirmation } from '../../components/ActionConfirmationProvider.jsx'
import { useEditGuard } from '../../components/EditGuardProvider.jsx'
import { businessClock } from '../../app/clock.js'
import { trainerReassignmentAvailabilityError, trainerReassignmentSnapshot } from '../../app/trainerReassignment.js'
import { formatTimestamp } from '../../utils/date.js'

export default function ReassignTrainerDialog({ client, trainers, sessions, packageCreditTransactions = [], timeZone, onSave, onClose, reviewed, initialTrainerId = '', uncertain = false }) {
  const confirmAction = useActionConfirmation()
  const { guardNavigation } = useEditGuard()
  const [initial] = useState(() => ({
    requestId: globalThis.crypto?.randomUUID?.() ?? `reassign-${Date.now()}-${Math.random().toString(36).slice(2)}`,
    expected: reviewed ? { trainerId: reviewed.current.id, packages: reviewed.purchases, sessions: reviewed.sessions } : trainerReassignmentSnapshot(client, sessions, packageCreditTransactions, businessClock(new Date(), timeZone)),
  }))
  const [trainerId, setTrainerId] = useState(initialTrainerId)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const choices = reviewed ? reviewed.choices.map(t => ({ ...t, availabilityError: t.error })) : trainers.filter(item => item.status === 'active' && item.id !== initial.expected.trainerId)
    .map(trainer => ({ ...trainer, availabilityError: trainerReassignmentAvailabilityError(client, trainer, initial.expected.sessions) }))
  const previous = reviewed?.current ?? trainers.find(item => item.id === initial.expected.trainerId)
  const selected = choices.find(item => item.id === trainerId)
  const save = async () => {
    if (saving || !selected || selected.availabilityError) return
    setSaving(true); setError('')
    try {
      const confirmed = uncertain || await confirmAction({ title: `Reassign trainer for ${client.name}?`, confirmLabel: 'Reassign Trainer',
        message: `${previous?.name ?? 'Unknown trainer'} → ${selected.name}. Update ${initial.expected.sessions.length} eligible upcoming sessions and ${initial.expected.packages.length} current/additional packages. Completed and acknowledged sessions keep their recorded trainer.` })
      if (!confirmed) return
      await onSave({ ...initial, ...(reviewed ? { reviewed } : {}), trainerId })
      onClose()
    } catch (failure) { setError(failure.message || 'Trainer reassignment failed.') }
    finally { setSaving(false) }
  }
  return <ConfirmDialog open title="Permanently Reassign Trainer" confirmLabel={saving ? 'Reassigning…' : uncertain ? 'Check Reassignment' : 'Review Reassignment'}
    confirmDisabled={saving || !selected || Boolean(selected.availabilityError)} onConfirm={save} onCancel={() => { if (!saving) guardNavigation(onClose) }}>
    <div className="stack-gap">
      <p>Current trainer: <strong>{previous?.name ?? 'Unknown trainer'}</strong></p>
      <Field label="New trainer" required><SelectField aria-label="New trainer" value={trainerId} disabled={saving || uncertain} onChange={event => setTrainerId(event.target.value)}>
        <option value="">Choose trainer</option>{choices.map(trainer => <option key={trainer.id} value={trainer.id} disabled={Boolean(trainer.availabilityError)}>{trainer.name}{trainer.availabilityError ? ' — Unavailable' : ''}</option>)}
      </SelectField></Field>
      {!choices.length && <p>No other active trainers.</p>}
      {choices.length > 0 && !choices.some(trainer => !trainer.availabilityError) && <p>No trainer matches the saved schedules and preferences.</p>}
      {choices.filter(trainer => trainer.availabilityError).map(trainer => <p className="helper" key={trainer.id}>{trainer.name}: {trainer.availabilityError}</p>)}
      <p>{initial.expected.sessions.length} eligible upcoming sessions · {initial.expected.packages.length} current/additional packages</p>
      {error && <p role="alert" className="onboarding-error">{error}</p>}
      {Boolean((reviewed?.history ?? client.trainerAssignmentHistory)?.length) && <section aria-label="Trainer assignment history">
        <h3>Assignment History</h3>
        <div className="client-record-list">{[...(reviewed?.history.map(h => ({ id: h.id, at: h.at, by: h.actor, from: h.previous, to: h.replacement })) ?? client.trainerAssignmentHistory)].reverse().map(entry => <div className="client-record-row" key={entry.id}>
          <div><strong>{entry.from.name} → {entry.to.name}</strong><span><time dateTime={entry.at}>{formatTimestamp(entry.at, timeZone)}</time> · {entry.by.name}</span></div>
        </div>)}</div>
      </section>}
    </div>
  </ConfirmDialog>
}
