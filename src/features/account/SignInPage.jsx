import SelectField from '../../components/SelectField.jsx'
import { useState } from 'react'
import Panel from '../../components/Panel.jsx'

export default function SignInPage({ accounts = [], demoPassword, onSignIn }) {
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const submit = async event => {
    event.preventDefault()
    if (busy) return
    setBusy(true); setError('')
    try { await onSignIn({ identifier, password }) }
    catch (failure) { setError(failure.message || 'Unable to sign in. Try again.') }
    finally { setBusy(false) }
  }
  return <main className="account-entry"><Panel>
    <span className="eyebrow">Staff portal</span><h1>Sign in</h1>
    {demoPassword && <p className="helper">Demo password: <strong>{demoPassword}</strong></p>}
    <form onSubmit={submit} className="account-form">
      <fieldset disabled={busy}>
        <label>Account{accounts.length ? <SelectField aria-label="Account" required value={identifier} onChange={event => setIdentifier(event.target.value)}><option value="">Choose account</option>{accounts.map(account => <option key={account.id} value={account.id}>{account.name}</option>)}</SelectField> : <input aria-label="Account" autoComplete="username" required value={identifier} onChange={event => setIdentifier(event.target.value)} />}</label>
        <label>Password<input aria-label="Password" type="password" autoComplete="current-password" required value={password} onChange={event => setPassword(event.target.value)} /></label>
      </fieldset>
      {error && <p className="validation-copy" role="alert">{error}</p>}
      <button type="submit" className="primary-button" disabled={busy}>{busy ? 'Signing in…' : 'Sign In'}</button>
    </form>
  </Panel></main>
}
