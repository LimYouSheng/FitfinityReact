import { useEffect, useId, useLayoutEffect, useRef, useSyncExternalStore } from 'react'
import ConfirmDialog from '../../components/ConfirmDialog.jsx'
import StaffPersonalFields from '../../components/StaffPersonalFields.jsx'
import { useEditGuard } from '../../components/EditGuardProvider.jsx'
import { adminErrors, adminPayload, createAdminDraft } from '../../app/adminOnboarding.js'
import { createUuid } from '../../utils/uuid.js'

function useCreation(creation) {
  const { setActiveEdit } = useEditGuard()
  const state = useSyncExternalStore(creation.subscribe, creation.getSnapshot)
  const { draft, saving, created } = state
  const dirty = JSON.stringify(draft) !== JSON.stringify(createAdminDraft())
  // Publish the guard in the same commit as the draft, before native Back can run.
  useLayoutEffect(() => {
    setActiveEdit(!created && (dirty || saving) ? 'New Admin' : null)
    return () => setActiveEdit(null)
  }, [created, dirty, saving, setActiveEdit])
  return { ...state, dirty }
}

export function AdminCreationRecovery({ creation }) {
  const { dirty, submitted, created } = useCreation(creation)
  return dirty || submitted || created ? <p role="status">Your Admin setup progress is retained in this tab. Retry loading to verify your account and resume.</p> : null
}

export default function CreateAdminDialog({ today, realAuthentication, creation, onCreate, onClose }) {
  const { draft, errors, saving, submitted, created } = useCreation(creation)
  const form = useRef(null)
  const formId = useId()
  useEffect(() => {
    if (Object.keys(errors).length) form.current?.querySelector('[aria-invalid="true"]')?.focus()
  }, [errors])
  const save = async event => {
    event?.preventDefault()
    if (creation.getSnapshot().saving || created) return
    const validation = adminErrors(draft, today)
    if (Object.keys(validation).length) { creation.update({ errors: validation }); return }
    const version = creation.version()
    if (!creation.update({ saving: true, errors: {} }, version)) return
    let dispatched = false
    try {
      const payload = adminPayload(draft)
      const requestKey = creation.getSnapshot().requestKey ?? createUuid()
      creation.update({ requestKey, submitted: true }, version)
      dispatched = true
      creation.update({ created: await onCreate(payload, requestKey) }, version)
    }
    catch (error) {
      creation.update({ errors: { save: error.message || 'Account setup could not be completed. Retry with the same details.' } }, version)
      // A preparation failure never submitted an account. After dispatch, uncertain failures
      // retain the exact payload/key so retries can reconcile an already-created account.
      if (!dispatched || ['validation_error', 'STAFF_EMAIL_EXISTS'].includes(error.code)) creation.update({ submitted: false, requestKey: null }, version)
    } finally { creation.update({ saving: false }, version) }
  }
  const close = () => { if (!creation.getSnapshot().saving) onClose() }
  return <ConfirmDialog open title="Create Admin" className="create-admin-dialog" confirmForm={formId}
    confirmLabel={saving ? 'Creating…' : submitted ? 'Check Account Setup' : realAuthentication ? 'Create Admin & Send Invitation' : 'Create Admin'}
    confirmDisabled={saving} hideConfirm={Boolean(created)} cancelLabel={created ? 'Done' : 'Cancel'} onCancel={close}
    onKeyDown={event => { if (event.key === 'Escape') { event.stopPropagation(); close() } }}>
    {created ? <div className="stack-gap" role="status">
      <p><strong>{created.name}</strong> has been created as an Admin.</p>
      <p>{created.invitation === 'sent' ? `An invitation email was requested for ${created.email}. They can set their password and MFA, then install the PWA.`
        : created.invitation === 'demo' ? 'This is a demo account. No email was sent.'
        : 'Invitation delivery is not confirmed. Contact support before sending another invitation; the account has been preserved.'}</p>
    </div> : <form id={formId} ref={form} noValidate onSubmit={save}>
      <h3>General Information</h3>
      <fieldset disabled={saving || submitted} className="onboarding-step-body">
        <legend className="visually-hidden">Admin details</legend>
        <div className="onboarding-grid"><StaffPersonalFields draft={draft} errors={errors} onChange={patch => creation.update({ draft: { ...draft, ...patch }, errors: {} })} /></div>
      </fieldset>
      <p className="helper">Admin access includes daily operations. Trainer pay rates, remuneration and privileged account management are restricted.</p>
      {realAuthentication && <p className="helper">An access email will be sent to this address. Password setup and MFA are required.</p>}
      {errors.save && <p className="onboarding-error" role="alert">{errors.save}</p>}
    </form>}
  </ConfirmDialog>
}
