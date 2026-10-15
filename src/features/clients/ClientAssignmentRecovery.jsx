import { useRef, useState } from 'react'
import usePortalActions from '../../hooks/usePortalActions.js'

export default function ClientAssignmentRecovery({ pending, services }) {
  const { runAction, reload } = usePortalActions()
  const locked = useRef(false), [busy, setBusy] = useState(false)
  return <section><h1>Check Trainer Reassignment</h1><p>The previous reassignment of {pending.reviewed.name} needs checking before another client can be reassigned.</p>
    <button type="button" disabled={busy} onClick={async () => {
      if (locked.current) return
      locked.current = true; setBusy(true)
      try {
        await runAction(() => services.clientService.reassignTrainer({ id: pending.id, draft: { reviewed: pending.reviewed, trainerId: pending.trainerId } }), { message: 'Trainer reassignment confirmed.' })
        await reload()
      } catch (error) { if (error.status >= 400 && error.status < 500) await reload() }
      finally { locked.current = false; setBusy(false) }
    }}>{busy ? 'Checking…' : 'Check Reassignment'}</button>
  </section>
}
