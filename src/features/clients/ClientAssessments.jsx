import { memo, useCallback, useRef, useState } from 'react'
import ConfirmDialog from '../../components/ConfirmDialog.jsx'
import { useActionConfirmation } from '../../components/ActionConfirmationProvider.jsx'
import { businessClock } from '../../app/clock.js'
import paperLayouts from '../../app/assessmentPaperLayouts.json'
import useSwipeBack from '../../hooks/useSwipeBack.js'
import { ASSESSMENT_FORMS, assessmentErrors, assessmentFields, saveAssessment } from '../../app/assessmentForms.js'

const HEADER_FIELDS = { $name: { label: 'Client name' }, $birthday: { label: 'Date of birth' }, $date: { label: 'Assessment date' } }
const FORM_FIELDS = Object.fromEntries(ASSESSMENT_FORMS.map(form => [form.id,
  Object.fromEntries(assessmentFields(form).map(field => [field.id, field]))]))

// The page artwork uses the PDF's exact geometry. Controls occupy its original answer spaces.
const PaperField = memo(function PaperField({ placement, page, field, value, onChange, readOnly, error }) {
  const [x, y, width, height] = placement.rect
  const style = { left: `${x / page.width * 100}%`, top: `${y / page.height * 100}%`,
    width: `${width / page.width * 100}%`, height: `${height / page.height * 100}%` }
  const label = placement.kind === 'check' && field.type !== 'checkbox' ? `${field.label} — ${placement.value}` : field.label
  const props = { 'aria-label': label, 'aria-invalid': error ? 'true' : undefined, title: error || label }
  let control
  if (placement.kind === 'check') {
    control = readOnly ? <span {...props}>{value === placement.value ? '✓' : ''}</span>
      : <input {...props} type="checkbox" checked={value === placement.value}
        onChange={event => onChange(field.id, event.target.checked ? placement.value : '')} />
  } else if (readOnly) control = <span {...props} tabIndex={value !== undefined && value !== '' ? 0 : undefined}>{value ?? ''}</span>
  else {
    const input = { ...props, value: value ?? '', onChange: event => onChange(field.id, event.target.value) }
    control = ['area', 'cell'].includes(placement.kind) ? <textarea {...input} />
        : <input {...input} type={field.type === 'number' ? 'number' : 'text'} min={field.min} max={field.max}
          step={field.type === 'number' ? 'any' : undefined} />
  }
  return <div className={`assessment-paper-field is-${placement.kind}${HEADER_FIELDS[placement.id] ? ' is-metadata' : ''}`} style={style}>{control}</div>
})

function AssessmentPaper({ definition, person, draft, errors, onChange, readOnly }) {
  const [failedPages, setFailedPages] = useState([])
  const fields = FORM_FIELDS[definition.id]
  const pages = paperLayouts[definition.id]
  const headerValues = { $name: person.name, $birthday: person.birthday, $date: draft.date }
  return <div className="assessment-paper-pages">
    <p className="onboarding-hint">{readOnly ? 'Saved answers are shown below.' : 'Fill the highlighted answer spaces.'} On a smaller screen, scroll sideways inside the page.</p>
    {!readOnly && definition.id === 'health_history' && <p className="onboarding-hint">Record weight in kg and circumferences in cm. Select an answer once; select it again to clear it.</p>}
    {pages.map((page, index) => <section key={page.asset} aria-label={`${definition.paperTitle} — page ${index + 1}`}>
      <p className="assessment-page-number">Page {index + 1} of {pages.length}</p>
      {failedPages.includes(index) && <p role="alert" className="onboarding-error">This page could not load. Reopen the form or use Open original PDF to check its questions.</p>}
      <div className="assessment-paper-scroll" data-no-swipe role="region" aria-label={`Paper page ${index + 1}`} tabIndex={0}>
        <div className="assessment-paper-page" style={{ aspectRatio: `${page.width} / ${page.height}` }}>
          <img className="assessment-paper-art" src={`${import.meta.env.BASE_URL}assessment-forms/pages/${page.asset}`} alt=""
            width={page.width} height={page.height} decoding="async" loading={index === 0 ? 'eager' : 'lazy'}
            onError={() => setFailedPages(current => current.includes(index) ? current : [...current, index])} />
          <p className="visually-hidden">{page.text}</p>
          {page.fields.map(placement => {
            const metadata = HEADER_FIELDS[placement.id]
            const field = metadata ?? fields[placement.id]
            return <PaperField key={`${placement.id}-${placement.value ?? ''}`} placement={placement} page={page} field={field}
              value={metadata ? headerValues[placement.id] : draft.answers[field.id]} error={errors[placement.id === '$date' ? 'date' : field.id]}
              readOnly={readOnly || Boolean(metadata)}
              onChange={onChange} />
          })}
        </div>
      </div>
    </section>)}
  </div>
}

export function AssessmentDialog({ definition, person, record, onSave, onClose, readOnly, assessor, timeZone }) {
  const confirmAction = useActionConfirmation()
  const [initial] = useState(() => record ?? { date: businessClock(new Date(), timeZone).date, assessor: assessor ?? '', answers: {} })
  const [draft, setDraft] = useState(initial)
  const [errors, setErrors] = useState({})
  const [saving, setSaving] = useState(false)
  const pendingSave = useRef(false)
  const body = useRef(null)
  const closing = useRef(false)
  const dirty = JSON.stringify(initial) !== JSON.stringify(draft)
  const close = async () => {
    if (closing.current || pendingSave.current) return
    closing.current = true
    try {
      if (!readOnly && dirty && !await confirmAction({ title: 'Discard form changes?',
        message: 'The changes in this popup have not been saved. Your other forms will stay as they are.', confirmLabel: 'Discard Changes', danger: true })) return
      onClose()
    } finally { closing.current = false }
  }
  useSwipeBack({ enabled: true, onBack: close, surface: '.assessment-dialog', routeKey: definition.id })
  const save = () => {
    if (pendingSave.current) return
    const validation = assessmentErrors(definition.id, draft)
    setErrors(validation)
    if (Object.keys(validation).length) {
      // The alert remains visible even when the missing answer has no input.
      queueMicrotask(() => body.current?.querySelector('[aria-invalid="true"], [role="alert"]')?.focus())
      return
    }
    const failed = error => {
      pendingSave.current = false
      setSaving(false)
      setErrors({ save: error.message || 'The form could not be saved. Your answers are still here.' })
    }
    try {
      pendingSave.current = true
      const result = onSave(saveAssessment(definition.id, draft))
      if (result?.then) {
        setSaving(true)
        void result.then(onClose).catch(failed)
      } else onClose()
    } catch (error) { failed(error) }
  }
  const changeAnswer = useCallback((id, value) => {
    setDraft(current => ({ ...current, answers: { ...current.answers, [id]: value } }))
    setErrors(current => Object.keys(current).length ? {} : current)
  }, [])
  return <ConfirmDialog open title={definition.title} className="assessment-dialog" confirmLabel={saving ? 'Saving…' : 'Save'} confirmDisabled={saving}
    cancelLabel={readOnly ? 'Close' : 'Cancel'} hideConfirm={readOnly} onConfirm={save} onCancel={close}
    onKeyDown={event => { if (event.key === 'Escape' && !event.defaultPrevented) { event.preventDefault(); event.stopPropagation(); void close() } }}>
    <div ref={body} className="assessment-form">
      <div className="assessment-paper-heading"><div><h3 tabIndex={-1} data-modal-initial-focus>{definition.paperTitle}</h3><p className="assessment-person">{definition.subtitle}</p></div>
        <a className="secondary-button assessment-source" href={`${import.meta.env.BASE_URL}assessment-forms/${definition.source}`}
          target="_blank" rel="noopener noreferrer">Open original PDF <span className="visually-hidden">(opens in a new tab)</span></a>
      </div>
      {!readOnly && <p className="onboarding-hint">The original paper layout is shown below. Leave unassessed items blank. Save returns to the form list.</p>}
      {definition.id === 'hurdle_step' && <p className="onboarding-hint">The hurdle-step pages contain the protocol and reference findings. {!readOnly && 'Tick only findings you observe in this client. '}Printed examples are not saved as results.</p>}
      {Object.keys(errors).length > 0 && <p className="onboarding-error" role="alert" tabIndex={-1}>{Object.values(errors)[0]}</p>}
      <div className="assessment-metadata" role="group" aria-label="Form details">
        <p className="assessment-answer"><strong>Name</strong><span>{person.name}</span></p>
        <p className="assessment-answer"><strong>Date of birth</strong><span>{person.birthday || 'Not recorded'}</span></p>
        <p className="assessment-answer"><strong>Assessment date</strong><span>{draft.date}</span></p>
        <p className="assessment-answer"><strong>Assessor</strong><span>{draft.assessor || 'Not available'}</span></p>
      </div>
      <AssessmentPaper definition={definition} person={person} draft={draft} errors={errors} onChange={changeAnswer} readOnly={readOnly || saving} />
    </div>
  </ConfirmDialog>
}

/** One form grid and popup owner, shared by onboarding and saved profile viewing. */
export default function ClientAssessments({ people, activePerson, setActivePerson, onChange, readOnly = false,
  fillUnfilled = false, onSaveForm, onEditChange, disabled = false, assessor, timeZone }) {
  const [openForm, setOpenForm] = useState(null)
  const [announcement, setAnnouncement] = useState('')
  const person = people[activePerson] ?? people[0]
  const records = person.assessments ?? {}
  const count = ASSESSMENT_FORMS.filter(form => records[form.id]?.status === 'filled').length
  return <div className="client-assessments">
    {people.length > 1 && <div className="onboarding-person-tabs" role="group" aria-label="Assessment client tabs">
      {people.map((item, index) => <button key={index} type="button" aria-pressed={activePerson === index}
        className={activePerson === index ? 'active' : ''} onClick={() => { setActivePerson(index); setAnnouncement('') }}>Client {index + 1}</button>)}
    </div>}
    <div className="assessment-grid-heading"><strong>{person.name}</strong><span>{count} of {ASSESSMENT_FORMS.length} filled</span></div>
    <p className="onboarding-hint">{fillUnfilled ? 'Choose an unfilled form to complete it. Filled forms open for viewing.' : readOnly ? 'Open a filled form to view the saved answers.' : 'Choose a form to fill in. You can continue with unfilled forms.'} Green means the form has been saved.</p>
    {!readOnly && <p className="onboarding-hint">Forms stay in this draft until you select Create Client.</p>}
    <div className="assessment-grid" aria-label={`Assessment forms for ${person.name}`}>
      {ASSESSMENT_FORMS.map(definition => {
        const filled = records[definition.id]?.status === 'filled'
        return <button key={definition.id} type="button" className={`assessment-card${filled ? ' is-filled' : ''}`}
          aria-label={`${definition.title} — ${filled ? 'Filled' : 'Not filled'}`} disabled={disabled || (readOnly && !filled && !fillUnfilled)}
          onClick={event => {
            // Touch browsers do not necessarily focus a tapped button. Give the shared modal owner a reliable return target.
            event.currentTarget.focus({ preventScroll: true })
            if (fillUnfilled && !filled) onEditChange?.(true)
            setOpenForm(definition)
          }}>
          <strong>{definition.title}</strong><span className="assessment-card-description">{definition.subtitle}</span>
          <span className="assessment-status"><span aria-hidden="true">{filled ? '✓' : '○'}</span>{filled ? 'Filled' : 'Not filled'}</span>
        </button>
      })}
    </div>
    <span className="visually-hidden" role="status" aria-live="polite">{announcement}</span>
    {openForm && <AssessmentDialog key={`${activePerson}-${openForm.id}`} definition={openForm} person={person}
      record={records[openForm.id]} readOnly={readOnly && !(fillUnfilled && records[openForm.id]?.status !== 'filled')}
      assessor={assessor} timeZone={timeZone} onClose={() => { setOpenForm(null); onEditChange?.(false) }} onSave={record => {
        if (fillUnfilled) return onSaveForm(activePerson, openForm.id, record).then(() => {
          setAnnouncement(`${openForm.title} saved for ${person.name}.`)
        })
        onChange(people.map((item, index) => index === activePerson ? { ...item, assessments: { ...records, [openForm.id]: record } } : item))
        setAnnouncement(`${openForm.title} saved for ${person.name}.`)
      }} />}
  </div>
}
