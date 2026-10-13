import { useRef, useState } from 'react'
import usePortalActions from '../../hooks/usePortalActions.js'

export default function MessageReadRecovery({ pending, services, renewal = false }) {
  const { runAction, reload } = usePortalActions()
  const [busy, setBusy] = useState(false)
  const locked = useRef(false)
  return <section><h1>Messages</h1><p>{renewal ? 'A previous renewal removal needs checking before another follow-up can be removed.' : 'A previous read-state change needs checking before another message can be changed.'}</p>
    <button disabled={busy} onClick={async () => {
      if (locked.current) return
      locked.current = true; setBusy(true)
      try {
        const operation = renewal ? 'dismissRenewal' : pending.read ? 'markRead' : 'markUnread'
        const input = renewal ? { id: pending.id, expectedClientVersion: pending.expectedClientVersion } : { id: pending.id, expectedVersion: pending.expectedVersion }
        await runAction(() => services.messageService[operation](input), { message: renewal ? 'Renewal removal checked.' : 'Message read state confirmed.' })
        await reload()
      } catch { /* The shared banner reports errors; retain the original pending command. */ }
      finally { locked.current = false; setBusy(false) }
    }}>{busy ? 'Checking Message…' : renewal ? 'Check Renewal Removal' : 'Check Message Read State'}</button>
  </section>
}
