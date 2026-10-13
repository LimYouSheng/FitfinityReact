import { useRef, useState } from 'react'
import usePortalActions from '../../hooks/usePortalActions.js'

export default function MessageReadRecovery({ pending, services, renewal = false, cancellation = false }) {
  const { runAction, reload } = usePortalActions()
  const [busy, setBusy] = useState(false)
  const locked = useRef(false)
  return <section><h1>Messages</h1><p>{cancellation ? 'A previous request cancellation needs checking before another request can be cancelled.' : renewal ? 'A previous renewal removal needs checking before another follow-up can be removed.' : 'A previous read-state change needs checking before another message can be changed.'}</p>
    <button disabled={busy} onClick={async () => {
      if (locked.current) return
      locked.current = true; setBusy(true)
      try {
        const operation = cancellation ? 'cancel' : renewal ? 'dismissRenewal' : pending.read ? 'markRead' : 'markUnread'
        const input = renewal ? { id: pending.id, expectedClientVersion: pending.expectedClientVersion } : { id: pending.id, expectedVersion: pending.expectedVersion }
        await runAction(() => (cancellation ? services.requestService : services.messageService)[operation](input), { message: cancellation ? 'Request cancellation confirmed.' : renewal ? 'Renewal removal checked.' : 'Message read state confirmed.' })
        await reload()
      } catch (error) {
        // A definitive cancellation rejection releases its pending command. Refresh the decision.
        if (cancellation && error.status >= 400 && error.status < 500) { try { await reload() } catch { /* Shared load error owns Retry. */ } }
      }
      finally { locked.current = false; setBusy(false) }
    }}>{busy ? 'Checking Message…' : cancellation ? 'Check Request Cancellation' : renewal ? 'Check Renewal Removal' : 'Check Message Read State'}</button>
  </section>
}
