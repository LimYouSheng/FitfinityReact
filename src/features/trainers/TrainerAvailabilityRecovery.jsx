import { useRef, useState } from 'react'
import usePortalActions from '../../hooks/usePortalActions.js'
import { scheduleNotification } from '../../app/actionNotifications.js'

export default function TrainerAvailabilityRecovery({ pending, services }) {
  const { runAction, reload } = usePortalActions()
  const locked = useRef(false)
  const [busy, setBusy] = useState(false)
  return <section><h1>Check Availability Save</h1><p>Your previous availability change needs checking before another change can be made.</p>
    <button type="button" disabled={busy} onClick={async () => {
      if (locked.current) return
      locked.current = true; setBusy(true)
      try {
        await runAction(() => services.trainerService.saveAvailability(pending), result => scheduleNotification('Availability', result))
        await reload()
      } catch (error) {
        if (error.status >= 400 && error.status < 500) { try { await reload() } catch { /* Shared load error owns Retry. */ } }
      } finally { locked.current = false; setBusy(false) }
    }}>{busy ? 'Checking Availability…' : 'Check Availability Save'}</button>
  </section>
}
