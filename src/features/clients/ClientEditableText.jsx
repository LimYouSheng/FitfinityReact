import { useContext, useEffect, useRef, useState } from 'react'
import { PortalData } from '../../hooks/usePortalData.js'
import Panel from '../../components/Panel.jsx'
import { useActionConfirmation } from '../../components/ActionConfirmationProvider.jsx'

export default function ClientEditableText({ title, value, editable, multiline = false, editing, editDisabled, onBeginEdit, onEndEdit, onSave, version, onSaved, recoveryKey }) {
  const recovery = useContext(PortalData)?.draftRecovery
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

  useEffect(() => { if (!editable) recovery?.remove(recoveryKey) }, [editable, recovery, recoveryKey])
  const changeDraft = event => {
    setDraft(event.target.value)
    if (recoveryKey) recovery?.set(recoveryKey, { draft: event.target.value, reviewed: reviewed.current })
  }
  const begin = () => {
    const retained = recoveryKey && recovery?.get(recoveryKey)
    reviewed.current = retained?.reviewed ?? { expectedVersion: version }
    setDraft(retained?.draft ?? value)
    onBeginEdit()
  }
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
      recovery?.remove(recoveryKey)
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
          <button type="button" className="text-action" disabled={editDisabled} onClick={begin}>
            Edit
          </button>
        ) : (
          <div className="inline-actions">
            <button
              type="button"
              className="text-action muted-action"
              disabled={busy}
              onClick={() => {
                recovery?.remove(recoveryKey)
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

      {!editing && editable && recoveryKey && recovery?.get(recoveryKey) && <p role="status">Your unsaved draft is available. Choose Edit to resume it.</p>}
      {editing
        ? (
          multiline
            ? <textarea aria-label={title} disabled={busy} value={draft} onChange={changeDraft} />
            : <input aria-label={title} disabled={busy} value={draft} onChange={changeDraft} />
        )
        : <div className="notice">{value}</div>}
    </Panel>
  )
}

