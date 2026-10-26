import { useEffect, useState } from 'react'
import { useActionConfirmation } from '../../components/ActionConfirmationProvider.jsx'

/** Keep an uncertain command recoverable without retaining a private editor on screen. */
export default function ClientNoteRecovery({ services, generation, serverAt, attempt, onRecovered }) {
  const confirm = useActionConfirmation()
  const [state, setState] = useState(null)
  const [checking, setChecking] = useState(false)
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    if (!services.recoverClientNotes) return
    let current = true
    services.recoverClientNotes({}).then(result => {
      if (!current) return
      setState({ generation, ...result })
      if (result.recovered) void onRecovered()
    }).catch(error => { if (current) setState({ generation, pending: true, error: error.message }) })
    return () => { current = false }
  }, [services, generation, serverAt, attempt, retry, onRecovered])
  if (!state || state.generation !== generation || !state.pending) return null
  return <section role="alert">
    <p>An earlier notes save needs checking. Cancelling an editor does not cancel a request already sent.</p>
    {state.error && <p>{state.error}</p>}
    <button type="button" disabled={checking} onClick={() => setRetry(value => value + 1)}>Check Previous Notes Save</button>
    <button type="button" disabled={checking} onClick={async () => {
      const accepted = await confirm({ title: 'Retry original notes save?', message: 'Check the original receipt, then retry only the original values if no completed receipt exists. Later edits will not be sent.', confirmLabel: 'Retry Original Save' })
      if (!accepted) return
      setChecking(true)
      try { const saved = await services.resumeClientNotes({}); setRetry(value => value + 1); if (saved) await onRecovered() }
      catch (error) { setState({ generation, pending: true, error: error.message }); setRetry(value => value + 1) }
      finally { setChecking(false) }
    }}>Retry Original Notes Save</button>
  </section>
}
