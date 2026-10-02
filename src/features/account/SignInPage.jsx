import SelectField from '../../components/SelectField.jsx'
import { useEffect, useRef, useState } from 'react'
import Panel from '../../components/Panel.jsx'

export default function SignInPage({ accounts = [], demoPassword, policy, authNotice = '', onSignIn, onChallenge, onForgotPassword, onResetPassword, onAuthenticated }) {
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [stage, setStage] = useState('password')
  const [challenge, setChallenge] = useState(null)
  const [code, setCode] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [notice, setNotice] = useState(authNotice)
  const pending = useRef(false)
  const active = useRef(true)
  const heading = useRef(null)
  const real = Boolean(onChallenge)
  useEffect(() => { active.current = true; return () => { active.current = false } }, [])
  useEffect(() => { if (stage !== 'password') heading.current?.focus() }, [stage, challenge?.challenge])
  const reset = () => { setStage('password'); setChallenge(null); setPassword(''); setNewPassword(''); setConfirmation(''); setCode(''); setError(''); setNotice('') }
  useEffect(() => {
    if (!challenge?.expiresAt) return
    const remaining = new Date(challenge.expiresAt).getTime() - Date.now()
    const timer = setTimeout(() => { reset(); setError('The sign-in step expired. Start again.') }, Math.max(0, remaining))
    return () => clearTimeout(timer)
  }, [challenge?.expiresAt])
  const needsNewPassword = stage === 'reset' || challenge?.challenge === 'NEW_PASSWORD_REQUIRED'
  const passwordHelp = `Use ${policy?.minimumLength ?? 15}–${policy?.maximumLength ?? 128} characters without spaces or other whitespace.`
  const accept = async result => {
    setPassword(''); setNewPassword(''); setConfirmation(''); setCode('')
    if (result?.challenge) { setChallenge(result); setStage('challenge') }
    else { setChallenge(null); setStage('authenticated'); await onAuthenticated?.() }
  }
  const submit = async event => {
    event.preventDefault()
    if (pending.current) return
    if (needsNewPassword) {
      const length = Array.from(newPassword).length
      if (length < (policy?.minimumLength ?? 15) || length > (policy?.maximumLength ?? 128) || /\s/u.test(newPassword)) { setError(passwordHelp); return }
      if (newPassword !== confirmation) { setError('The new passwords do not match.'); return }
    }
    pending.current = true
    setBusy(true); setError('')
    try {
      if (stage === 'authenticated') {
        await onAuthenticated?.()
      } else if (stage === 'forgot') {
        const result = await onForgotPassword({ identifier })
        if (active.current) { setNotice(result.message); setStage('reset'); setPassword('') }
      } else if (stage === 'reset') {
        await onResetPassword({ code, newPassword })
        if (active.current) { reset(); setNotice('Password reset. Sign in with your new password and authenticator.') }
      } else {
        const result = stage === 'challenge'
          ? await onChallenge(needsNewPassword ? { newPassword } : { code })
          : await onSignIn({ identifier, password })
        if (active.current && real) await accept(result)
      }
    } catch (failure) {
      if (active.current) {
        if (['SESSION_EXPIRED', 'SESSION_RECHECK', 'API_RESPONSE'].includes(failure.code)) reset()
        setError(failure.message || 'Unable to sign in. Try again.')
      }
    } finally { pending.current = false; if (active.current) setBusy(false) }
  }
  const title = stage === 'authenticated' ? 'Loading your account' : stage === 'forgot' ? 'Reset password' : stage === 'reset' ? 'Enter recovery code' : needsNewPassword ? 'Choose a new password' : challenge?.challenge === 'MFA_SETUP' ? 'Set up your authenticator' : stage === 'challenge' ? 'Authenticator verification' : 'Sign in'
  const button = stage === 'authenticated' ? 'Retry loading account' : stage === 'forgot' ? 'Send recovery code' : stage === 'reset' ? 'Reset Password' : stage === 'challenge' ? 'Continue' : 'Sign In'
  return <main className="account-entry"><Panel>
    <span className="eyebrow">Staff portal</span><h1 ref={heading} tabIndex={-1}>{title}</h1>
    {demoPassword && <p className="helper">Demo password: <strong>{demoPassword}</strong></p>}
    {notice && <p role="status" className="helper">{notice}</p>}
    {challenge?.challenge === 'MFA_SETUP' && <div className="auth-setup"><p>Add an account in your authenticator app. Choose a time-based code and enter this setup key:</p><code aria-label="Authenticator setup key">{challenge.secretCode}</code><p className="helper">Keep this key private. Enter the six-digit code from your authenticator below.</p></div>}
    <form onSubmit={submit} className="account-form">
      <fieldset disabled={busy}>
        {['password', 'forgot'].includes(stage) && <label>{real ? 'Email' : 'Account'}{accounts.length ? <SelectField aria-label="Account" required value={identifier} onChange={event => setIdentifier(event.target.value)}><option value="">Choose account</option>{accounts.map(account => <option key={account.id} value={account.id}>{account.name}</option>)}</SelectField> : <input aria-label={real ? 'Email' : 'Account'} type={real ? 'email' : 'text'} autoComplete="username" autoCapitalize="none" spellCheck={false} required value={identifier} onChange={event => setIdentifier(event.target.value)} />}</label>}
        {stage === 'password' && <label>Password<input aria-label="Password" type="password" autoComplete="current-password" required value={password} onChange={event => setPassword(event.target.value)} /></label>}
        {needsNewPassword && <><p className="helper">{passwordHelp}</p><label>New password<input type="password" autoComplete="new-password" required value={newPassword} onChange={event => setNewPassword(event.target.value)} /></label><label>Confirm new password<input type="password" autoComplete="new-password" required value={confirmation} onChange={event => setConfirmation(event.target.value)} /></label></>}
        {(stage === 'reset' || (stage === 'challenge' && !needsNewPassword)) && <label>{stage === 'reset' ? 'Recovery code' : 'Authenticator code'}<input inputMode="numeric" autoComplete="one-time-code" required pattern={stage === 'reset' ? undefined : '[0-9]{6}'} maxLength={stage === 'reset' ? 64 : 6} value={code} onChange={event => setCode(event.target.value)} /></label>}
      </fieldset>
      {error && <p className="validation-copy" role="alert">{error}</p>}
      <button type="submit" className="primary-button" disabled={busy}>{busy ? 'Please wait…' : button}</button>
      {real && (stage === 'password' ? <button type="button" className="text-action" disabled={busy} onClick={() => { reset(); setStage('forgot') }}>Forgot password?</button> : <button type="button" className="text-action" disabled={busy} onClick={reset}>Back to sign in</button>)}
    </form>
  </Panel></main>
}
