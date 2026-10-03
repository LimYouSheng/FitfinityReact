import { useState } from 'react'
import ConfirmDialog from '../../components/ConfirmDialog.jsx'
import DateField from '../../components/DateField.jsx'
import Field from '../../components/OnboardingField.jsx'
import { useEditGuard } from '../../components/EditGuardProvider.jsx'
import { clientReactivationReview, clientReactivationSnapshot } from '../../app/clientReactivation.js'
import { formatDate } from '../../utils/date.js'

export default function ClientReactivationDialog({ client, clients, trainers, sessions, packageCreditTransactions = [], onSave, onClose }) {
  const { guardNavigation } = useEditGuard()
  const db = { clients, trainers, sessions, packageCreditTransactions }
  const [initial] = useState(() => ({
    expected: clientReactivationSnapshot(client, sessions, packageCreditTransactions),
    conflicts: clientReactivationReview(db, client).conflicts.map(row => row.session.id),
  }))
  const [dates, setDates] = useState({})
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const stale = JSON.stringify(initial.expected) !== JSON.stringify(clientReactivationSnapshot(client, sessions, packageCreditTransactions))
  const review = clientReactivationReview(db, client, stale ? {} : dates)
  const rows = review.rows.filter(row => row.error || initial.conflicts.includes(row.session.id) || Object.hasOwn(dates, row.session.id))
  const save = async () => {
    if (saving || stale || review.conflicts.length) return
    setSaving(true); setError('')
    try {
      await onSave({ dates, expected: initial.expected })
      onClose()
    } catch (failure) { setError(failure.message || 'Client reactivation failed.') }
    finally { setSaving(false) }
  }
  return <ConfirmDialog open title={`Reactivate ${client.name}?`} confirmLabel={saving ? 'Reactivating…' : 'Reactivate Client'}
    confirmDisabled={saving || stale || review.conflicts.length > 0} onConfirm={save}
    onCancel={() => { if (!saving) guardNavigation(onClose) }}>
    <div className="stack-gap">
      <p>Packages disabled with this client and their retained sessions will become active again. Separately deactivated packages stay inactive; recently deleted sessions can be restored separately using Undo in Messages within 24 hours.</p>
      <p>{review.rows.length} retained sessions checked. Each conflicting session needs a free date. Its time, trainer and original package stay the same.</p>
      {rows.map(({ session, original, locked, error: conflict }) => {
        const label = `Session ${review.rows.findIndex(row => row.session.id === session.id) + 1} · ${formatDate(original.date)} · ${original.from}–${original.to}`
        return <div key={session.id} className="stack-gap">
          <Field label={label} required><DateField aria-label={label} value={session.date} disabled={saving || stale || locked}
            onChange={event => { setDates(current => ({ ...current, [session.id]: event.target.value })); setError('') }} /></Field>
          <p className="helper">Trainer: {trainers.find(item => item.id === original.trainerId)?.name ?? 'Unavailable'}</p>
          <p className={conflict ? 'onboarding-error' : 'helper'}>{conflict || 'No scheduling conflict.'}{locked && ' This acknowledged session is locked.'}</p>
        </div>
      })}
      {!review.conflicts.length && <p role="status">All retained sessions are conflict-free.</p>}
      {stale && <p role="alert" className="onboarding-error">The client packages or sessions changed. Close and reopen reactivation to review them.</p>}
      {error && <p role="alert" className="onboarding-error">{error}</p>}
    </div>
  </ConfirmDialog>
}
