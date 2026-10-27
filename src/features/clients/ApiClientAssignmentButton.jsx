import { useEffect, useRef, useState } from 'react'
import { useEditGuard } from '../../components/EditGuardProvider.jsx'
import ReassignTrainerDialog from './ReassignTrainerDialog.jsx'

export default function ApiClientAssignmentButton({ client, workflow, timeZone, disabled, onEditing }) {
  const { activeEdit } = useEditGuard()
  const [draft, setDraft] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)
  const locked = useRef(false), finishing = useRef(false)
  const reviewScope = useRef(null)
  // A delayed review cannot take over another edit or reactivate a retired control.
  useEffect(() => {
    reviewScope.current = {}
    return () => { reviewScope.current = null }
  }, [disabled, client.id, client.status])
  useEffect(() => {
    if (saved && !activeEdit && !finishing.current) {
      finishing.current = true
      void workflow.saved().then(snapshot => {
        // A fresh directory permits another reassignment of this same client.
        // Failed refreshes retain the confirmed state until the portal recovers.
        if (snapshot) { finishing.current = false; setSaved(false) }
      }).catch(() => {})
    }
  }, [saved, activeEdit, workflow])
  if (saved) return null
  return <>
    <button type="button" className="text-action" disabled={disabled || busy} onClick={async () => {
      if (locked.current) return
      const scope = reviewScope.current
      locked.current = true; setBusy(true); setError('')
      try {
        const reviewed = await workflow.review()
        if (reviewScope.current !== scope) return
        setDraft(reviewed); onEditing(true)
      } catch (failure) { if (reviewScope.current === scope) setError(failure.message) }
      finally { locked.current = false; if (reviewScope.current) setBusy(false) }
    }}>{busy ? 'Checking Trainers…' : 'Reassign Trainer'}</button>
    {draft && <ReassignTrainerDialog client={client} trainers={[]} sessions={[]} timeZone={timeZone}
      reviewed={draft.reviewed} initialTrainerId={draft.trainerId} uncertain={draft.uncertain}
      onSave={async value => {
        try { await workflow.save(value); setSaved(true) }
        catch (failure) {
          setDraft(current => ({ ...current, trainerId: value.trainerId, uncertain: !(failure.status >= 400 && failure.status < 500) }))
          throw failure
        }
      }} onClose={() => { setDraft(null); onEditing(false) }} />}
    {error && <p role="alert">{error}</p>}
  </>
}
