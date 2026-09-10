import { useMemo } from 'react'
import Field from '../../components/OnboardingField.jsx'
import { COUNTRY_CODES, GENDERS } from '../../app/contact.js'

/** One owner for trainer personal controls in creation and profile editing. */
export default function TrainerGeneralFields({ draft, errors = {}, policy, trainers, onChange: update }) {
  const types = useMemo(() => [...new Set([...policy.trainerTypes, ...trainers.map(trainer => trainer.trainerType).filter(Boolean)])].sort(), [policy.trainerTypes, trainers])
  return (
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
  )
}
