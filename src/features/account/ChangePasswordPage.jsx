import { useEffect, useRef, useState } from 'react'
import Panel from '../../components/Panel.jsx'
import { useEditGuard } from '../../components/EditGuardProvider.jsx'
import { useActionConfirmation } from '../../components/ActionConfirmationProvider.jsx'
import { useNotifications } from '../../components/NotificationProvider.jsx'

export default function ChangePasswordPage({ policy, onSave, onBack }) {
  const [draft, setDraft] = useState({ currentPassword: '', newPassword: '', confirmation: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const pending = useRef(false)
  const { setActiveEdit } = useEditGuard()
  const confirm = useActionConfirmation()
  const { notify } = useNotifications()
  const requirements = `Use ${policy.minimumLength}–${policy.maximumLength} characters for the new password.${policy.spacesAllowed === false ? ' No spaces or other whitespace.' : ''} It must differ from your current password and match the confirmation.`
  const showRequirements = () => notify({ tone: 'info', message: requirements })
  const dirty = Object.values(draft).some(Boolean)
  useEffect(() => { setActiveEdit(dirty ? 'Change password' : null); return () => setActiveEdit(null) }, [dirty, setActiveEdit])
  const submit = async event => {
    event.preventDefault()
    if (pending.current) return
    setError('')
    if (!draft.currentPassword) { notify({ tone: 'error', message: 'Enter your current password.' }); return }
    const length = policy.spacesAllowed === false ? Array.from(draft.newPassword).length : draft.newPassword.length
    if (length < policy.minimumLength || length > policy.maximumLength || (policy.spacesAllowed === false && /\s/u.test(draft.newPassword))) { notify({ tone: 'error', message: requirements }); return }
    if (draft.newPassword !== draft.confirmation) { notify({ tone: 'error', message: 'The new passwords do not match.' }); return }
    if (draft.newPassword === draft.currentPassword) { notify({ tone: 'error', message: 'Choose a different new password.' }); return }
    pending.current = true; setBusy(true); setError('')
    try {
      if (!await confirm({ title: 'Change password?', message: policy.spacesAllowed === false ? 'The new password takes effect immediately and signs out all sessions.' : 'The new password takes effect immediately.', confirmLabel: 'Change Password' })) return
      await onSave(draft)
      setDraft({ currentPassword: '', newPassword: '', confirmation: '' }); setActiveEdit(null)
    } catch (failure) { setError(failure.message || 'Unable to change the password. Try again.') }
    finally { pending.current = false; setBusy(false) }
  }
  return <>
    <div className="page-head"><h1>Change Password</h1></div>
    <Panel className={dirty ? 'editing-section' : ''}><form className="account-form" onSubmit={submit} noValidate>
      <fieldset disabled={busy}>{[['currentPassword', 'Current password', 'current-password'], ['newPassword', 'New password', 'new-password'], ['confirmation', 'Confirm new password', 'new-password']].map(([key, label, autocomplete]) => <label key={key}>{label}<input aria-label={label} type="password" autoComplete={autocomplete} required value={draft[key]} onFocus={key === 'newPassword' ? showRequirements : undefined} onChange={event => { setDraft(value => ({ ...value, [key]: event.target.value })); setError('') }} /></label>)}</fieldset>
      <button type="button" className="text-action" disabled={busy} onClick={showRequirements}>Password requirements</button>
      {error && <p role="alert" className="validation-copy">{error}</p>}
      <div className="inline-actions"><button type="button" className="secondary-button" disabled={busy} onClick={onBack}>Cancel</button><button type="submit" className="primary-button" disabled={busy}>Save Password</button></div>
    </form></Panel>
  </>
}
