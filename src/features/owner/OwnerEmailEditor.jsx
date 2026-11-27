import { useEffect, useRef, useState } from 'react'
import StaffEmailVerification from '../account/StaffEmailVerification.jsx'
import LoadingIndicator from '../../components/LoadingIndicator.jsx'
import { useEditGuard } from '../../components/EditGuardProvider.jsx'
import { useActionConfirmation } from '../../components/ActionConfirmationProvider.jsx'

export default function OwnerEmailEditor({ auth, version, onCompleted }) {
  const [pending, setPending] = useState(undefined)
  const [editing, setEditing] = useState(false)
  const [email, setEmail] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [revision, setRevision] = useState(0)
  const attempt = useRef(null)
  const confirm = useActionConfirmation()
  const { setActiveEdit } = useEditGuard()
  useEffect(() => {
    if (!editing) return
    setActiveEdit('Owner login email')
    return () => setActiveEdit(value => value === 'Owner login email' ? null : value)
  }, [editing, setActiveEdit])
  useEffect(() => {
    let current = true
    auth.pendingEmailChange().then(value => { if (current) setPending(value) }).catch(reason => { if (current) setError(reason.message) })
    return () => { current = false }
  }, [auth, revision])
  const submit = async event => {
    event.preventDefault()
    if (busy) return
    const input = attempt.current ?? { email: email.trim().toLowerCase(), expectedVersion: version }
    if (!attempt.current && !await confirm({ title: 'Change your login email?', message: 'Your current email stays active until you verify the new address. Verification signs you out of existing sessions.', confirmLabel: 'Request Verification' })) return
    attempt.current = input
    setBusy(true); setError('')
    try {
      setPending(await auth.requestOwnerEmailChange(input))
      attempt.current = null; setEditing(false)
    } catch (reason) {
      setError(reason.message)
      if (reason.status >= 400 && reason.status < 500) attempt.current = null
    } finally { setBusy(false) }
  }
  return <section aria-label="Owner login email">
    {error && <p role="alert">{error}</p>}
    {pending === undefined ? error ? <button className="text-action" onClick={() => { setError(''); setRevision(value => value + 1) }}>Retry Email Status</button> : <LoadingIndicator label="Checking email verification…" />
      : pending ? <StaffEmailVerification key={pending.id} auth={auth} onCompleted={onCompleted} />
        : editing ? <form onSubmit={submit} className="stack-gap">
          <label>New login email<input aria-label="New Owner login email" type="email" required maxLength={320} value={email} disabled={busy || Boolean(attempt.current)} onChange={event => setEmail(event.target.value)} /></label>
          <p className="helper">Request verification, then send a code to the new address. Your existing login stays active until verification succeeds.</p>
          <div className="inline-actions"><button className="onboarding-button primary" disabled={busy}>{attempt.current ? 'Check Original Request' : 'Request Verification'}</button><button type="button" className="onboarding-button" disabled={busy || Boolean(attempt.current)} onClick={() => setEditing(false)}>Cancel</button></div>
        </form> : <button className="text-action" onClick={() => setEditing(true)}>Change Login Email</button>}
  </section>
}
