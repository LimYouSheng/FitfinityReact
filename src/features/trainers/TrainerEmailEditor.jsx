import { useEffect, useRef, useState } from 'react'
import { useActionConfirmation } from '../../components/ActionConfirmationProvider.jsx'

export default function TrainerEmailEditor({ trainer, auth, onRequest, editing, disabled, onEdit, onClose }) {
  const confirm = useActionConfirmation()
  const [pending, setPending] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const version = useRef(null)
  useEffect(() => {
    let current = true
    setLoading(true)
    setError('')
    auth.pendingTrainerEmailChange({ id: trainer.id }).then(value => { if (current) setPending(value) })
      .catch(reason => { if (current) setError(reason.message) })
      .finally(() => { if (current) setLoading(false) })
    return () => { current = false }
  }, [auth, trainer.id, attempt])
  const submit = async event => {
    event.preventDefault()
    if (busy) return
    if (!await confirm({ title: 'Request an email change?', message: 'The trainer must sign in to Your account and verify a code sent to the new address. The current login and recovery email stays active until verification.', confirmLabel: 'Request Verification' })) return
    setBusy(true); setError('')
    try {
      const value = await onRequest({ email }, version.current)
      setPending(value)
      onClose()
    } catch (reason) { setError(reason.message) }
    finally { setBusy(false) }
  }
  if (loading) return <p role="status">Checking email verification…</p>
  if (error && !editing) return <div role="alert">{error}<button type="button" className="text-action" onClick={() => setAttempt(value => value + 1)}>Retry Email Status</button></div>
  if (pending && pending.state !== 'completed') return <p role="status">Awaiting the trainer’s verification of {pending.email}. The current email is still active.</p>
  return editing ? <form onSubmit={submit}>
    <label>New login email<input aria-label="New trainer login email" type="email" required maxLength={320} value={email} disabled={busy} onChange={event => setEmail(event.target.value)} /></label>
    <p className="helper">The trainer confirms the new address from Your account before login or recovery changes.</p>
    {error && <p role="alert">{error}</p>}
    <div className="inline-actions"><button className="primary-button" disabled={busy} type="submit">Request Verification</button><button type="button" className="secondary-button" disabled={busy} onClick={onClose}>Cancel</button></div>
  </form> : <button type="button" className="text-action" disabled={disabled || trainer.status === 'inactive'} onClick={() => { version.current = trainer.version; setEmail(''); onEdit() }}>Change Login Email</button>
}
