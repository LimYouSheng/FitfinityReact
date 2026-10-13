import { useRef, useState } from 'react'
import { useActionConfirmation } from '../../components/ActionConfirmationProvider.jsx'

export default function TrainerReactivationButton({ trainer, disabled, onReview, onReactivate }) {
  const confirmAction = useActionConfirmation()
  const working = useRef(false)
  const [busy, setBusy] = useState(false)
  const [uncertain, setUncertain] = useState(false)
  const [saved, setSaved] = useState(false)
  if (saved) return null
  return <button type="button" className="profile-menu-reactivate" disabled={disabled || busy} onClick={async () => {
    if (working.current) return
    working.current = true
    setBusy(true)
    let submitted = false
    try {
      const review = onReview ? await onReview() : null
      if (!review?.uncertain && !await confirmAction({
        title: `Reactivate ${trainer.name}?`,
        message: `The trainer will return to active trainer lists and can be assigned to sessions again.${onReview ? ' A fresh sign-in is required; separately disabled sign-in identities remain disabled.' : ''}`,
        confirmLabel: 'Reactivate Trainer',
      })) return
      submitted = true
      await onReactivate(review?.reviewed)
      setUncertain(false)
      setSaved(true)
    } catch (error) {
      // The route reports the failure. Unknown outcomes retain the original review in the adapter.
      setUncertain(submitted && !(error.status >= 400 && error.status < 500))
    } finally {
      working.current = false
      setBusy(false)
    }
  }}>{busy ? 'Checking Trainer…' : uncertain ? 'Check Reactivation' : 'Reactivate Trainer'}</button>
}
