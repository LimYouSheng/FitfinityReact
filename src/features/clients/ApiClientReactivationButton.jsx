import useReviewLifetime from '../../hooks/useReviewLifetime.js'
import { useEffect, useRef, useState } from 'react'
import ConfirmDialog from '../../components/ConfirmDialog.jsx'
import DateField from '../../components/DateField.jsx'
import Field from '../../components/OnboardingField.jsx'
import { useEditGuard } from '../../components/EditGuardProvider.jsx'
import { formatDate } from '../../utils/date.js'

export default function ApiClientReactivationButton({ disabled, workflow, onEditing, packageName, recordId }) {
  const { guardNavigation, activeEdit } = useEditGuard()
  const target = packageName === undefined ? 'Client' : 'Package'
  const actionLabel = `Reactivate ${target}`
  const beginReview = useReviewLifetime(disabled, recordId ?? packageName)
  const locked = useRef(false)
  const [review, setReview] = useState(null)
  const [dates, setDates] = useState({})
  const [initialConflicts, setInitialConflicts] = useState([])
  const [busy, setBusy] = useState(false)
  const [uncertain, setUncertain] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)
  const finishing = useRef(false)
  useEffect(() => {
    if (saved && !activeEdit && !finishing.current) {
      finishing.current = true
      void workflow.saved().catch(() => { /* The shared portal reports refresh failure after a confirmed save. */ })
    }
  }, [saved, activeEdit, workflow])
  const close = () => { setReview(null); onEditing(false) }
  const open = async () => {
    if (locked.current) return
    const isCurrent = beginReview()
    locked.current = true; setBusy(true); setError('')
    try {
      const value = await workflow.review()
      if (!isCurrent()) return
      setReview(value.reviewed); setDates(value.dates); setUncertain(value.uncertain)
      setInitialConflicts(value.reviewed.rows.filter(r => r.error).map(r => r.id)); onEditing(true)
    } catch (failure) { if (isCurrent()) setError(failure.message) }
    finally { locked.current = false; setBusy(false) }
  }
  const preview = async (id, day) => {
    if (locked.current) return
    const proposed = { ...dates, [id]: day }
    setDates(proposed); setError(''); locked.current = true; setBusy(true)
    try { setReview(await workflow.preview({ id: review.id, reviewed: review, dates: proposed })) }
    catch (failure) { setError(failure.message) }
    finally { locked.current = false; setBusy(false) }
  }
  const save = async () => {
    if (locked.current) return
    locked.current = true; setBusy(true); setError('')
    try {
      await workflow.save({ id: review.id, reviewed: review, dates })
      setUncertain(false); close(); setSaved(true)
    } catch (failure) { setUncertain(!(failure.status >= 400 && failure.status < 500)); setError(failure.message) }
    finally { locked.current = false; setBusy(false) }
  }
  const rows = review?.rows.filter(r => r.error || initialConflicts.includes(r.id) || Object.hasOwn(dates, r.id)) ?? []
  const openCount = review?.rows.filter(r => r.scheduleState === 'open').length ?? 0
  if (saved) return null
  return <>
    <button type="button" className={packageName === undefined ? 'profile-menu-reactivate' : 'secondary-button'} disabled={disabled || busy} onClick={open}>{busy ? `Checking ${target}…` : uncertain ? 'Check Reactivation' : actionLabel}</button>
    {review && <ConfirmDialog open title={packageName === undefined ? `Reactivate ${review.name}?` : 'Reactivate Package?'} confirmLabel={busy ? 'Checking…' : uncertain ? 'Check Reactivation' : actionLabel}
      confirmDisabled={busy || (!uncertain && (Boolean(error) || Boolean(review.packageError) || review.rows.some(r => r.error)))} onConfirm={save}
      onCancel={() => { if (!busy) guardNavigation(close) }}>
      <div className="stack-gap">
        {packageName !== undefined ? <p>{packageName} will become active again. Used credits and the expiry date stay the same. Deleted sessions are not recreated.</p> : <p>Packages disabled with this client and their retained sessions will become active again. Separately deactivated packages stay inactive. Deleted sessions are not recreated; used credits and purchased terms stay unchanged.</p>}
        <p>{openCount} open {openCount === 1 ? 'session' : 'sessions'} will remain unscheduled.</p>
        <p>{review.rows.length} retained sessions checked. Each conflicting session needs a free date. Its time, trainer and original package stay the same.</p>
        {rows.map(row => {
          const label = row.scheduleState === 'open' ? 'Open session' : `Session ${review.rows.findIndex(r => r.id === row.id) + 1} · ${formatDate(row.originalDate)} · ${row.startsAt}–${row.endsAt}`
          return <div key={row.id} className="stack-gap">
            {row.scheduleState === 'open' ? <p>Open session · No date or time assigned.</p> : <Field label={label} required><DateField aria-label={label} value={dates[row.id] ?? row.date} disabled={busy || uncertain || row.locked} onChange={event => preview(row.id, event.target.value)} /></Field>}
            <p className="helper">Trainer: {row.trainerName}</p>
            <p className={row.error ? 'onboarding-error' : 'helper'}>{row.error || 'No scheduling conflict.'}{row.locked && ' This acknowledged session is locked.'}</p>
          </div>
        })}
        {!review.packageError && !review.rows.some(r => r.error) && <p role="status">All retained sessions are conflict-free.</p>}
        {review.packageError && <p role="alert" className="onboarding-error">{review.packageError}</p>}
        {error && <p role="alert" className="onboarding-error">{error}</p>}
      </div>
    </ConfirmDialog>}
    {!review && error && <p role="alert">{error}</p>}
  </>
}
