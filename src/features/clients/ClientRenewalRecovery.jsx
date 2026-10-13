import { useRef, useState } from 'react'
import usePortalActions from '../../hooks/usePortalActions.js'

export default function ClientRenewalRecovery({ pending, services }) {
  const { runAction, reload } = usePortalActions()
  const locked = useRef(false)
  const [busy, setBusy] = useState(false)
  return <section><h1>Check Package Addition</h1><p>The package addition for {pending.draft.clientName ?? 'this client'} needs checking before another package can be added.</p>
    <p>{pending.draft.packageName} · Start date: {pending.draft.startDate}</p>
    <button type="button" disabled={busy} onClick={async () => {
      if (locked.current) return
      locked.current = true; setBusy(true)
      try {
        await runAction(() => services.clientService.renewPackage(pending), { message: 'Package addition confirmed.' })
        await reload()
      } catch (error) {
        if (error.status >= 400 && error.status < 500) await reload()
      } finally { locked.current = false; setBusy(false) }
    }}>{busy ? 'Checking Package…' : 'Check Package Addition'}</button>
  </section>
}
