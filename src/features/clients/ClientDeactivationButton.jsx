import { useRef, useState } from 'react'
import { useActionConfirmation } from '../../components/ActionConfirmationProvider.jsx'

export default function ClientDeactivationButton({ disabled, onReview, onDeactivate }) {
  const confirm = useActionConfirmation()
  const locked = useRef(false)
  const [busy, setBusy] = useState(false)
  const [uncertain, setUncertain] = useState(false)
  const [saved, setSaved] = useState(false)
  if (saved) return null
  return <button type="button" className="profile-menu-danger" disabled={disabled || busy} onClick={async () => {
    if (locked.current) return
    locked.current = true; setBusy(true)
    let submitted = false
    try {
      const { reviewed, uncertain: pending } = await onReview()
      if (!pending && !await confirm({ title: `Deactivate ${reviewed.name}?`, danger: true, confirmLabel: 'Deactivate Client',
        message: `The client will become inactive and remain visible to the assigned trainer. ${reviewed.purchases.filter(p => p.status === 'active').length} active purchased packages will be deactivated. Retained sessions and credits stay unchanged.` })) return
      submitted = true
      await onDeactivate(reviewed)
      setSaved(true); setUncertain(false)
    } catch (error) { setUncertain(submitted && !(error.status >= 400 && error.status < 500)) }
    finally { locked.current = false; setBusy(false) }
  }}>{busy ? 'Checking Client…' : uncertain ? 'Check Deactivation' : 'Deactivate Client'}</button>
}
