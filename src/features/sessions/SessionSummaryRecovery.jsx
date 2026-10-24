import { useRef, useState } from 'react'
import usePortalActions from '../../hooks/usePortalActions.js'

export default function SessionSummaryRecovery({ pending, services }) {
  const { runAction, reload } = usePortalActions()
  const locked = useRef(false)
  const [busy, setBusy] = useState(false)
  return <section><h1>Client-facing summary</h1><p>Check the original summary save before making another change.</p>
    <p>{pending.summary}</p>
    <button disabled={busy} onClick={async () => {
      if (locked.current) return
      locked.current = true; setBusy(true)
      try {
        await runAction(() => services.sessionService.saveClientSummary(pending), { message: 'Original client summary confirmed.' })
        await reload()
      } catch (error) {
        if (error.status >= 400 && error.status < 500) { try { await reload() } catch { /* Shared loading failure owns Retry. */ } }
      } finally { locked.current = false; setBusy(false) }
    }}>{busy ? 'Checking…' : 'Check original summary'}</button>
  </section>
}
