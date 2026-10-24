import { useRef, useState } from 'react'
import usePortalActions from '../../hooks/usePortalActions.js'

export default function SessionOutcomeRecovery({ pending, services }) {
  const { runAction, reload } = usePortalActions()
  const locked = useRef(false)
  const [busy, setBusy] = useState(false)
  return <section><h1>Session outcome</h1><p>Check the original outcome save before making another change.</p>
    <p>{pending.outcome.trainerComments}</p>
    <ul>{pending.outcome.exerciseResults.map(row => <li key={row.id}>{row.name}: {row.loadKg} kg · {row.reps} reps · {row.sets} sets</li>)}</ul>
    <button disabled={busy} onClick={async () => {
      if (locked.current) return
      locked.current = true; setBusy(true)
      try {
        await runAction(() => services.sessionService.saveOutcome(pending), { message: 'Original session outcome confirmed.' })
        await reload()
      } catch (error) {
        if (error.status >= 400 && error.status < 500) { try { await reload() } catch { /* Shared loading failure owns Retry. */ } }
      } finally { locked.current = false; setBusy(false) }
    }}>{busy ? 'Checking…' : 'Check original outcome'}</button>
  </section>
}
