import { useRef, useState } from 'react'
import usePortalActions from '../../hooks/usePortalActions.js'

export default function ExerciseLibraryRecovery({ pending, services, onRecovered }) {
  const { runAction, reload } = usePortalActions()
  const locked = useRef(false)
  const [busy, setBusy] = useState(false)
  return <section><h1>Exercise Library</h1><p>Check the original exercise save before making another change.</p><p>{pending.draft.name}</p>
    <button disabled={busy} onClick={async () => {
      if (locked.current) return
      locked.current = true; setBusy(true)
      try {
        const saved = await runAction(() => services.exerciseLibraryService.save(pending), { message: 'Original exercise save confirmed.' })
        await reload()
        onRecovered(saved)
      } catch (error) {
        if (error.status >= 400 && error.status < 500) { try { await reload() } catch { /* Shared loading failure owns Retry. */ } }
      } finally { locked.current = false; setBusy(false) }
    }}>{busy ? 'Checking…' : 'Check original exercise save'}</button>
  </section>
}
