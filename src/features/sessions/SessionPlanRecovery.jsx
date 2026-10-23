import { useRef, useState } from 'react'
import usePortalActions from '../../hooks/usePortalActions.js'

export default function SessionPlanRecovery({ pending, services }) {
  const { runAction, reload } = usePortalActions()
  const locked = useRef(false)
  const [busy, setBusy] = useState(false)
  return <section><h1>Exercise plan</h1><p>Check the original plan save before making another change.</p>
    <ol>{pending.items.map(item => <li key={item.id}>{item.name}</li>)}</ol>
    <button disabled={busy} onClick={async () => {
      if (locked.current) return
      locked.current = true; setBusy(true)
      try {
        await runAction(() => services.sessionService.saveExercisePlan(pending), { message: 'Original exercise plan confirmed.' })
        await reload()
      } catch (error) {
        if (error.status >= 400 && error.status < 500) { try { await reload() } catch { /* Shared loading failure owns Retry. */ } }
      } finally { locked.current = false; setBusy(false) }
    }}>{busy ? 'Checking…' : 'Check original save'}</button>
  </section>
}
