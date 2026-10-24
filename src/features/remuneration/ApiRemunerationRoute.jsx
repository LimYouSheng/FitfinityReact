import { useEffect, useState } from 'react'
import usePortalData from '../../hooks/usePortalData.js'
import usePortalActions from '../../hooks/usePortalActions.js'
import RemunerationPage from './RemunerationPage.jsx'

/** Load financial records only on the pay route; scope and totals come from verified API responses. */
export default function ApiRemunerationRoute({ cycleKey, trainerId, onNavigate, onOpenSession }) {
  const { snapshot, services } = usePortalData()
  const { runAction, reload } = usePortalActions()
  const { user, sessionGeneration, serverAt, policy } = snapshot
  const selected = user.role === 'owner' ? trainerId : user.trainerId
  const scope = `${user.id}/${sessionGeneration}/${cycleKey ?? ''}/${selected ?? ''}`
  const [state, setState] = useState(null), [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let active = true
    const load = async () => {
      if (cycleKey && selected) {
        const row = await services.remunerationService.detail({ cycle: cycleKey, trainerId: selected })
        return [{ key: row.cycle.key, cycle: row.cycle, isCurrent: !row.closed, trainers: [row] }]
      }
      return services.remunerationService.list({})
    }
    load().then(views => { if (active) setState({ scope, views }) }).catch(error => { if (active) setState({ scope, error }) })
    return () => { active = false }
  }, [scope, cycleKey, selected, serverAt, services, attempt])
  if (!state || state.scope !== scope) return <p role="status">Loading remuneration…</p>
  if (state.error) return <section role="alert"><p>{state.error.message}</p><button onClick={() => setAttempt(value => value + 1)}>Retry remuneration</button></section>
  return <RemunerationPage user={user} views={state.views} policy={{ ...policy, currency: 'SGD', locale: 'en-SG' }} cycleKey={cycleKey} trainerId={trainerId} onNavigate={onNavigate} onOpenSession={onOpenSession} apiApprovalRecovery onApprove={async (cycle, trainer, revision) => {
    await runAction(() => services.remunerationService.approve({ cycle, trainerId: trainer, revision }), { message: 'Remuneration approved.' })
    setAttempt(value => value + 1)
    await reload()
  }} />
}
