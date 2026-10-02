import { useEffect, useState } from 'react'
import Panel from '../../components/Panel.jsx'
import { useActionConfirmation } from '../../components/ActionConfirmationProvider.jsx'

export default function ClientEditableText({ title, value, editable, multiline = false, editing, editDisabled, onBeginEdit, onEndEdit, onSave }) {
  const confirmAction = useActionConfirmation()
  const [draft, setDraft] = useState(value)

  useEffect(() => setDraft(value), [value])

  const save = async () => {
    const confirmed = await confirmAction({
      title: `Save ${title.toLowerCase()}?`,
      message: `This will replace the client’s current ${title.toLowerCase()}.`,
      confirmLabel: 'Save Changes',
    })
    if (!confirmed) return
    try {
      await onSave(draft)
      onEndEdit()
    } catch { /* The action banner reports failure; keep the draft open. */ }
  }

  return (
    <Panel className={editing ? 'editing-section' : ''}>
      <div className="section-head">
        <h2>{title}</h2>

        {editable && (!editing ? (
          <button type="button" className="text-action" disabled={editDisabled} onClick={onBeginEdit}>
            Edit
          </button>
        ) : (
          <div className="inline-actions">
            <button
              type="button"
              className="text-action muted-action"
              onClick={() => {
                setDraft(value)
                onEndEdit()
              }}
            >
              Cancel
            </button>
            <button type="button" className="text-action" onClick={save}>Save</button>
          </div>
        ))}
      </div>

      {editing
        ? (
          multiline
            ? <textarea value={draft} onChange={event => setDraft(event.target.value)} />
            : <input value={draft} onChange={event => setDraft(event.target.value)} />
        )
        : <div className="notice">{value}</div>}
    </Panel>
  )
}

