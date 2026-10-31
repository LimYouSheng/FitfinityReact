import { canEditTrainerRates } from '../../app/permissions.js'
import { useEffect, useRef } from 'react'
import useCreationForm from '../../hooks/useCreationForm.js'
import Panel from '../../components/Panel.jsx'
import OnboardingReview from '../../components/OnboardingReview.jsx'
import { ONBOARDING_REVIEW_STEP, trainerReviewSections, firstIncompleteSection } from '../../app/onboardingReview.js'
import Field from '../../components/OnboardingField.jsx'
import AvailabilityEditor from '../../components/AvailabilityEditor.jsx'
import ApprovalSetting from '../../components/ApprovalSetting.jsx'
import { useActionConfirmation } from '../../components/ActionConfirmationProvider.jsx'
import { useEditGuard } from '../../components/EditGuardProvider.jsx'
import { APPROVAL_FIELDS } from '../../app/constants.js'
import TrainerGeneralFields from './TrainerGeneralFields.jsx'
import { DAYS, availabilityBlockError } from '../../app/availability.js'
import { TRAINER_ONBOARDING_STEPS, createTrainerDraft, trainerStepErrors } from '../../app/trainerOnboarding.js'

export default function AddTrainerPage({ viewer, policy, trainers, onCancel, onCreate, onCreated, recovery, realAuthentication = false }) {
  const includeRates = canEditTrainerRates(viewer)
  const creationSteps = TRAINER_ONBOARDING_STEPS.filter(step => step.key !== 'rates' || includeRates)
  const formSteps = [...creationSteps, ONBOARDING_REVIEW_STEP]
  const confirmAction = useActionConfirmation()
  const { activeEdit, setActiveEdit } = useEditGuard()
  const { form: creation, update: updateCreation, setter } = useCreationForm(recovery, () => {
    const initialDraft = { ...createTrainerDraft(policy, { includeRates }), ...(realAuthentication ? { requestId: crypto.randomUUID() } : {}) }
    return { initialDraft, draft: initialDraft, stepIndex: 0, returningToReview: false, selectedDays: [],
      from: policy.availability.from, to: policy.availability.to, errors: {}, saving: false, created: null, submitted: null, approvalSubmitted: false }
  })
  const { initialDraft, draft, stepIndex, returningToReview, selectedDays, from, to, errors, saving, created, submitted, approvalSubmitted } = creation
  const setDraft = setter('draft'), setStepIndex = setter('stepIndex'), setReturningToReview = setter('returningToReview')
  const setSelectedDays = setter('selectedDays'), setFrom = setter('from'), setTo = setter('to'), setErrors = setter('errors')
  const submissionPending = useRef(false)
  const navigationCompleted = useRef(false)
  const nextBlockId = useRef(1 + draft.availabilityBlocks.reduce((max, block) => Math.max(max, Number(block.id?.match(/^trainer-block-(\d+)$/)?.[1] ?? 0)), 0))
  const formRef = useRef(null)
  const headingRef = useRef(null)
  const previousIndex = useRef(0)
  const step = formSteps[stepIndex]
  const reviewing = step.key === 'review'
  const previous = formSteps[stepIndex - 1]
  const next = formSteps[stepIndex + 1]
  const dirty = JSON.stringify(draft) !== JSON.stringify(initialDraft) || selectedDays.length > 0 || from !== policy.availability.from || to !== policy.availability.to

  useEffect(() => {
    setActiveEdit(dirty && !created && !approvalSubmitted ? 'New trainer' : null)
    return () => setActiveEdit(null)
  }, [created, dirty, approvalSubmitted, setActiveEdit])

  useEffect(() => {
    if (!created || activeEdit || navigationCompleted.current) return
    navigationCompleted.current = true
    onCreated(created.id, created)
  }, [activeEdit, created, onCreated])

  useEffect(() => {
    if (previousIndex.current === stepIndex) return
    previousIndex.current = stepIndex
    headingRef.current?.focus({ preventScroll: true })
    headingRef.current?.scrollIntoView({ block: 'start' })
  }, [stepIndex])

  useEffect(() => {
    if (Object.keys(errors).length) formRef.current?.querySelector('[aria-invalid="true"]')?.focus()
  }, [errors])

  const update = patch => { setDraft(current => ({ ...current, ...patch })); setErrors({}) }
  const goTo = index => { setErrors({}); setStepIndex(index) }
  const addAvailability = () => {
    const block = { days: DAYS.filter(day => selectedDays.includes(day)), from, to }
    const error = availabilityBlockError(block, draft.availabilityBlocks, true)
    if (error) { setErrors({ availability: error }); return }
    update({ availabilityBlocks: [...draft.availabilityBlocks, { ...block, id: `trainer-block-${nextBlockId.current++}` }] })
    setSelectedDays([])
  }
  const resetAvailability = () => {
    setSelectedDays([])
    setFrom(policy.availability.from)
    setTo(policy.availability.to)
    update({ availabilityBlocks: [] })
  }

  const save = async original => {
    const version = recovery?.version()
    if (!updateCreation({ saving: true, submitted: realAuthentication ? original : null, errors: {} }, version)) return
    try {
      const result = await onCreate(original)
      updateCreation({ created: result, submitted: null, saving: false }, version)
    } catch (error) {
      if (error.code === 'APPROVAL_PENDING') {
        updateCreation({ saving: false, submitted: null, approvalSubmitted: true, errors: {} }, version)
        return
      }
      updateCreation({ saving: false, ...(error.status >= 400 && error.status < 500 ? { submitted: null } : {}),
        errors: { save: error instanceof Error ? error.message : 'Trainer creation failed. Please try again.' } }, version)
    }
  }
  const submit = async event => {
    event.preventDefault()
    if (submissionPending.current || saving || created) return
    if (submitted) {
      submissionPending.current = true
      try { await save(submitted) } finally { submissionPending.current = false }
      return
    }
    const validation = trainerStepErrors(draft, step.key)
    if (step.key === 'availability' && selectedDays.length) {
      validation.availability = 'Select Add Time to include these days before continuing.'
    }
    if (Object.keys(validation).length) { setErrors(validation); return }
    if (!returningToReview && next && next.key !== 'review') { goTo(stepIndex + 1); return }
    const invalid = firstIncompleteSection(draft, creationSteps, trainerStepErrors, selectedDays.length > 0)
    if (invalid) { goTo(invalid.index); setErrors(invalid.errors); return }
    if (!reviewing) {
      setReturningToReview(false)
      goTo(creationSteps.length)
      return
    }
    submissionPending.current = true
    try {
      const confirmed = await confirmAction({
        title: `Create ${draft.name.trim()}?`,
        message: realAuthentication ? 'Create this trainer account with the reviewed profile, approved availability and approval controls, and request a login invitation?' : includeRates ? 'Create the trainer profile with these rates, approved availability and approval controls? This is a mock account; no login invitation is sent.' : 'Create the trainer profile with approved availability and approval controls? Owner-configured default rates will apply. This is a mock account; no login invitation is sent.',
        confirmLabel: 'Create Trainer',
      })
      if (!confirmed) return
      await save(structuredClone(draft))
    } catch (error) {
      setErrors({ save: error instanceof Error ? error.message : 'Trainer creation failed. Please try again.' })
    } finally {
      submissionPending.current = false
    }
  }

  const editReviewSection = key => {
    const index = creationSteps.findIndex(item => item.key === key)
    if (index < 0 || saving || submitted || submissionPending.current) return
    setReturningToReview(true)
    goTo(index)
  }

  if (approvalSubmitted) return <Panel><h1>Trainer request submitted</h1>
    <p role="status">Submitted for Owner approval. No Trainer account has been created yet. Owner approval will automatically request the login invitation.</p>
    <button type="button" className="onboarding-button" onClick={onCancel}>Done</button>
  </Panel>

  return (
    <div className={`trainer-onboarding${dirty ? ' editing-section' : ''}`}>
      <div className="page-head compact-page-head">
        <div><span className="eyebrow">Operations</span><h1>Add New Trainer</h1></div>
        <button type="button" className="onboarding-button" disabled={saving} onClick={onCancel}>Cancel</button>
      </div>
      <form ref={formRef} noValidate onSubmit={submit} aria-label="Trainer creation">
        <Panel>
          <div className="section-head onboarding-step-head">
            <h2 ref={headingRef} tabIndex={-1}>{step.title}</h2>
            <span className="onboarding-step-count" aria-label="Creation progress">Step {stepIndex + 1} of {formSteps.length}</span>
          </div>
          <fieldset className="onboarding-step-body" disabled={saving || Boolean(submitted)}>
            <legend className="visually-hidden">{step.title}</legend>
            {step.key === 'general' && (
              <TrainerGeneralFields requireComplete draft={draft} errors={errors} policy={policy} trainers={trainers} onChange={update} />
            )}
            {step.key === 'rates' && (
              <div className="onboarding-grid">
                <Field label="Peak session rate (S$)" required error={errors.peak}>
                  <input aria-label="Peak session rate" type="number" min="0" step="0.01" value={draft.rates.peak} onChange={event => update({ rates: { ...draft.rates, peak: event.target.value } })} />
                </Field>
                <Field label="Off-peak session rate (S$)" required error={errors.offPeak}>
                  <input aria-label="Off-peak session rate" type="number" min="0" step="0.01" value={draft.rates.offPeak} onChange={event => update({ rates: { ...draft.rates, offPeak: event.target.value } })} />
                </Field>
              </div>
            )}
            {step.key === 'availability' && (
              <AvailabilityEditor blocks={draft.availabilityBlocks} selectedDays={selectedDays}
                from={from} to={to} error={errors.availability} listLabel="Trainer availability blocks"
                onToggleDay={day => { setSelectedDays(current => current.includes(day) ? current.filter(value => value !== day) : [...current, day]); setErrors({}) }}
                onFrom={value => { setFrom(value); setErrors({}) }} onTo={value => { setTo(value); setErrors({}) }}
                onAdd={addAvailability} onRemove={id => update({ availabilityBlocks: draft.availabilityBlocks.filter(block => block.id !== id) })}
                onReset={resetAvailability}
              />
            )}
            {step.key === 'autonomy' && (
              <div className="onboarding-availability">
                <h3>Owner approval required</h3>
                <div className="approval-grid">
                  {APPROVAL_FIELDS.map(([field, label]) => (
                    <ApprovalSetting key={field} label={label} checked={draft.approvalNeeded[field]}
                      onChange={checked => update({ approvalNeeded: { ...draft.approvalNeeded, [field]: checked } })} />
                  ))}
                </div>
              </div>
            )}
            {reviewing && <OnboardingReview sections={trainerReviewSections(draft, { includeRates })} onEdit={editReviewSection} />}
          </fieldset>
          {Object.keys(errors).length > 0 && <p className="onboarding-error" role="alert">{Object.values(errors)[0]}</p>}
          <div className="onboarding-step-actions">
            {!returningToReview && previous && <button type="button" className="onboarding-button" disabled={saving || Boolean(submitted)} onClick={() => goTo(stepIndex - 1)}>Back to {previous.title}</button>}
            <button type="submit" className="onboarding-button primary" disabled={saving}>
              {saving ? 'Creating…' : submitted ? 'Check Trainer Creation' : reviewing ? 'Create Trainer' : returningToReview ? 'Return to Review & Confirm' : `Continue to ${next.title}`}
            </button>
          </div>
        </Panel>
      </form>
    </div>
  )
}
