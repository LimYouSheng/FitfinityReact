import { useRef, useState } from 'react'
import usePortalActions from '../../hooks/usePortalActions.js'

export default function TrainerDeactivationRecovery({ pending, services }) {
  const { runAction, reload } = usePortalActions()
  const locked = useRef(false), [busy, setBusy] = useState(false)
  return <section><h1>Check Trainer Deactivation</h1><p>The previous deactivation of {pending.reviewed.name} needs checking before another Trainer can be deactivated.</p>
    <button type="button" disabled={busy} onClick={async () => {
      if (locked.current) return
      locked.current = true; setBusy(true)
      try {
        await runAction(() => services.trainerService.deactivate({ id: pending.id, reviewed: pending.reviewed, replacements: pending.replacements }), { message: 'Trainer deactivation confirmed.' })
        await reload()
      } catch (error) { if (error.status >= 400 && error.status < 500) await reload() }
      finally { locked.current = false; setBusy(false) }
    }}>{busy ? 'Checking…' : 'Check Deactivation'}</button>
  </section>
}
