import { DEFAULT_PACKAGES, WEEKLY_FREQUENCIES, weeklyFrequencyLabel, freeGymEligible } from '../../app/packages.js'
import { useEffect, useMemo, useRef, useState } from 'react'
import Panel from '../../components/Panel.jsx'
import OnboardingReview from '../../components/OnboardingReview.jsx'
import { ONBOARDING_REVIEW_STEP, clientReviewSections, firstIncompleteSection } from '../../app/onboardingReview.js'
import Field from '../../components/OnboardingField.jsx'
import ClientPersonFields from './ClientPersonFields.jsx'
import AvailabilityEditor from '../../components/AvailabilityEditor.jsx'
import { availabilityBlockError } from '../../app/availability.js'
import { useActionConfirmation } from '../../components/ActionConfirmationProvider.jsx'
import { useEditGuard } from '../../components/EditGuardProvider.jsx'
import {
  CLIENT_ONBOARDING_STEPS,
  DAYS,
  DEFAULT_AVAILABILITY_FROM,
  DEFAULT_AVAILABILITY_TO,
  GENDER_PREFERENCES,
  buildFixedWeeklySchedule,
  clientStepErrors,
  defaultMatchingTrainer,
  matchTrainers,
} from '../../app/clientOnboarding.js'

const emptyPerson = () => ({
  name: '',
  phone: { countryCode: '+65', number: '' },
  email: '',
  birthday: '',
  gender: '',
  emergencyContact: { name: '', relationship: 'Spouse', countryCode: '+65', number: '' },
  healthNotes: '',
})

const emptyDraft = () => ({
  type: 'Individual',
  people: [emptyPerson(), emptyPerson()],
  sessionsPerWeek: 1,
  startDate: '',
  genderPreference: 'No gender preference',
  remarks: '',
  clientPreferences: [],
  trainerId: '',
})

const FORM_STEPS = [...CLIENT_ONBOARDING_STEPS, ONBOARDING_REVIEW_STEP]

export default function AddClientPage({ packages = DEFAULT_PACKAGES, trainers, onCancel, onCreate, onCreated }) {
  const confirmAction = useActionConfirmation()
  const { activeEdit, setActiveEdit } = useEditGuard()
  const [initialDraft] = useState(() => ({ ...emptyDraft(), packageId: packages[0]?.id ?? '' }))
  const [draft, setDraft] = useState(initialDraft)
  const [stepIndex, setStepIndex] = useState(0)
  const [returningToReview, setReturningToReview] = useState(false)
  const [activePerson, setActivePerson] = useState(0)
  const [selectedDays, setSelectedDays] = useState([])
  const [from, setFrom] = useState(DEFAULT_AVAILABILITY_FROM)
  const [to, setTo] = useState(DEFAULT_AVAILABILITY_TO)
  const [errors, setErrors] = useState({})
  const [saving, setSaving] = useState(false)
  const [created, setCreated] = useState(null)
  const submissionPending = useRef(false)
  const navigationCompleted = useRef(false)
  const stepHeading = useRef(null)
  const previousStepIndex = useRef(0)
  const formRef = useRef(null)
  const nextBlockId = useRef(1)

  const validateStep = (value, key) => ({ ...clientStepErrors(value, key),
    ...(key === 'package' && !packages.some(item => item.id === value.packageId) ? { packageId: 'Choose an active PT package.' } : {}) })
  const step = FORM_STEPS[stepIndex]
  const reviewing = step.key === 'review'
  const previousStep = FORM_STEPS[stepIndex - 1]
  const nextStep = FORM_STEPS[stepIndex + 1]
  const dirty = JSON.stringify(draft) !== JSON.stringify(initialDraft) || selectedDays.length > 0 || from !== DEFAULT_AVAILABILITY_FROM || to !== DEFAULT_AVAILABILITY_TO

  useEffect(() => {
    setActiveEdit(dirty && !created ? 'New client' : null)
    return () => setActiveEdit(null)
  }, [created, dirty, setActiveEdit])

  // Navigation occurs on the render after the edit guard has been released,
  // not through a stale App callback captured before the asynchronous save.
  useEffect(() => {
    if (!created || activeEdit || navigationCompleted.current) return
    navigationCompleted.current = true
    onCreated(created.id)
  }, [activeEdit, created, onCreated])

  useEffect(() => {
    if (previousStepIndex.current === stepIndex) return
    previousStepIndex.current = stepIndex
    stepHeading.current?.focus({ preventScroll: true })
    stepHeading.current?.scrollIntoView({ block: 'start' })
  }, [stepIndex])

  useEffect(() => {
    if (!Object.keys(errors).length) return
    formRef.current?.querySelector('[aria-invalid="true"]')?.focus()
  }, [activePerson, errors])

  const visibleMatches = useMemo(
    () => matchTrainers(trainers, draft.clientPreferences, draft.genderPreference),
    [trainers, draft.clientPreferences, draft.genderPreference],
  )
  const selectedTrainer = visibleMatches.find(result => result.trainer.id === draft.trainerId)?.trainer ?? null
  const fixedWeeklySchedule = useMemo(
    () => selectedTrainer ? buildFixedWeeklySchedule(selectedTrainer, draft.clientPreferences, draft.sessionsPerWeek) : [],
    [draft.clientPreferences, draft.sessionsPerWeek, selectedTrainer],
  )
  const selectedPack = packages.find(item => item.id === draft.packageId)
  const completeDraft = { ...draft, packageVersion: selectedPack?.version, packageName: selectedPack?.name, packageDefinition: selectedPack, trainerId: selectedTrainer?.id ?? '', fixedWeeklySchedule }

  const update = (patch, invalidateMatching = false) => {
    setDraft(current => ({ ...current, ...patch, ...(invalidateMatching ? { trainerId: '' } : {}) }))
    setErrors({})
  }

  const updatePerson = nextPerson => {
    update({ people: draft.people.map((person, index) => index === activePerson ? nextPerson : person) })
  }

  const goToStep = index => {
    if (FORM_STEPS[index].key === 'matching') {
      setDraft(current => ({ ...current, trainerId: defaultMatchingTrainer(
        visibleMatches, current.clientPreferences, current.sessionsPerWeek, current.trainerId,
      ) }))
    }
    setErrors({})
    setStepIndex(index)
  }

  const addPreference = () => {
    const days = DAYS.filter(day => selectedDays.includes(day))
    const error = availabilityBlockError({ days, from, to }, draft.clientPreferences)
    if (error) {
      setErrors({ availability: error })
      return
    }
    update({ clientPreferences: [...draft.clientPreferences, { id: `client-preference-${nextBlockId.current++}`, days, from, to }] }, true)
    setSelectedDays([])
  }

  const resetAvailability = () => {
    setSelectedDays([])
    setFrom(DEFAULT_AVAILABILITY_FROM)
    setTo(DEFAULT_AVAILABILITY_TO)
    update({ clientPreferences: [] }, true)
  }

  const handleSubmit = async event => {
    event.preventDefault()
    if (submissionPending.current || saving || created) return
    const validation = validateStep(completeDraft, step.key)
    if (step.key === 'availability' && selectedDays.length) {
      validation.availability = 'Select Add Time to include these days before continuing.'
    }
    if (Object.keys(validation).length) {
      setErrors(validation)
      const personError = Object.keys(validation).find(key => key.startsWith('people.'))
      if (personError) setActivePerson(Number(personError.split('.')[1]))
      return
    }
    if (!returningToReview && nextStep && nextStep.key !== 'review') {
      goToStep(stepIndex + 1)
      return
    }
    const invalid = firstIncompleteSection(completeDraft, CLIENT_ONBOARDING_STEPS, validateStep, selectedDays.length > 0)
    if (invalid) {
      goToStep(invalid.index)
      setErrors(invalid.errors)
      const personError = Object.keys(invalid.errors).find(key => key.startsWith('people.'))
      if (personError) setActivePerson(Number(personError.split('.')[1]))
      return
    }
    if (!reviewing) {
      setReturningToReview(false)
      goToStep(CLIENT_ONBOARDING_STEPS.length)
      return
    }

    submissionPending.current = true
    try {
      const displayName = (draft.type === 'Couple' ? draft.people : draft.people.slice(0, 1)).map(person => person.name.trim()).join(' & ')
      const confirmed = await confirmAction({
        title: `Create ${displayName}?`,
        message: `${selectedTrainer.name} will be assigned. ${selectedPack.total} sessions will be created with ${selectedPack.validityDays}-day validity. ${freeGymEligible(draft.sessionsPerWeek) ? 'Free gym package included.' : ''}`,
        confirmLabel: 'Create Client',
      })
      if (!confirmed) return
      setSaving(true)
      const result = await onCreate(completeDraft)
      setCreated(result)
    } catch (error) {
      setSaving(false)
      setErrors({ save: error instanceof Error ? error.message : 'Client creation failed. Please try again.' })
    } finally {
      submissionPending.current = false
    }
  }

  const editReviewSection = key => {
    const index = CLIENT_ONBOARDING_STEPS.findIndex(item => item.key === key)
    if (index < 0 || saving || submissionPending.current) return
    setReturningToReview(true)
    if (key === 'general') setActivePerson(0)
    goToStep(index)
  }

  const personLabel = draft.type === 'Couple' ? `Client ${activePerson + 1}` : 'Client'

  return (
    <div className={`client-onboarding${dirty ? ' editing-section' : ''}`}>
      <div className="page-head compact-page-head">
        <div><span className="eyebrow">Operations</span><h1>Add New Client</h1></div>
        <button type="button" className="onboarding-button" disabled={saving} onClick={onCancel}>Cancel</button>
      </div>
      <form ref={formRef} noValidate onSubmit={handleSubmit} aria-label="Client creation">
        <Panel>
          <div className="section-head onboarding-step-head">
            <h2 ref={stepHeading} tabIndex={-1}>{step.title}</h2>
            <span className="onboarding-step-count" aria-label="Creation progress">Step {stepIndex + 1} of {FORM_STEPS.length}</span>
          </div>
          <fieldset className="onboarding-step-body" disabled={saving}>
            <legend className="visually-hidden">{step.title}</legend>

            {step.key === 'general' && (
              <div className="onboarding-general-fields">
                <Field label="Client type" required error={errors.type}>
                  <select aria-label="Client type" value={draft.type} onChange={event => { update({ type: event.target.value }); setActivePerson(0) }}>
                    <option value="Individual">Single</option><option value="Couple">Couple</option>
                  </select>
                </Field>
                {draft.type === 'Couple' && (
                  <div className="onboarding-person-tabs" role="group" aria-label="Couple client tabs">
                    {[0, 1].map(index => (
                      <button key={index} type="button" className={activePerson === index ? 'active' : ''} aria-pressed={activePerson === index} onClick={() => setActivePerson(index)}>
                        Client {index + 1}
                      </button>
                    ))}
                  </div>
                )}
                <ClientPersonFields person={draft.people[activePerson]} labelPrefix={personLabel} nameError={errors[`people.${activePerson}.name`]} onChange={updatePerson} />
                <Field label="Remarks"><textarea aria-label="Remarks" value={draft.remarks} onChange={event => update({ remarks: event.target.value })} /></Field>
              </div>
            )}

            {step.key === 'package' && (
              <div className="onboarding-grid">
                <div className="onboarding-package-fields">
                  <Field label="PT Package" required error={errors.packageId}><select aria-label="PT Package" value={draft.packageId} onChange={event => {
                    const item = packages.find(item => item.id === event.target.value)
                    if (item) update({ packageId: item.id }, true)
                  }}><option value="" disabled>Choose package</option>{packages.map(item => <option value={item.id} key={item.id}>{item.name} · {item.validityDays} days</option>)}</select></Field>
                  <Field label="Start date" required error={errors.startDate}>
                    <input aria-label="Start date" type="date" value={draft.startDate} onChange={event => update({ startDate: event.target.value })} />
                  </Field>
                  <Field label="Weekly frequency" required error={errors.sessionsPerWeek}>
                    <select aria-label="Weekly frequency" value={draft.sessionsPerWeek} onChange={event => {
                      update({ sessionsPerWeek: Number(event.target.value) }, true)
                    }}>
                      {WEEKLY_FREQUENCIES.map(frequency => <option key={frequency} value={frequency}>{weeklyFrequencyLabel(frequency)}</option>)}
                    </select>
                  </Field>
                  <Field label="Gym membership">
                    <input aria-label="Gym membership" readOnly value={freeGymEligible(draft.sessionsPerWeek) ? 'Included' : 'Not included'} />
                  </Field>
                </div>
                <Field label="Trainer preference">
                  <select aria-label="Trainer preference" value={draft.genderPreference} onChange={event => update({ genderPreference: event.target.value }, true)}>
                    {GENDER_PREFERENCES.map(preference => <option key={preference}>{preference}</option>)}
                  </select>
                </Field>
              </div>
            )}

            {step.key === 'availability' && (
              <AvailabilityEditor blocks={draft.clientPreferences} selectedDays={selectedDays}
                from={from} to={to} error={errors.availability} listLabel="Client availability blocks"
                onToggleDay={day => { setSelectedDays(current => current.includes(day) ? current.filter(value => value !== day) : [...current, day]); setErrors({}) }}
                onFrom={value => { setFrom(value); setErrors({}) }}
                onTo={value => { setTo(value); setErrors({}) }}
                onAdd={addPreference}
                onRemove={id => update({ clientPreferences: draft.clientPreferences.filter(block => block.id !== id) }, true)}
                onReset={resetAvailability}
              />
            )}

            {step.key === 'matching' && (
              <div className="onboarding-matching">
                <Field label="Matched trainer" required error={errors.trainerId}>
                  <select aria-label="Matched trainer" value={selectedTrainer?.id ?? ''}
                    disabled={!visibleMatches.length} onChange={event => update({ trainerId: event.target.value })}>
                    <option value="">{visibleMatches.length ? 'Choose a trainer' : 'No matching trainers'}</option>
                    {visibleMatches.map(result => <option key={result.trainer.id} value={result.trainer.id}>{result.trainer.name}</option>)}
                  </select>
                </Field>
                {!visibleMatches.length && <p className="onboarding-hint" role="status">No active trainer matches these days and times. Go back to adjust the availability or preference.</p>}
                {visibleMatches.length > 0 && (
                  <>
                    <div className="onboarding-schedule-preview" aria-label="Fixed Weekly Schedule">
                      <strong>Fixed Weekly Schedule</strong>
                      {fixedWeeklySchedule.map(slot => <div key={slot.id}><span>{slot.day}</span><b>{slot.from}–{slot.to}</b></div>)}
                      {fixedWeeklySchedule.length < draft.sessionsPerWeek && <p className="onboarding-hint">This trainer needs {draft.sessionsPerWeek} matching weekly {draft.sessionsPerWeek === 1 ? 'day' : 'days'}. Choose another trainer or adjust availability.</p>}
                    </div>
                    <p className="onboarding-hint">{selectedPack?.total} sessions · {selectedPack?.validityDays}-day validity</p>
                  </>
                )}
              </div>
            )}
            {reviewing && <OnboardingReview sections={clientReviewSections(completeDraft, selectedTrainer)} onEdit={editReviewSection} />}
          </fieldset>
          {Object.keys(errors).length > 0 && <p className="onboarding-error" role="alert">{Object.values(errors)[0]}</p>}
          <div className="onboarding-step-actions">
            {!returningToReview && previousStep && <button type="button" className="onboarding-button" disabled={saving} onClick={() => goToStep(stepIndex - 1)}>Back to {previousStep.title}</button>}
            <button type="submit" className="onboarding-button primary" disabled={saving}>
              {saving ? 'Creating…' : reviewing ? 'Create Client' : returningToReview ? 'Return to Review & Confirm' : `Continue to ${nextStep.title}`}
            </button>
          </div>
        </Panel>
      </form>
    </div>
  )
}
