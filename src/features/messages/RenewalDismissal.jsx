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
      const accepted = await confirm({ title: 'Remove renewal follow-up?', confirmLabel: 'Remove',
        message: `Remove “${message.title}” from the renewal list? The client and packages stay unchanged.` })
      if (accepted && mounted.current) await onDismiss(message.id)
    } catch (failure) { if (mounted.current) setError(failure.message || 'Could not remove this follow-up. Try again.') }
    finally { locked.current = false; if (mounted.current) setBusy(false) }
  }
  return <div className="renewal-remove-action">
    <button type="button" className="secondary-button small" aria-label={`Remove ${message.title} from renewals`} disabled={busy} onClick={remove}>{busy ? 'Removing…' : 'Remove'}</button>
    {error && <p role="alert">{error}</p>}
  </div>
}
