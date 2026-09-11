import SelectField from '../../components/SelectField.jsx'
import ClientPackageFields from './ClientPackageFields.jsx'
import { freeGymEligible } from '../../app/packages.js'
import { useEffect, useMemo, useRef, useState } from 'react'
import Panel from '../../components/Panel.jsx'
import OnboardingReview from '../../components/OnboardingReview.jsx'
import { ONBOARDING_REVIEW_STEP, clientReviewSections, firstIncompleteSection } from '../../app/onboardingReview.js'
import Field from '../../components/OnboardingField.jsx'
import ClientGeneralFields from './ClientGeneralFields.jsx'
import AvailabilityEditor from '../../components/AvailabilityEditor.jsx'
import { availabilityBlockError } from '../../app/availability.js'
import { useActionConfirmation } from '../../components/ActionConfirmationProvider.jsx'
import { useEditGuard } from '../../components/EditGuardProvider.jsx'
import {
  CLIENT_ONBOARDING_STEPS,
  DAYS,
  buildFixedWeeklySchedule,
  clientStepErrors,
  defaultMatchingTrainer,
  matchTrainers,
} from '../../app/clientOnboarding.js'

const emptyPerson = policy => ({
  name: '',
  phone: { countryCode: policy.defaultCountryCode, number: '' },
  email: '',
  birthday: '',
  gender: '',
  emergencyContact: { name: '', relationship: policy.defaultRelationship, countryCode: policy.defaultCountryCode, number: '' },
  healthNotes: '',
})

const emptyDraft = policy => ({
  type: 'Individual',
  people: [emptyPerson(policy), emptyPerson(policy)],
  sessionsPerWeek: policy.weeklyFrequencies[0],
  startDate: '',
  genderPreference: 'No gender preference',
  remarks: '',
  clientPreferences: [],
  trainerId: '',
})

export default function ClientOnboardingForm({ packages, policy, trainers, onCancel, onCreate, onCreated, packageDraft }) {
  const addingPackage = Boolean(packageDraft)
  const steps = addingPackage ? CLIENT_ONBOARDING_STEPS.slice(1) : CLIENT_ONBOARDING_STEPS
  const formSteps = [...steps, ONBOARDING_REVIEW_STEP]
  const confirmAction = useActionConfirmation()
  const { activeEdit, setActiveEdit } = useEditGuard()
  const [initialDraft] = useState(() => ({ ...emptyDraft(policy), packageId: packages[0]?.id ?? '', ...packageDraft }))
  const [draft, setDraft] = useState(initialDraft)
  const [stepIndex, setStepIndex] = useState(0)
  const [returningToReview, setReturningToReview] = useState(false)
  const [activePerson, setActivePerson] = useState(0)
  const [selectedDays, setSelectedDays] = useState([])
  const [from, setFrom] = useState(policy.availability.from)
  const [to, setTo] = useState(policy.availability.to)
  const [errors, setErrors] = useState({})
  const [saving, setSaving] = useState(false)
  const [created, setCreated] = useState(null)
  const submissionPending = useRef(false)
  const navigationCompleted = useRef(false)
  const stepHeading = useRef(null)
  const previousStepIndex = useRef(0)
  const formRef = useRef(null)
  const nextBlockId = useRef(1 + initialDraft.clientPreferences.reduce((max, block) => Math.max(max, Number(block.id?.match(/^client-preference-(\d+)$/)?.[1] ?? 0)), 0))

  const validateStep = (value, key) => ({ ...clientStepErrors(value, key),
    ...(key === 'package' && !packages.some(item => item.id === value.packageId) ? { packageId: 'Choose an active PT package.' } : {}) })
  const step = formSteps[stepIndex]
  const reviewing = step.key === 'review'
  const previousStep = formSteps[stepIndex - 1]
  const nextStep = formSteps[stepIndex + 1]
  const dirty = JSON.stringify(draft) !== JSON.stringify(initialDraft) || selectedDays.length > 0 || from !== policy.availability.from || to !== policy.availability.to

  useEffect(() => {
    setActiveEdit(dirty && !created ? (addingPackage ? 'New package' : 'New client') : null)
    return () => setActiveEdit(null)
  }, [addingPackage, created, dirty, setActiveEdit])

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
    () => selectedTrainer ? (draft.fixedWeeklySchedule ?? buildFixedWeeklySchedule(selectedTrainer, draft.clientPreferences, draft.sessionsPerWeek)) : [],
    [draft.clientPreferences, draft.fixedWeeklySchedule, draft.sessionsPerWeek, selectedTrainer],
  )
  const selectedPack = packages.find(item => item.id === draft.packageId)
  const completeDraft = { ...draft, packageVersion: selectedPack?.version, packageName: selectedPack?.name, packageDefinition: selectedPack, trainerId: selectedTrainer?.id ?? '', fixedWeeklySchedule }

  const update = (patch, invalidateMatching = false) => {
    setDraft(current => ({ ...current, ...patch, ...(invalidateMatching ? { trainerId: '', fixedWeeklySchedule: undefined } : {}) }))
    setErrors({})
  }



  const goToStep = index => {
    if (formSteps[index].key === 'matching') {
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
    setFrom(policy.availability.from)
    setTo(policy.availability.to)
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
    const invalid = firstIncompleteSection(completeDraft, steps, validateStep, selectedDays.length > 0)
    if (invalid) {
      goToStep(invalid.index)
      setErrors(invalid.errors)
      const personError = Object.keys(invalid.errors).find(key => key.startsWith('people.'))
      if (personError) setActivePerson(Number(personError.split('.')[1]))
      return
    }
    if (!reviewing) {
      setReturningToReview(false)
      goToStep(steps.length)
      return
    }

    submissionPending.current = true
    try {
      const displayName = (draft.type === 'Couple' ? draft.people : draft.people.slice(0, 1)).map(person => person.name.trim()).join(' & ')
      const confirmed = await confirmAction({
        title: addingPackage ? `Add package for ${packageDraft.clientName}?` : `Create ${displayName}?`,
        message: `${selectedTrainer.name} will be assigned. ${selectedPack.total} sessions will be created with ${selectedPack.validityDays}-day validity. ${freeGymEligible(draft.sessionsPerWeek, policy.freeGymMinimumFrequency) ? 'Free gym package included.' : ''}`,
        confirmLabel: addingPackage ? 'Add Package' : 'Create Client',
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
    const index = steps.findIndex(item => item.key === key)
    if (index < 0 || saving || submissionPending.current) return
    setReturningToReview(true)
    if (key === 'general') setActivePerson(0)
    goToStep(index)
  }


  return (
    <div className={`client-onboarding${dirty ? ' editing-section' : ''}`}>
      {!addingPackage && <div className="page-head compact-page-head">
        <div><span className="eyebrow">Operations</span><h1>{addingPackage ? 'Add Package' : 'Add New Client'}</h1></div>
        <button type="button" className="onboarding-button" disabled={saving} onClick={onCancel}>Cancel</button>
      </div>}
      <form ref={formRef} noValidate onSubmit={handleSubmit} aria-label={addingPackage ? 'Add package' : 'Client creation'}>
        <Panel>
          <div className="section-head onboarding-step-head">
            <h2 ref={stepHeading} tabIndex={-1}>{step.title}</h2>
            <span className="onboarding-step-count" aria-label="Creation progress">Step {stepIndex + (addingPackage ? 2 : 1)} of {CLIENT_ONBOARDING_STEPS.length + 1}</span>
          </div>
          <fieldset className="onboarding-step-body" disabled={saving}>
            <legend className="visually-hidden">{step.title}</legend>

            {step.key === 'general' && (
              <ClientGeneralFields draft={draft} errors={errors} activePerson={activePerson} setActivePerson={setActivePerson} onChange={update} />
            )}

            {step.key === 'package' && (
              <ClientPackageFields packages={packages} policy={policy} draft={draft} errors={errors} onChange={patch => update(patch, Object.hasOwn(patch, 'sessionsPerWeek') || Object.hasOwn(patch, 'genderPreference'))} />
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
                  <SelectField aria-label="Matched trainer" value={selectedTrainer?.id ?? ''}
                    disabled={!visibleMatches.length} onChange={event => update({ trainerId: event.target.value, fixedWeeklySchedule: undefined })}>
                    <option value="">{visibleMatches.length ? 'Choose a trainer' : 'No matching trainers'}</option>
                    {visibleMatches.map(result => <option key={result.trainer.id} value={result.trainer.id}>{result.trainer.name}</option>)}
                  </SelectField>
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
            {reviewing && <OnboardingReview sections={clientReviewSections(completeDraft, selectedTrainer, policy).filter(section => !addingPackage || section.key !== 'general')} onEdit={editReviewSection} />}
          </fieldset>
          {Object.keys(errors).length > 0 && <p className="onboarding-error" role="alert">{Object.values(errors)[0]}</p>}
          <div className="onboarding-step-actions">
            {!returningToReview && previousStep && <button type="button" className="onboarding-button" disabled={saving} onClick={() => goToStep(stepIndex - 1)}>Back to {previousStep.title}</button>}
            <button type="submit" className="onboarding-button primary" disabled={saving}>
              {saving ? 'Saving…' : reviewing ? (addingPackage ? 'Add Package' : 'Create Client') : returningToReview ? 'Return to Review & Confirm' : `Continue to ${nextStep.title}`}
            </button>
          </div>
        </Panel>
      </form>
    </div>
  )
}
