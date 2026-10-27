import useReviewLifetime from '../../hooks/useReviewLifetime.js'
import { useRef, useState } from 'react'
import ConfirmDialog from '../../components/ConfirmDialog.jsx'
import { useEditGuard } from '../../components/EditGuardProvider.jsx'

// Freeze the original review on response loss; recovery reads its receipt without a new write.
export default function ApiPackageActionButton({ workflow, operation, disabled, recordId }) {
  const { setActiveEdit, guardNavigation } = useEditGuard()
  const beginReview = useReviewLifetime(disabled, `${recordId}/${operation}`)
  const locked = useRef(false)
  const [draft, setDraft] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const label = operation === 'deactivate' ? 'Deactivate Package' : 'Delete Upcoming Sessions'
  const close = () => { setDraft(null); setActiveEdit(null) }
  const open = async () => {
    if (locked.current) return
    const isCurrent = beginReview()
    locked.current = true; setBusy(true); setError('')
    try {
      const reviewed = await workflow.review()
      if (!isCurrent()) return
      setDraft(reviewed); setActiveEdit(label)
    } catch (failure) { if (isCurrent()) setError(failure.message) }
    finally { locked.current = false; setBusy(false) }
  }
  const save = async () => {
    if (locked.current) return
    locked.current = true; setBusy(true); setError('')
    try {
      if (draft.uncertain) {
        const recovered = await workflow.reconcile()
        if (!recovered) { setError('The original request has no confirmed result yet. Check again.'); return }
      } else {
        const { reviewed, deleteUpcomingSessions } = draft
        await workflow.save({ reviewed, deleteUpcomingSessions })
      }
      close(); await workflow.saved()
    } catch (failure) {
      setError(failure.message)
      setDraft(current => ({ ...current, uncertain: !(failure.status >= 400 && failure.status < 500) }))
    } finally { locked.current = false; setBusy(false) }
  }
  return <>
    <button type="button" className="secondary-button" disabled={disabled || busy} onClick={open}>{label}</button>
    {!draft && error && <p role="alert">{error}</p>}
    {draft && <ConfirmDialog open title={`${label}?`} danger confirmLabel={busy ? 'Checking…' : draft.uncertain ? 'Check Original Request' : operation === 'deactivate' ? 'Deactivate Package' : 'Delete Sessions'} confirmDisabled={busy} onConfirm={save} onCancel={() => { if (!busy) guardNavigation(close) }}>
      <p>{draft.reviewed.name}: {draft.reviewed.eligible.length} eligible upcoming sessions.</p>
      <p>Completed sessions, credits and purchased terms are retained.</p>
      {operation === 'deactivate' ? <label><input type="checkbox" checked={draft.deleteUpcomingSessions} disabled={busy || draft.uncertain} onChange={event => setDraft(current => ({ ...current, deleteUpcomingSessions: event.target.checked }))} /> Delete upcoming sessions too (cannot be undone)</label>
        : <p>The package stays inactive. Deletion can be undone in Messages within 24 hours while the original sessions remain eligible.</p>}
      {error && <p role="alert">{error}</p>}
    </ConfirmDialog>}
  </>
}
