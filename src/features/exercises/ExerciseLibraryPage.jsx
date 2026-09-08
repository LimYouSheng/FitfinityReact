import { useEffect, useMemo, useRef, useState } from 'react'
import Panel from '../../components/Panel.jsx'
import StatusBadge from '../../components/StatusBadge.jsx'
import PaginationControls from '../../components/PaginationControls.jsx'
import usePagination from '../../hooks/usePagination.js'
import { useActionConfirmation } from '../../components/ActionConfirmationProvider.jsx'
import { useEditGuard } from '../../components/EditGuardProvider.jsx'
import { EXERCISE_MEDIA_TYPES, exerciseDraftErrors, exerciseMediaError, filterExerciseCatalog } from '../../app/exerciseCatalog.js'
import ExerciseLibraryMedia from './ExerciseLibraryMedia.jsx'

const EXERCISE_EDIT_LABEL = 'Exercise library entry'
const draftFor = (exercise, categories) => ({ name: exercise?.name ?? '', category: exercise?.category ?? categories[0] ?? '', description: exercise?.description ?? '', status: exercise?.status ?? 'active' })
const mediaLabel = media => media ? media.type.startsWith('image/') ? 'Photo' : 'Video' : '—'

function ExerciseDetail({ exercise, exercises, categories, creating, onLoadMedia, onSave, onNavigate }) {
  const confirm = useActionConfirmation()
  const { activeEdit, setActiveEdit } = useEditGuard()
  const [editing, setEditing] = useState(creating)
  const [draft, setDraft] = useState(() => draftFor(exercise, categories))
  const [file, setFile] = useState(null)
  const [mediaError, setMediaError] = useState('')
  const [removeMedia, setRemoveMedia] = useState(false)
  const [errors, setErrors] = useState({})
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [created, setCreated] = useState(null)
  const pending = useRef(false), navigated = useRef(false), fileInput = useRef(null)
  const dirty = JSON.stringify(draft) !== JSON.stringify(draftFor(exercise, categories)) || Boolean(file) || removeMedia
  useEffect(() => {
    setActiveEdit(editing && dirty ? EXERCISE_EDIT_LABEL : null)
    return () => setActiveEdit(null)
  }, [dirty, editing, setActiveEdit])
  useEffect(() => {
    if (!editing) setDraft(draftFor(exercise, categories))
  }, [categories, editing, exercise])
  useEffect(() => {
    if (!created || activeEdit || navigated.current) return
    navigated.current = true
    onNavigate(`exercises/${created.id}`, { replace: true })
  }, [activeEdit, created, onNavigate])
  const patch = update => { setDraft(current => ({ ...current, ...update })); setErrors({}); setError('') }

  const persist = async (nextDraft, statusOnly = false) => {
    if (pending.current) return
    const validation = exerciseDraftErrors(nextDraft, exercises, exercise?.id, categories)
    setErrors(validation)
    if (Object.keys(validation).length || (!statusOnly && mediaError)) return
    pending.current = true; setBusy(true); setError('')
    try {
      const action = statusOnly ? nextDraft.status === 'active' ? 'Reactivate Exercise' : 'Deactivate Exercise' : creating ? 'Create Exercise' : 'Save Exercise'
      if (!await confirm({ title: `${action}?`, confirmLabel: action,
        message: `${nextDraft.name.trim()} · ${nextDraft.category}. ${statusOnly && nextDraft.status === 'inactive' ? 'This removes the exercise from new session selections. Saved plans keep their existing details.' : 'Save this library entry and create a related Message.'}` })) return
      const saved = await onSave({ id: exercise?.id, expectedVersion: exercise?.version, draft: nextDraft,
        mediaFile: statusOnly ? null : file, removeMedia: statusOnly ? false : removeMedia })
      setEditing(false); setFile(null); setMediaError(''); setRemoveMedia(false); setActiveEdit(null)
      if (creating) setCreated(saved)
    } catch (failure) { setError(failure.message || 'Could not save the exercise. Try again.') }
    finally { pending.current = false; setBusy(false) }
  }

  if (creating && created) return <Panel><p role="status">Opening exercise…</p></Panel>
  if (!editing) return <Panel>
    <div className="section-head"><div><h2>{exercise?.name ?? created?.name}</h2><StatusBadge tone={exercise?.status === 'inactive' ? 'neutral' : 'green'}>{exercise?.status === 'inactive' ? 'Inactive' : 'Active'}</StatusBadge></div>
      <button type="button" className="text-action" disabled={busy} onClick={() => { setEditing(true); setDraft(draftFor(exercise, categories)) }}>Edit Exercise</button>
    </div>
    <dl className="library-summary"><div><dt>Category</dt><dd>{exercise?.category}</dd></div><div><dt>Description</dt><dd>{exercise?.description || '—'}</dd></div><div><dt>Photo / video</dt><dd>{exercise?.media?.name || 'No attachment'}</dd></div></dl>
    <ExerciseLibraryMedia onLoad={onLoadMedia} media={exercise?.media} />
    {error && <p className="validation-copy" role="alert">{error}</p>}
    {exercise && <div className="library-lifecycle"><button className="secondary-button" type="button" disabled={busy} onClick={() => persist({ ...draftFor(exercise, categories), status: exercise.status === 'active' ? 'inactive' : 'active' }, true)}>{exercise.status === 'active' ? 'Deactivate Exercise' : 'Reactivate Exercise'}</button></div>}
  </Panel>

  return <Panel>
    <form className="library-form" noValidate onSubmit={event => { event.preventDefault(); persist(draft) }}>
      <fieldset disabled={busy}>
        <div className={`library-field is-required ${errors.name ? 'is-invalid' : ''}`}><label htmlFor="library-name">Exercise name <span aria-hidden="true">*</span></label><input id="library-name" required maxLength={180} value={draft.name} aria-invalid={Boolean(errors.name)} aria-describedby={errors.name ? 'library-name-error' : undefined} onChange={event => patch({ name: event.target.value })} />{errors.name && <small id="library-name-error">{errors.name}</small>}</div>
        <div className={`library-field is-required ${errors.category ? 'is-invalid' : ''}`}><label htmlFor="library-category">Category <span aria-hidden="true">*</span></label><select id="library-category" required value={draft.category} aria-invalid={Boolean(errors.category)} onChange={event => patch({ category: event.target.value })}>{categories.map(category => <option key={category}>{category}</option>)}</select>{errors.category && <small>{errors.category}</small>}</div>
        <div className="library-field"><label htmlFor="library-description">Description</label><textarea id="library-description" rows={3} maxLength={2000} value={draft.description} onChange={event => patch({ description: event.target.value })} />{errors.description && <small>{errors.description}</small>}</div>
        <div className="library-field"><label htmlFor="library-file">Photo / video</label><input id="library-file" ref={fileInput} type="file" accept={EXERCISE_MEDIA_TYPES.join(',')} onChange={event => {
          const selected = event.target.files?.[0]
          if (!selected) return
          const invalid = exerciseMediaError(selected)
          if (invalid) { setMediaError(invalid); event.target.value = ''; return }
          setFile(selected); setRemoveMedia(false); setMediaError('')
        }} /><small>JPG, PNG, WebP, MP4, WebM or MOV · up to 50 MB.</small>
          {mediaError && <small className="validation-copy" role="alert">{mediaError}</small>}
          {(file || mediaError || (!removeMedia && exercise?.media)) && <div className="library-attachment"><span>{file?.name || (!removeMedia && exercise?.media?.name)}</span><button type="button" className="secondary-button" onClick={() => { setFile(null); setMediaError(''); setRemoveMedia(Boolean(exercise?.media)); if (fileInput.current) fileInput.current.value = '' }}>Remove Attachment</button></div>}
        </div>
        <ExerciseLibraryMedia onLoad={onLoadMedia} file={file} media={removeMedia ? null : exercise?.media} />
        <div className="library-form-actions"><button className="secondary-button" type="button" onClick={() => {
          if (creating) onNavigate('exercises')
          else { setEditing(false); setFile(null); setMediaError(''); setRemoveMedia(false); setErrors({}); setError('') }
        }}>Cancel</button><button className="primary-button" type="submit" disabled={!creating && !dirty}>{busy ? 'Saving…' : creating ? 'Create Exercise' : 'Save Exercise'}</button></div>
      </fieldset>
      {error && <p className="validation-copy" role="alert">{error}</p>}
    </form>
  </Panel>
}

function OwnerExerciseLibrary({ exercises, categories, detailId, onNavigate, onBack, onLoadMedia, onSave }) {
  const { activeEdit } = useEditGuard()
  const [query, setQuery] = useState(''), [category, setCategory] = useState(''), [status, setStatus] = useState('active')
  const visible = useMemo(() => filterExerciseCatalog(exercises, { query, category, status }), [category, exercises, query, status])
  const pagination = usePagination(visible, `${query}|${category}|${status}`)
  const creating = detailId === 'new'
  const selected = exercises.find(item => item.id === detailId)
  return <div className={`exercise-library-page${activeEdit === EXERCISE_EDIT_LABEL ? ' editing-section' : ''}`}>
    <div className="page-head"><div><span className="eyebrow">Operations</span><h1>{creating ? 'Add Exercise' : 'Exercise Library'}</h1></div>{detailId
      ? <button type="button" className="secondary-button" onClick={onBack}>Back to Exercise Library</button>
      : <button type="button" className="primary-button" onClick={() => onNavigate('exercises/new')}>Add Exercise</button>}</div>
    {detailId ? creating || selected ? <ExerciseDetail key={detailId} exercise={selected} exercises={exercises} categories={categories} creating={creating} onLoadMedia={onLoadMedia} onSave={onSave} onNavigate={onNavigate} /> : <Panel><p>Exercise not found.</p></Panel>
      : <Panel>
        <div className="library-filters"><input type="search" aria-label="Search exercises" placeholder="Search exercises" value={query} onChange={event => setQuery(event.target.value)} /><select aria-label="Exercise category" value={category} onChange={event => setCategory(event.target.value)}><option value="">All categories</option>{categories.map(item => <option key={item}>{item}</option>)}</select><select aria-label="Exercise status" value={status} onChange={event => setStatus(event.target.value)}><option value="active">Active</option><option value="inactive">Inactive</option><option value="">All statuses</option></select></div>
        <p className="library-count">{visible.length} exercises</p>
        <div className="library-table" role="table" aria-label="Exercise library">
          <div className="library-grid library-table-head" role="row"><span role="columnheader">Exercise</span><span role="columnheader">Category</span><span className="library-media-cell" role="columnheader">Media</span><span role="columnheader">Status</span><span role="columnheader">View</span></div>
          {pagination.items.map(exercise => <div className="library-grid library-row" role="row" key={exercise.id}><strong role="cell">{exercise.name}</strong><span role="cell">{exercise.category}</span><span className="library-media-cell" role="cell">{mediaLabel(exercise.media)}</span><span role="cell"><StatusBadge tone={exercise.status === 'active' ? 'green' : 'neutral'}>{exercise.status === 'active' ? 'Active' : 'Inactive'}</StatusBadge></span><span role="cell"><button type="button" className="secondary-button" aria-label={`View exercise ${exercise.name}`} onClick={() => onNavigate(`exercises/${exercise.id}`)}>View</button></span></div>)}
        </div>
        {!visible.length && <p className="empty">No exercises match your filters.</p>}
        <PaginationControls {...pagination} onPage={pagination.setPage} />
      </Panel>}
  </div>
}
export default function ExerciseLibraryPage(props) {
  if (props.user.role !== 'owner') return <Panel><h1>Exercise Library</h1><p>Exercise library management is available to the owner.</p></Panel>
  return <OwnerExerciseLibrary {...props} />
}
