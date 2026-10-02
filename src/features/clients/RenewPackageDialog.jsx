import { useState } from 'react'
import ConfirmDialog from '../../components/ConfirmDialog.jsx'
import { useEditGuard } from '../../components/EditGuardProvider.jsx'
import { packageDraftForClient } from '../../app/packageRenewal.js'
import ClientOnboardingForm from './ClientOnboardingForm.jsx'

export default function RenewPackageDialog({ client, clients = [], trainers, sessions, packages, policy, today, onSave, onClose }) {
  const { guardNavigation } = useEditGuard()
  const [initial] = useState(() => packageDraftForClient(client, sessions, packages, today))
  const [saving, setSaving] = useState(false)
  const cancel = () => { if (!saving) guardNavigation(onClose) }
  return <ConfirmDialog open title="Add Package" hideConfirm onCancel={cancel}>
    <ClientOnboardingForm packageDraft={initial} packages={packages} policy={policy} trainers={trainers} sessions={sessions} clients={clients}
      onCancel={cancel} onCreated={onClose} onCreate={async draft => {
        setSaving(true)
        try { return await onSave(draft) ?? { id: client.id } }
        finally { setSaving(false) }
      }} />
  </ConfirmDialog>
}
