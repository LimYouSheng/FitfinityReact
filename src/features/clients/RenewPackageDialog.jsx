import { useEffect, useState } from 'react'
import { renewalMatchBody } from '../../services/apiClientRenewal.js'
import ConfirmDialog from '../../components/ConfirmDialog.jsx'
import { useEditGuard } from '../../components/EditGuardProvider.jsx'
import { packageDraftForClient } from '../../app/packageRenewal.js'
import ClientOnboardingForm from './ClientOnboardingForm.jsx'

export default function RenewPackageDialog({ client, clients = [], trainers, sessions, packages, policy, today, onSave, onClose, renewalWorkflow }) {
  const { guardNavigation } = useEditGuard()
  const [initial, setInitial] = useState(() => renewalWorkflow ? null : packageDraftForClient(client, sessions, packages, today))
  const [readReview] = useState(() => renewalWorkflow?.review)
  const [source] = useState(() => ({ client, sessions, packages }))
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    if (!readReview) return
    let current = true
    readReview().then(reviewed => {
      const grouped = new Map()
      for (const block of reviewed.clientPreferences) {
        const key = `${block.from}/${block.to}`
        if (!grouped.has(key)) grouped.set(key, { id: `saved-preference-${grouped.size + 1}`, days: [], from: block.from, to: block.to })
        for (const day of block.days) if (!grouped.get(key).days.includes(day)) grouped.get(key).days.push(day)
      }
      const saved = { ...source.client, name: reviewed.name, trainerId: reviewed.trainerId, genderPreference: reviewed.genderPreference,
        package: { ...source.client.package, ...reviewed.package }, fixedWeeklySchedule: reviewed.fixedWeeklySchedule, clientPreferences: [...grouped.values()] }
      const draft = packageDraftForClient(saved, source.sessions, source.packages, today, reviewed.minimumStartDate)
      if (current) { setInitial({ ...draft, minimumStartDate: reviewed.minimumStartDate, renewalExpected: reviewed.expected, expectedVersion: reviewed.version }); setError('') }
    }).catch(error => { if (current) setError(error.message) })
    return () => { current = false }
  }, [readReview, attempt, source, today])
  const [saving, setSaving] = useState(false)
  const cancel = () => { if (!saving) guardNavigation(onClose) }
  return <ConfirmDialog open title="Add Package" hideConfirm onCancel={cancel}>
    {!initial && (error ? <div role="alert"><p>{error}</p><button type="button" onClick={() => { setError(''); setAttempt(value => value + 1) }}>Retry package review</button></div> : <p role="status">Loading package details…</p>)}
    {initial && <ClientOnboardingForm packageDraft={initial} previewMatches={renewalWorkflow?.preview} matchBody={renewalWorkflow ? renewalMatchBody : undefined} packages={packages} policy={policy} trainers={trainers} sessions={sessions} clients={clients}
      onCancel={cancel} onCreated={() => { onClose(); void renewalWorkflow?.saved() }} onCreate={async draft => {
        setSaving(true)
        try { return await onSave(draft) ?? { id: client.id } }
        finally { setSaving(false) }
      }} />}
  </ConfirmDialog>
}
