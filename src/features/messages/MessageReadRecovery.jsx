import { useRef, useState } from 'react'
import usePortalActions from '../../hooks/usePortalActions.js'

export default function MessageReadRecovery({ pending, services }) {
  const { runAction, reload } = usePortalActions()
  const [busy, setBusy] = useState(false)
  const locked = useRef(false)
  return <section><h1>Messages</h1><p>A previous read-state change needs checking before another message can be changed.</p>
    <button disabled={busy} onClick={async () => {
      if (locked.current) return
      locked.current = true; setBusy(true)
      try {
        const operation = pending.read ? 'markRead' : 'markUnread'
        await runAction(() => services.messageService[operation]({ id: pending.id, expectedVersion: pending.expectedVersion }), { message: 'Message read state confirmed.' })
        await reload()
      } catch { /* The shared banner reports errors; retain the original pending command. */ }
      finally { locked.current = false; setBusy(false) }
    }}>{busy ? 'Checking Message…' : 'Check Message Read State'}</button>
  </section>
}
