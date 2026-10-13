import { useEffect, useRef, useState } from 'react'
import Panel from '../../components/Panel.jsx'
import { useActionConfirmation } from '../../components/ActionConfirmationProvider.jsx'

export default function ClientEditableText({ title, value, editable, multiline = false, editing, editDisabled, onBeginEdit, onEndEdit, onSave, version, onSaved }) {
  const confirmAction = useActionConfirmation()
  const [draft, setDraft] = useState(value)

  const reviewed = useRef(null)
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState(false)
  useEffect(() => { if (!editing) setDraft(value) }, [value, editing])
  useEffect(() => {
    if (!saved || editing) return
    setSaved(false)
    onSaved?.()
  }, [saved, editing, onSaved])

  const save = async () => {
    if (busy) return
    const confirmed = await confirmAction({
      title: `Save ${title.toLowerCase()}?`,
      message: `This will replace the client’s current ${title.toLowerCase()}.`,
      confirmLabel: 'Save Changes',
    })
    if (!confirmed) return
    try {
      setBusy(true)
      await onSave(draft, reviewed.current)
      onEndEdit()
      setSaved(true)
    } catch { /* The action banner reports failure; keep the draft open. */ }
    finally { setBusy(false) }
  }

  return (
    <Panel className={editing ? 'editing-section' : ''}>
      <div className="section-head">
        <h2>{title}</h2>

        {editable && (!editing ? (
          <button type="button" className="text-action" disabled={editDisabled} onClick={() => { reviewed.current = { expectedVersion: version }; onBeginEdit() }}>
            Edit
          </button>
        ) : (
          <div className="inline-actions">
            <button
              type="button"
              className="text-action muted-action"
              disabled={busy}
              onClick={() => {
                setDraft(value)
                onEndEdit()
              }}
            >
              Cancel
            </button>
            <button type="button" className="text-action" disabled={busy} onClick={save}>Save</button>
          </div>
        ))}
      </div>

      {editing
        ? (
          multiline
            ? <textarea aria-label={title} disabled={busy} value={draft} onChange={event => setDraft(event.target.value)} />
            : <input aria-label={title} disabled={busy} value={draft} onChange={event => setDraft(event.target.value)} />
        )
        : <div className="notice">{value}</div>}
    </Panel>
  )
}

