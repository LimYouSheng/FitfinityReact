import { useEffect, useRef, useState } from 'react'
import { useEditGuard } from '../../components/EditGuardProvider.jsx'
import TrainerDeactivationDialog from './TrainerDeactivationDialog.jsx'

export default function ApiTrainerDeactivationButton({ trainer, workflow, disabled, onEditing }) {
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
  }, [disabled, trainer.id, trainer.status])
  useEffect(() => {
    if (saved && !activeEdit && !finishing.current) {
      finishing.current = true
      void workflow.saved().catch(() => {})
    }
  }, [saved, activeEdit, workflow])
  if (saved) return null
  return <>
    <button type="button" className="profile-menu-danger" disabled={disabled || busy} onClick={async () => {
      if (locked.current) return
      const scope = reviewScope.current
      locked.current = true; setBusy(true); setError('')
      try {
        const reviewed = await workflow.review()
        if (reviewScope.current !== scope) return
        setDraft(reviewed); onEditing(true)
      } catch (failure) { if (reviewScope.current === scope) setError(failure.message) }
      finally { locked.current = false; if (reviewScope.current) setBusy(false) }
    }}>{busy ? 'Checking Trainer…' : 'Deactivate Trainer'}</button>
    {draft && <TrainerDeactivationDialog trainer={trainer} trainers={[]} clients={[]} sessions={[]}
      deactivateOpen reviewed={draft.reviewed} initialReplacements={draft.replacements} uncertain={draft.uncertain}
      onPreview={workflow.preview}
      setDeactivateOpen={() => { setDraft(null); onEditing(false) }}
      onDeactivate={async (replacements, reviewed) => {
        try { await workflow.save({ reviewed, replacements }); setSaved(true) }
        catch (failure) {
          setDraft(current => ({ ...current, reviewed, replacements, uncertain: !(failure.status >= 400 && failure.status < 500) }))
          throw failure
        }
      }} />}
    {error && <p role="alert">{error}</p>}
  </>
}
