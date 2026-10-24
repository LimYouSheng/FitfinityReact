import { useRef, useState } from 'react'
import usePortalActions from '../../hooks/usePortalActions.js'

export default function SessionAcknowledgementRecovery({ pending, services }) {
  const { runAction, reload } = usePortalActions()
  const locked = useRef(false)
  const [busy, setBusy] = useState(false)
  return <section><h1>Session acknowledgement</h1><p>Check the original acknowledgement save before making another change.</p>
    <p>{pending.acknowledgement.method === 'signature' ? 'Client signature' : 'Late / no-show'}</p>
    <button disabled={busy} onClick={async () => {
      if (locked.current) return
      locked.current = true; setBusy(true)
      try {
        await runAction(() => services.sessionService.acknowledge(pending), { message: 'Original session acknowledgement confirmed.' })
        await reload()
      } catch (error) {
        if (error.status >= 400 && error.status < 500) { try { await reload() } catch { /* Shared loading failure owns Retry. */ } }
      } finally { locked.current = false; setBusy(false) }
    }}>{busy ? 'Checking…' : 'Check original acknowledgement'}</button>
  </section>
}
