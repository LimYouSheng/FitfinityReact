import { useRef, useState } from 'react'
import ConfirmDialog from '../../components/ConfirmDialog.jsx'

/** Keep the preview and original intent visible until confirmation or reconciliation finishes. */
export default function PreviousPlanDialog({ available, onPreview, onCopy, onBegin, onEnd }) {
  const [preview, setPreview] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const locked = useRef(false)
  const open = async () => {
    if (locked.current) return
    locked.current = true; setBusy(true); setError(''); onBegin()
    try { const value = await onPreview(); setPreview(value) }
    catch (failure) { setError(failure.message); onEnd() }
    finally { locked.current = false; setBusy(false) }
  }
  const close = () => {
    if (locked.current || preview?.uncertain) return
    setPreview(null); setError(''); onEnd()
  }
  const copy = async () => {
    if (locked.current) return
    locked.current = true; setBusy(true); setError('')
    try { await onCopy(preview); setPreview(null); onEnd() }
    catch (failure) {
      setError(failure.message)
      setPreview(current => ({ ...current, uncertain: !(failure.status >= 400 && failure.status < 500), rejected: failure.status >= 400 && failure.status < 500 }))
    } finally { locked.current = false; setBusy(false) }
  }
  return <>
    {available && <button type="button" className="text-action" disabled={busy} onClick={open}>Previous Plan</button>}
    {!preview && error && <p role="alert">{error}</p>}
    <ConfirmDialog open={Boolean(preview)} title="Previous exercise plan" onCancel={close} onConfirm={copy}
      cancelDisabled={busy || preview?.uncertain} hideConfirm={!preview?.source} confirmDisabled={busy || preview?.rejected}
      confirmLabel={busy ? 'Checking…' : preview?.uncertain ? 'Check original copy' : 'Replace Plan'}>
      {preview?.source ? <>
        {preview.source.date && <p>From {preview.source.date}</p>}
        <p>Confirm to replace this session’s exercise plan. Videos remain with their original session.</p>
        <ol>{preview.source.items.map(item => <li key={item.id}><strong>{item.name}</strong>
          <p>{[item.weight, item.reps && `${item.reps} reps`, item.rounds && `${item.rounds} rounds`, item.rest && `${item.rest} rest`].filter(Boolean).join(' · ')}</p>
          {(item.customDetails ?? []).map(detail => <p key={detail.id}>{detail.value}</p>)}
        </li>)}</ol>
      </> : <p>No previous exercise plan is available.</p>}
      {preview?.uncertain && <p role="status">The copy outcome is unknown. Check the original copy before making another change.</p>}
      {error && <p role="alert">{error}</p>}
    </ConfirmDialog>
  </>
}
