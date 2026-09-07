import { useEffect, useMemo, useRef, useState } from 'react'
import Panel from '../../components/Panel.jsx'
import OnboardingReview from '../../components/OnboardingReview.jsx'
import { ONBOARDING_REVIEW_STEP, trainerReviewSections, firstIncompleteSection } from '../../app/onboardingReview.js'
import Field from '../../components/OnboardingField.jsx'
import AvailabilityEditor from '../../components/AvailabilityEditor.jsx'
import ApprovalSetting from '../../components/ApprovalSetting.jsx'
import { useActionConfirmation } from '../../components/ActionConfirmationProvider.jsx'
import { useEditGuard } from '../../components/EditGuardProvider.jsx'
import { APPROVAL_FIELDS } from '../../app/constants.js'
import { COUNTRY_CODES, GENDERS } from '../../app/contact.js'
import { DAYS, DEFAULT_AVAILABILITY_FROM, DEFAULT_AVAILABILITY_TO, availabilityBlockError } from '../../app/availability.js'
import { TRAINER_ONBOARDING_STEPS, createTrainerDraft, trainerStepErrors } from '../../app/trainerOnboarding.js'

const FORM_STEPS = [...TRAINER_ONBOARDING_STEPS, ONBOARDING_REVIEW_STEP]

export default function AddTrainerPage({ trainers, onCancel, onCreate, onCreated }) {
  const confirmAction = useActionConfirmation()
  const { activeEdit, setActiveEdit } = useEditGuard()
  const [initialDraft] = useState(createTrainerDraft)
  const [draft, setDraft] = useState(initialDraft)
  const [stepIndex, setStepIndex] = useState(0)
  const [returningToReview, setReturningToReview] = useState(false)
  const [selectedDays, setSelectedDays] = useState([])
  const [from, setFrom] = useState(DEFAULT_AVAILABILITY_FROM)
  const [to, setTo] = useState(DEFAULT_AVAILABILITY_TO)
  const [errors, setErrors] = useState({})
  const [saving, setSaving] = useState(false)
  const [created, setCreated] = useState(null)
  const submissionPending = useRef(false)
  const navigationCompleted = useRef(false)
  const nextBlockId = useRef(1)
  const formRef = useRef(null)
  const headingRef = useRef(null)
  const previousIndex = useRef(0)
  const step = FORM_STEPS[stepIndex]
  const reviewing = step.key === 'review'
  const previous = FORM_STEPS[stepIndex - 1]
  const next = FORM_STEPS[stepIndex + 1]
  const dirty = JSON.stringify(draft) !== JSON.stringify(initialDraft) || selectedDays.length > 0 || from !== DEFAULT_AVAILABILITY_FROM || to !== DEFAULT_AVAILABILITY_TO
  const types = useMemo(() => [...new Set(trainers.map(trainer => trainer.trainerType).filter(Boolean))].sort(), [trainers])

  useEffect(() => {
    setActiveEdit(dirty && !created ? 'New trainer' : null)
    return () => setActiveEdit(null)
  }, [created, dirty, setActiveEdit])

  useEffect(() => {
    if (!created || activeEdit || navigationCompleted.current) return
    navigationCompleted.current = true
    onCreated(created.id)
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
    setFrom(DEFAULT_AVAILABILITY_FROM)
    setTo(DEFAULT_AVAILABILITY_TO)
    update({ availabilityBlocks: [] })
  }

  const submit = async event => {
    event.preventDefault()
    if (submissionPending.current || saving || created) return
    const validation = trainerStepErrors(draft, step.key)
    if (step.key === 'availability' && selectedDays.length) {
      validation.availability = 'Select Add Time to include these days before continuing.'
    }
    if (Object.keys(validation).length) { setErrors(validation); return }
    if (!returningToReview && next && next.key !== 'review') { goTo(stepIndex + 1); return }
    const invalid = firstIncompleteSection(draft, TRAINER_ONBOARDING_STEPS, trainerStepErrors, selectedDays.length > 0)
    if (invalid) { goTo(invalid.index); setErrors(invalid.errors); return }
    if (!reviewing) {
      setReturningToReview(false)
      goTo(TRAINER_ONBOARDING_STEPS.length)
      return
    }
    submissionPending.current = true
    try {
      const confirmed = await confirmAction({
        title: `Create ${draft.name.trim()}?`,
        message: 'Create the trainer profile with these rates, approved availability and approval controls? This is a mock account; no login invitation is sent.',
        confirmLabel: 'Create Trainer',
      })
      if (!confirmed) return
      setSaving(true)
      setCreated(await onCreate(draft))
    } catch (error) {
      setSaving(false)
      setErrors({ save: error instanceof Error ? error.message : 'Trainer creation failed. Please try again.' })
    } finally {
      submissionPending.current = false
    }
  }

  const editReviewSection = key => {
    const index = TRAINER_ONBOARDING_STEPS.findIndex(item => item.key === key)
    if (index < 0 || saving || submissionPending.current) return
    setReturningToReview(true)
    goTo(index)
  }

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
            <span className="onboarding-step-count" aria-label="Creation progress">Step {stepIndex + 1} of {FORM_STEPS.length}</span>
          </div>
          <fieldset className="onboarding-step-body" disabled={saving}>
            <legend className="visually-hidden">{step.title}</legend>
            {step.key === 'general' && (
              <div className="onboarding-grid">
                <Field label="Trainer name" required error={errors.name}>
                  <input aria-label="Trainer name" autoComplete="name" value={draft.name} onChange={event => update({ name: event.target.value })} />
                </Field>
                <Field label="Email" required error={errors.email}>
                  <input aria-label="Trainer email" type="email" autoComplete="email" value={draft.email} onChange={event => update({ email: event.target.value })} />
                </Field>
                <Field label="Phone" group error={errors.phoneCountryCode || errors.phoneNumber}>
                  <div className="onboarding-phone-grid">
                    <select aria-label="Trainer phone country code" value={draft.phone.countryCode} aria-invalid={Boolean(errors.phoneCountryCode)} onChange={event => update({ phone: { ...draft.phone, countryCode: event.target.value } })}>
                      {COUNTRY_CODES.map(code => <option key={code}>{code}</option>)}
                    </select>
                    <input aria-label="Trainer phone number" inputMode="tel" aria-invalid={Boolean(errors.phoneNumber)} value={draft.phone.number} onChange={event => update({ phone: { ...draft.phone, number: event.target.value } })} />
                  </div>
                </Field>
                <Field label="Birthday" error={errors.birthday}>
                  <input aria-label="Trainer birthday" type="date" value={draft.birthday} onChange={event => update({ birthday: event.target.value })} />
                </Field>
                <Field label="Gender" required error={errors.gender}>
                  <select aria-label="Trainer gender" value={draft.gender} onChange={event => update({ gender: event.target.value })}>
                    <option value="">Select gender</option>{GENDERS.map(gender => <option key={gender}>{gender}</option>)}
                  </select>
                </Field>
                <Field label="Trainer type" required error={errors.trainerType}>
                  <input aria-label="Trainer type" list="trainer-type-options" value={draft.trainerType} onChange={event => update({ trainerType: event.target.value })} />
                </Field>
                <datalist id="trainer-type-options">{types.map(type => <option key={type} value={type} />)}</datalist>
                <Field label="Public profile" error={errors.publicProfile}>
                  <select aria-label="Trainer public profile" value={draft.publicProfile} onChange={event => update({ publicProfile: event.target.value })}>
                    <option>Visible</option><option>Hidden</option>
                  </select>
                </Field>
                <Field label="Qualifications" className="onboarding-span-2">
                  <textarea aria-label="Trainer qualifications" value={draft.qualifications} onChange={event => update({ qualifications: event.target.value })} />
                </Field>
              </div>
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
                <p className="onboarding-hint">Checked = owner approval needed. Unchecked = direct action allowed.</p>
                <div className="approval-grid">
                  {APPROVAL_FIELDS.map(([field, label]) => (
                    <ApprovalSetting key={field} label={label} checked={draft.approvalNeeded[field]}
                      onChange={checked => update({ approvalNeeded: { ...draft.approvalNeeded, [field]: checked } })} />
                  ))}
                </div>
              </div>
            )}
            {reviewing && <OnboardingReview sections={trainerReviewSections(draft)} onEdit={editReviewSection} />}
          </fieldset>
          {Object.keys(errors).length > 0 && <p className="onboarding-error" role="alert">{Object.values(errors)[0]}</p>}
          <div className="onboarding-step-actions">
            {!returningToReview && previous && <button type="button" className="onboarding-button" disabled={saving} onClick={() => goTo(stepIndex - 1)}>Back to {previous.title}</button>}
            <button type="submit" className="onboarding-button primary" disabled={saving}>
              {saving ? 'Creating…' : reviewing ? 'Create Trainer' : returningToReview ? 'Return to Review & Confirm' : `Continue to ${next.title}`}
            </button>
          </div>
        </Panel>
      </form>
    </div>
  )
}
