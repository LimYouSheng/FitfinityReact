import DateField from '../../components/DateField.jsx'
import SuggestionField from '../../components/SuggestionField.jsx'
import SelectField from '../../components/SelectField.jsx'
import { useMemo } from 'react'
import Field from '../../components/OnboardingField.jsx'
import { COUNTRY_CODES, GENDERS } from '../../app/contact.js'

/** One owner for trainer personal controls in creation and profile editing. */
export default function TrainerGeneralFields({ draft, errors = {}, policy, trainers, onChange: update, requireComplete = false }) {
  const types = useMemo(() => [...new Set([...policy.trainerTypes, ...trainers.map(trainer => trainer.trainerType).filter(Boolean)])].sort(), [policy.trainerTypes, trainers])
  return (
    <div className="onboarding-grid">
      <Field label="Trainer name" required error={errors.name}>
        <input aria-label="Trainer name" autoComplete="name" value={draft.name} onChange={event => update({ name: event.target.value })} />
      </Field>
      <Field label="Email" required error={errors.email}>
        <input aria-label="Trainer email" type="email" autoComplete="email" value={draft.email} onChange={event => update({ email: event.target.value })} />
      </Field>
      <Field label="Phone" required={requireComplete} group error={errors.phoneCountryCode || errors.phoneNumber}>
        <div className="onboarding-phone-grid">
          <SelectField aria-label="Trainer phone country code" required={requireComplete} aria-required={requireComplete || undefined} value={draft.phone.countryCode} aria-invalid={Boolean(errors.phoneCountryCode)} onChange={event => update({ phone: { ...draft.phone, countryCode: event.target.value } })}>
            {COUNTRY_CODES.map(code => <option key={code}>{code}</option>)}
          </SelectField>
          <input aria-label="Trainer phone number" required={requireComplete} aria-required={requireComplete || undefined} inputMode="tel" aria-invalid={Boolean(errors.phoneNumber)} value={draft.phone.number} onChange={event => update({ phone: { ...draft.phone, number: event.target.value } })} />
        </div>
      </Field>
      <Field label="Birthday" required={requireComplete} error={errors.birthday}>
        <DateField aria-label="Trainer birthday"  value={draft.birthday} onChange={event => update({ birthday: event.target.value })} />
      </Field>
      <Field label="Gender" required error={errors.gender}>
        <SelectField aria-label="Trainer gender" value={draft.gender} onChange={event => update({ gender: event.target.value })}>
          <option value="">Select gender</option>{GENDERS.map(gender => <option key={gender}>{gender}</option>)}
        </SelectField>
      </Field>
      <Field label="Trainer type" required error={errors.trainerType}>
        <SuggestionField aria-label="Trainer type" options={types} value={draft.trainerType} onChange={event => update({ trainerType: event.target.value })} />
      </Field>
      <Field label="Public profile" error={errors.publicProfile}>
        <SelectField aria-label="Trainer public profile" value={draft.publicProfile} onChange={event => update({ publicProfile: event.target.value })}>
          <option>Visible</option><option>Hidden</option>
        </SelectField>
      </Field>
      <Field label="Qualifications" className="onboarding-span-2">
        <textarea aria-label="Trainer qualifications" value={draft.qualifications} onChange={event => update({ qualifications: event.target.value })} />
      </Field>
    </div>
  )
}
