import { useRef, useState } from 'react'
import usePortalActions from '../../hooks/usePortalActions.js'

export default function ClientDeactivationRecovery({ pending, services }) {
  const { runAction, reload } = usePortalActions()
  const locked = useRef(false)
  const [busy, setBusy] = useState(false)
  return <section><h1>Check Client Deactivation</h1><p>The previous deactivation of {pending.reviewed.name} needs checking before another client can be deactivated.</p>
    <button type="button" disabled={busy} onClick={async () => {
      if (locked.current) return
      locked.current = true; setBusy(true)
      try {
        await runAction(() => services.clientService.deactivate(pending), { message: 'Client deactivation confirmed.' })
        await reload()
      } catch { /* Keep the original review; the shared action banner reports the error. */ }
      finally { locked.current = false; setBusy(false) }
    }}>{busy ? 'Checking Client…' : 'Check Deactivation'}</button>
  </section>
}
