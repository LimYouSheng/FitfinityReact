import { useRef, useState } from 'react'
import usePortalActions from '../../hooks/usePortalActions.js'

export default function ClientReactivationRecovery({ pending, services, packageMode = false }) {
  const { runAction, reload } = usePortalActions()
  const locked = useRef(false)
  const [busy, setBusy] = useState(false)
  const target = packageMode ? 'Package' : 'Client'
  return <section><h1>Check {target} Reactivation</h1><p>The previous reactivation of {pending.reviewed.name} needs checking before another {target.toLowerCase()} can be reactivated.</p>
    <button type="button" disabled={busy} onClick={async () => {
      if (locked.current) return
      locked.current = true; setBusy(true)
      try {
        await runAction(() => packageMode ? services.clientService.reactivatePackage({ id: pending.id, options: { packageId: pending.packageId, reviewed: pending.reviewed, dates: pending.dates } }) : services.clientService.reactivate(pending), { message: `${target} reactivation confirmed.` })
        await reload()
      } catch (error) { if (packageMode && error.status >= 400 && error.status < 500) await reload() }
      finally { locked.current = false; setBusy(false) }
    }}>{busy ? `Checking ${target}…` : 'Check Reactivation'}</button>
  </section>
}
