import { useEffect, useState } from 'react'
import { CUSTOM_EXERCISE, exerciseChoiceFor } from '../../app/exerciseLibrary.js'
import { validateExercisePlan } from '../../app/sessionRules.js'
import { useActionConfirmation } from '../../components/ActionConfirmationProvider.jsx'
import ExerciseNamePicker from './ExerciseNamePicker.jsx'
import ExerciseVideoDialog from './ExerciseVideoDialog.jsx'

const FIELDS = [
  ['weight', 'Weight', 'e.g. 16 kg'],
  ['reps', 'Reps', 'e.g. 10'],
  ['rounds', 'Rounds', 'e.g. 3'],
  ['rest', 'Rest', 'e.g. 60 sec'],
]

const DEFAULT_EXERCISE_FIELDS = {
  reps: '8',
  rounds: '2',
  rest: '60 sec',
}

const blankExercise = () => ({
  id: `draft-${Date.now()}`,
  exerciseChoice: CUSTOM_EXERCISE,
  name: '',
  weight: '',
  customDetails: [],
  ...DEFAULT_EXERCISE_FIELDS,
  videoAttached: false,
})

const editableItems = items => items.map(item => ({
  ...item,
  reps: item.reps || DEFAULT_EXERCISE_FIELDS.reps,
  rounds: item.rounds || DEFAULT_EXERCISE_FIELDS.rounds,
  rest: item.rest || DEFAULT_EXERCISE_FIELDS.rest,
  exerciseChoice: exerciseChoiceFor(item.name),
  customDetails: (item.customDetails ?? []).map((detail, index) => ({
    id: detail.id ?? `detail-${item.id}-${index + 1}`,
    value: typeof detail === 'string' ? detail : detail.value ?? '',
  })),
}))

function CameraIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 8.5h3l1.4-2h7.2l1.4 2h3v10H4z" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
      <circle cx="12" cy="13.5" r="3.2" fill="none" stroke="currentColor" strokeWidth="1.7" />
    </svg>
  )
}

export default function ExercisePlanEditor({
  items,
  sessionId,
  canEdit,
  editing,
  onBeginEdit,
  onEndEdit,
  onSave,
  onToggleVideo,
}) {
  const confirmAction = useActionConfirmation()
  const [draft, setDraft] = useState(() => editableItems(items))
  const [pendingId, setPendingId] = useState(null)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [videoExercise, setVideoExercise] = useState(null)
  const hasBlankName = draft.some(item => !item.name.trim())

  useEffect(() => {
    if (!editing) setDraft(editableItems(items))
  }, [editing, items])

  const startPlan = () => {
    const first = blankExercise()
    setDraft([first])
    setPendingId(first.id)
    setError('')
    onBeginEdit()
  }

  const editPlan = () => {
    setDraft(editableItems(items))
    setPendingId(null)
    setError('')
    onBeginEdit()
  }

  const addExercise = () => {
    const next = blankExercise()
    setDraft(current => [next, ...current])
    setPendingId(next.id)
    setError('')
  }

  const update = (id, field, value) => {
    setDraft(current => current.map(item => item.id === id ? { ...item, [field]: value } : item))
    if (field === 'name' && value.trim() && pendingId === id) setPendingId(null)
    setError('')
  }

  const chooseExercise = (id, choice) => {
    setDraft(current => current.map(item => item.id === id
      ? { ...item, exerciseChoice: choice, name: choice === CUSTOM_EXERCISE ? '' : choice }
      : item))
    if (choice !== CUSTOM_EXERCISE && pendingId === id) setPendingId(null)
    setError('')
  }

  const remove = id => {
    setDraft(current => current.filter(item => item.id !== id))
    if (pendingId === id) setPendingId(null)
    setError('')
  }

  const addDetail = id => {
    setDraft(current => current.map(item => item.id === id
      ? {
          ...item,
          customDetails: [
            ...item.customDetails,
            { id: `detail-${item.id}-${Date.now()}`, value: '' },
          ],
        }
      : item))
  }

  const updateDetail = (exerciseId, detailId, value) => {
    setDraft(current => current.map(item => item.id === exerciseId
      ? {
          ...item,
          customDetails: item.customDetails.map(detail => detail.id === detailId ? { ...detail, value } : detail),
        }
      : item))
  }

  const removeDetail = (exerciseId, detailId) => {
    setDraft(current => current.map(item => item.id === exerciseId
      ? { ...item, customDetails: item.customDetails.filter(detail => detail.id !== detailId) }
      : item))
  }

  const cancelEditing = () => {
    setDraft(editableItems(items))
    setPendingId(null)
    setError('')
    onEndEdit()
  }

  const save = async () => {
    const validation = validateExercisePlan(draft)
    if (validation) {
      setError(validation)
      return
    }

    const confirmed = await confirmAction({
      title: 'Save exercise plan?',
      message: `This will save ${draft.length} exercise${draft.length === 1 ? '' : 's'} and replace the current plan for this session. Videos can be filmed after the plan is saved.`,
      confirmLabel: 'Save Plan',
    })
    if (!confirmed) return

    setSaving(true)
    setError('')
    try {
      await onSave(draft)
      setPendingId(null)
      onEndEdit()
    } catch (saveError) {
      setError(saveError.message)
    } finally {
      setSaving(false)
    }
  }

  const headerActions = editing ? (
    <div className="exercise-edit-actions">
      <button type="button" className="secondary-button" aria-label="Add Exercise" disabled={hasBlankName} onClick={addExercise}>+ Exercise</button>
      <button type="button" className="secondary-button" disabled={saving} onClick={cancelEditing}>Cancel</button>
      <button type="button" className="primary-button" disabled={saving || !draft.length || hasBlankName} onClick={save}>{saving ? 'Saving…' : 'Save'}</button>
    </div>
  ) : canEdit && items.length ? (
    <button
      type="button"
      className="text-action"
      aria-label="Edit exercise plan"
      onClick={editPlan}
    >
      Edit
    </button>
  ) : null

  return (
    <>
      <div className="section-head exercise-plan-head">
        <div>
          <h2>Exercise Plan</h2>
          {!editing && <p>{items.length
              ? `${items.length} exercise${items.length === 1 ? '' : 's'}`
              : 'No exercise plan yet.'}</p>}
        </div>
        {headerActions}
      </div>

      {!editing && !items.length && (
        canEdit ? (
          <button type="button" className="exercise-plan-empty" aria-label="Select to start new plan" onClick={startPlan}>
            <span className="exercise-plan-plus" aria-hidden="true">+</span>
            <strong>Select to start new plan</strong>
          </button>
        ) : (
          <div className="exercise-plan-empty"><strong>No exercise plan yet</strong></div>
        )
      )}

      {!editing && items.length > 0 && (
        <div className="exercise-display-list" aria-label="Exercise plan">
          {items.map(item => (
            <article className="exercise-display-row" key={item.id}>
              <div className="exercise-display-title">
                <strong>{item.name}</strong>
                {canEdit ? (
                  <button
                    type="button"
                    className={`exercise-display-camera ${item.videoAttached ? 'attached' : ''}`}
                    aria-label={`Manage video for ${item.name}`}
                    onClick={() => setVideoExercise(item)}
                  >
                    <CameraIcon />
                  </button>
                ) : (
                  <span className={`exercise-display-camera ${item.videoAttached ? 'attached' : ''}`} aria-label={item.videoAttached ? 'Video added' : 'No video'}>
                    <CameraIcon />
                  </span>
                )}
              </div>
              <dl>
                <div><dt>Weight</dt><dd>{item.weight || '—'}</dd></div>
                <div><dt>Reps</dt><dd>{item.reps || '—'}</dd></div>
                <div><dt>Rounds</dt><dd>{item.rounds || '—'}</dd></div>
                <div><dt>Rest</dt><dd>{item.rest || '—'}</dd></div>
                {(item.customDetails ?? []).map((detail, index) => (
                  <div key={detail.id ?? `${item.id}-detail-${index}`}>
                    <dt>Details {index + 1}</dt>
                    <dd>{typeof detail === 'string' ? detail : detail.value || '—'}</dd>
                  </div>
                ))}
              </dl>
            </article>
          ))}
        </div>
      )}

      {editing && (
        <div className="exercise-editor">
          <div className="exercise-editor-list">
            {draft.map((item, index) => (
                <article className={`exercise-editor-row ${pendingId === item.id ? 'pending' : ''}`} key={item.id}>
                  <div className="exercise-editor-head">
                    <button type="button" className="muted-action text-action" onClick={() => remove(item.id)}>
                      {pendingId === item.id ? 'Cancel' : 'Remove'}
                    </button>
                  </div>

                  <ExerciseNamePicker
                    index={index + 1}
                    choice={item.exerciseChoice}
                    name={item.name}
                    pending={!item.name.trim()}
                    onChoose={choice => chooseExercise(item.id, choice)}
                    onCustomName={value => update(item.id, 'name', value)}
                  />

                  <div className="exercise-field-grid">
                    {FIELDS.map(([field, label, placeholder]) => (
                      <label key={field}>
                        {label}
                        <input
                          aria-label={`Exercise ${index + 1} ${label.toLowerCase()}`}
                          value={item[field]}
                          onChange={event => update(item.id, field, event.target.value)}
                          placeholder={placeholder}
                        />
                      </label>
                    ))}
                    {item.customDetails.map((detail, detailIndex) => (
                      <label className="exercise-custom-detail-field" key={detail.id}>
                        <span>
                          Details {detailIndex + 1}
                          <button type="button" aria-label={`Remove detail ${detailIndex + 1} from exercise ${index + 1}`} onClick={() => removeDetail(item.id, detail.id)}>×</button>
                        </span>
                        <input
                          aria-label={`Exercise ${index + 1} details ${detailIndex + 1}`}
                          value={detail.value}
                          onChange={event => updateDetail(item.id, detail.id, event.target.value)}
                          placeholder="Enter exercise details"
                        />
                      </label>
                    ))}
                    <button type="button" className="exercise-add-detail-field" aria-label={`Add details for exercise ${index + 1}`} onClick={() => addDetail(item.id)}>
                      <span aria-hidden="true">+</span>
                      Details
                    </button>
                  </div>
                </article>
              ))}
          </div>
          {error && <p className="validation-copy" role="alert">{error}</p>}
        </div>
      )}

      <ExerciseVideoDialog
        open={Boolean(videoExercise)}
        sessionId={sessionId}
        exercise={videoExercise}
        onCancel={() => setVideoExercise(null)}
        onSaved={video => onToggleVideo(videoExercise.id, true, video)}
        onRemoved={() => onToggleVideo(videoExercise.id, false, null)}
      />
    </>
  )
}
