import { useEffect, useState } from 'react'
import usePortalActions from '../../hooks/usePortalActions.js'
import ContentManagementPage from './ContentManagementPage.jsx'

export default function ApiContentWorkspace({ services, generation, detailId, onNavigate, onBack }) {
  const { runAction } = usePortalActions()
  const [result, setResult] = useState(null)
  const [attempt, setAttempt] = useState(0)
  const [checking, setChecking] = useState(false)
  useEffect(() => {
    let current = true
    services.readContent().then(value => { if (current) setResult({ generation, detailId, value }) })
      .catch(error => { if (current) setResult({ generation, detailId, error }) })
    return () => { current = false }
  }, [services, generation, detailId, attempt])
  const retry = () => { setResult(null); setAttempt(value => value + 1) }
  const ready = result?.generation === generation && result.detailId === detailId ? result : null
  if (!ready) return <p role="status">Loading content…</p>
  if (ready.error) return <div role="alert"><p>{ready.error.message}</p><button onClick={retry}>Retry Content</button></div>
  if (ready.value.pending) return <div role="alert"><p>A previous content save needs checking before another change can be saved.</p>
    <button disabled={checking} onClick={async () => {
      setChecking(true)
      try { await runAction(() => services.contentService.save(ready.value.pending), { message: 'Content save confirmed.' }); retry() }
      catch { /* Original intent remains in the adapter; the action banner reports the error. */ }
      finally { setChecking(false) }
    }}>{checking ? 'Checking Content…' : 'Check Previous Content Save'}</button>
  </div>
  return <ContentManagementPage entries={ready.value.entries} detailId={detailId} onNavigate={onNavigate} onBack={onBack} guardUncertain
    onSave={options => runAction(() => services.contentService.save(options), { message: 'Content saved.' })} />
}
