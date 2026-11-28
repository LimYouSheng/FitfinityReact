import { useEffect, useRef, useState } from 'react'
import { useActionConfirmation } from '../../components/ActionConfirmationProvider.jsx'

export default function RenewalDismissal({ message, onDismiss }) {
  const confirm = useActionConfirmation()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const locked = useRef(false), mounted = useRef(false)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  const remove = async event => {
    event.stopPropagation()
    if (locked.current) return
    locked.current = true; setBusy(true); setError('')
    try {
      const accepted = await confirm({ title: 'Delete renewal follow-up?', confirmLabel: 'Delete',
        message: `Delete “${message.title}” from the renewal list? The client and packages stay unchanged.` })
      if (accepted && mounted.current) await onDismiss(message.id)
    } catch (failure) { if (mounted.current) setError(failure.message || 'Could not delete this follow-up. Try again.') }
    finally { locked.current = false; if (mounted.current) setBusy(false) }
  }
  return <div className="renewal-remove-action">
    <button type="button" className="secondary-button small" aria-label={`Delete ${message.title} from renewals`} disabled={busy} onClick={remove}>Delete</button>
    {error && <p role="alert">{error}</p>}
  </div>
}
