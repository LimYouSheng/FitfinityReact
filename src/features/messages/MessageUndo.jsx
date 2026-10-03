import { useEffect, useRef, useState } from 'react'
import { useActionConfirmation } from '../../components/ActionConfirmationProvider.jsx'
import { formatTimestamp } from '../../utils/date.js'

export default function MessageUndo({ message, timeZone, onUndo }) {
  const confirm = useActionConfirmation()
  const [now, setNow] = useState(Date.now)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState('')
  const locked = useRef(false), mounted = useRef(false)
  const undo = message.undo
  const expiresAt = Date.parse(undo.expiresAt)
  useEffect(() => {
    mounted.current = true
    const update = () => setNow(Date.now())
    const timer = setTimeout(update, Math.max(0, Math.min(2147483647, expiresAt - Date.now())))
    window.addEventListener('focus', update)
    return () => { mounted.current = false; clearTimeout(timer); window.removeEventListener('focus', update) }
  }, [expiresAt])
  const undone = done || undo.status === 'undone'
  const expired = undo.status === 'expired' || !Number.isFinite(expiresAt) || now >= expiresAt
  const perform = async event => {
    event.stopPropagation()
    if (locked.current || undone || expired) return
    locked.current = true; setBusy(true); setError('')
    try {
      const accepted = await confirm({ title: 'Undo session change?', confirmLabel: 'Undo Change',
        message: `Undo “${message.title}”${undo.count > 1 ? ` for all ${undo.count} affected sessions` : ''}? The original history will remain.${undo.notice ? ` ${undo.notice}` : ''}` })
      if (!accepted || !mounted.current) return
      if (Date.now() >= expiresAt) { setNow(Date.now()); throw new Error('Undo expired. The 24-hour window has ended.') }
      await onUndo(message.id)
      if (mounted.current) setDone(true)
    } catch (failure) { if (mounted.current) setError(failure.message || 'Could not undo the change. Try again.') }
    finally { locked.current = false; if (mounted.current) setBusy(false) }
  }
  return <div className="message-undo-action" onClick={event => event.stopPropagation()}>
    {undone ? <strong role="status">Undone</strong> : expired ? <span>Undo expired</span> : <>
      <button type="button" className="primary-button small" aria-label={`Undo ${message.title}`} disabled={busy || undo.status === 'blocked' || !onUndo} onClick={perform}>{busy ? 'Please wait…' : 'Undo'}</button>
      <span>Until {formatTimestamp(undo.expiresAt, timeZone)}</span>
      {undo.reason && <span>{undo.reason}</span>}
    </>}
    {error && <p role="alert">{error}</p>}
  </div>
}
