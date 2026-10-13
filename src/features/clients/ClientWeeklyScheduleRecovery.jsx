import { useRef, useState } from 'react'
import usePortalActions from '../../hooks/usePortalActions.js'
import { scheduleNotification } from '../../app/actionNotifications.js'

export default function ClientWeeklyScheduleRecovery({ pending, services }) {
  const { runAction, reload } = usePortalActions()
  const locked = useRef(false), [busy, setBusy] = useState(false)
  return <section><h1>Check Weekly Schedule</h1><p>The previous weekly-time change for {pending.reviewed.name} needs checking before another schedule is saved.</p>
    <button type="button" disabled={busy} onClick={async () => {
      if (locked.current) return
      locked.current = true; setBusy(true)
      try {
        await runAction(() => services.clientService.saveFixedWeeklySchedule({ id: pending.id, reviewed: pending.reviewed, slots: pending.slots }), result => scheduleNotification('Fixed weekly schedule', result))
        await reload()
      } catch (error) { if (error.status >= 400 && error.status < 500) await reload() }
      finally { locked.current = false; setBusy(false) }
    }}>{busy ? 'Checking…' : 'Check Schedule'}</button>
  </section>
}
