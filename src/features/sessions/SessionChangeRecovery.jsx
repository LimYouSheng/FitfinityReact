import { useRef, useState } from 'react'
import usePortalActions from '../../hooks/usePortalActions.js'

export default function SessionChangeRecovery({ pending, services }) {
  const { runAction, reload } = usePortalActions()
  const locked = useRef(false)
  const [busy, setBusy] = useState(false)
  return <section><h1>Session change</h1><p>Check the original change before starting another. Its booking may already have changed.</p>
    <button disabled={busy} onClick={async () => {
      if (locked.current) return
      locked.current = true; setBusy(true)
      try {
        const input = { sessionId: pending.sessionId, reviewed: pending.reviewed, ...(pending.kind === 'time' ? { patch: pending.patch } : { replacementTrainerId: pending.patch.replacementTrainerId }) }
        await runAction(() => services.sessionService[pending.kind === 'time' ? 'requestTimeChange' : 'requestTrainerChange'](input), { message: 'Original session change confirmed.' })
        await reload()
      } catch (error) {
        if (error.status >= 400 && error.status < 500) { try { await reload() } catch { /* Shared loading failure owns Retry. */ } }
      } finally { locked.current = false; setBusy(false) }
    }}>{busy ? 'Checking…' : 'Check original change'}</button>
  </section>
}
