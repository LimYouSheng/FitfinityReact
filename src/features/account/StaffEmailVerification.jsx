import { useEffect, useState } from 'react'

export default function StaffEmailVerification({ auth, onCompleted }) {
  const [change, setChange] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [uncertain, setUncertain] = useState(false)
  useEffect(() => {
    let current = true
    setLoading(true)
    setError('')
    auth.pendingEmailChange().then(value => { if (current) { setChange(value); setUncertain(['sending', 'verifying'].includes(value?.state)) } })
      .catch(reason => { if (current) setError(reason.message) })
      .finally(() => { if (current) setLoading(false) })
    return () => { current = false }
  }, [auth, attempt])
  const act = async operation => {
    if (busy || !change) return
    setBusy(true); setError('')
    try {
      const value = await auth[operation]({ id: change.id, ...(operation === 'verifyEmailChange' ? { code } : {}) })
      setChange(value); setUncertain(false); setCode('')
      if (value.state === 'completed') await onCompleted()
    } catch (reason) {
      setError(reason.message)
      if (!reason.status || reason.status >= 500 || reason.code === 'AUTH_BUSY') setUncertain(true)
      if (['SESSION_CHANGED', 'SESSION_EXPIRED'].includes(reason.code)) await onCompleted()
    } finally { setBusy(false) }
  }
  if (loading) return <p role="status">Checking email verification…</p>
  if (!change) return error ? <div role="alert">{error}<button type="button" className="text-action" onClick={() => setAttempt(value => value + 1)}>Retry Email Status</button></div> : null
  return <section aria-label="Email verification">
    <h2>Verify your new email</h2>
    <p>Requested address: <strong>{change.email}</strong></p>
    <p>Your current login and recovery email stays active until you verify this address.</p>
    {error && <p role="alert">{error}</p>}
    {uncertain && <p role="status">The last result is uncertain. Check its status before sending or verifying another code.</p>}
    {change.state === 'completed' ? <p role="status">Email verified. Sign in with your new email.</p> : <>
      <div className="inline-actions"><button type="button" className="secondary-button" disabled={busy || uncertain} onClick={() => act('sendEmailCode')}>{change.state === 'requested' ? 'Send Verification Code' : 'Send New Code'}</button>
        <button type="button" className="text-action" disabled={busy} onClick={() => act('reconcileEmailChange')}>Check Verification Status</button></div>
      {change.state !== 'requested' && <form onSubmit={event => { event.preventDefault(); act('verifyEmailChange') }}>
        <label>Verification code<input aria-label="Email verification code" autoComplete="one-time-code" inputMode="numeric" pattern="[0-9]{6}" minLength={6} maxLength={6} required value={code} disabled={busy || uncertain} onChange={event => setCode(event.target.value)} /></label>
        <button type="submit" className="primary-button" disabled={busy || uncertain}>Verify New Email</button>
      </form>}
    </>}
  </section>
}
