import { useCallback, useEffect, useState } from 'react'
import { useActionConfirmation } from './ActionConfirmationProvider.jsx'
import { PORTAL_ACTION_FAILED } from './NotificationProvider.jsx'
import { useEditGuard } from './EditGuardProvider.jsx'
import usePortalData from '../hooks/usePortalData.js'
import usePortalActions from '../hooks/usePortalActions.js'

/** Recovery lives above routes; Cancel never abandons an already-sent command. */
export default function ProfileSaveRecovery() {
  const { snapshot, services } = usePortalData()
  const { activeEdit } = useEditGuard()
  const { reload, runAction } = usePortalActions()
  const recovered = useCallback(() => runAction(reload, { message: 'Previous save confirmed.' }), [reload, runAction])
  return <ProfileSaveRecoveryPanel editing={Boolean(activeEdit)} services={services} generation={snapshot.sessionGeneration} serverAt={snapshot.serverAt} onRecovered={recovered} />
}

export function ProfileSaveRecoveryPanel({ services, generation, serverAt, onRecovered, editing = false }) {
  const confirm = useActionConfirmation()
  const [state, setState] = useState(null)
  const [checking, setChecking] = useState(false)
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    const failed = () => setRetry(value => value + 1)
    window.addEventListener(PORTAL_ACTION_FAILED, failed)
    return () => window.removeEventListener(PORTAL_ACTION_FAILED, failed)
  }, [])
  useEffect(() => {
    // The original editor must consume its own successful retry. Clearing its
    // creation command in the background could turn a later Save into a new create.
    if (editing || !services.recoverProfileSaves) return
    let current = true
    services.recoverProfileSaves({}).then(result => {
      if (!current) return
      setState({ generation, ...result })
    }).catch(error => { if (current) setState({ generation, pending: [], error: error.message }) })
    return () => { current = false }
  }, [services, generation, serverAt, retry, onRecovered, editing])
  if (editing || !state || state.generation !== generation) return null
  return <>
    {state.error && <section role="alert"><p>{state.error}</p><button type="button" onClick={() => setRetry(value => value + 1)}>Refresh Save Recovery</button></section>}
    {state.pending.map(({ kind, label, error }) => <section role="alert" key={kind}>
      <p>An earlier {label.toLowerCase()} save needs checking. Cancelling an editor does not cancel a request already sent.</p>
      {error && <p>{error}</p>}
      <button type="button" disabled={checking} onClick={async () => {
        setChecking(true)
        try {
          const result = await services.recoverProfileSaves({ kind })
          setState({ generation, ...result })
          if (result.recovered) await onRecovered()
        } catch (error) { setState(current => ({ ...current, error: error.message })) }
        finally { setChecking(false) }
      }}>Check Previous {label} Save</button>
      <button type="button" disabled={checking} onClick={async () => {
        const accepted = await confirm({ title: `Retry original ${label.toLowerCase()} save?`, message: 'Check the original receipt, then retry only the original values if no completed receipt exists. Later edits will not be sent.', confirmLabel: 'Retry Original Save' })
        if (!accepted) return
        setChecking(true)
        try { const saved = await services.resumeProfileSave({ kind }); setRetry(value => value + 1); if (saved) await onRecovered() }
        catch (error) { const result = await services.recoverProfileSaves({}); setState({ generation, ...result, error: error.message }) }
        finally { setChecking(false) }
      }}>Retry Original {label} Save</button>
    </section>)}
  </>
}
