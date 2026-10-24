import { useRef, useState } from 'react'
import usePortalActions from '../../hooks/usePortalActions.js'

export default function RemunerationRecovery({ pending, services }) {
  const { runAction, reload } = usePortalActions()
  const locked = useRef(false)
  const [busy, setBusy] = useState(false)
  return <section><h1>Remuneration approval</h1><p>Check the original remuneration approval save before making another change.</p>
    <button disabled={busy} onClick={async () => {
      if (locked.current) return
      locked.current = true; setBusy(true)
      try {
        await runAction(() => services.remunerationService.approve(pending), { message: 'Original remuneration approval confirmed.' })
        await reload()
      } catch (error) {
        if (error.status >= 400 && error.status < 500) { try { await reload() } catch { /* Shared loading failure owns Retry. */ } }
      } finally { locked.current = false; setBusy(false) }
    }}>{busy ? 'Checking…' : 'Check original remuneration approval'}</button>
  </section>
}
