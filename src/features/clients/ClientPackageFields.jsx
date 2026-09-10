import { weeklyFrequencyLabel, freeGymEligible } from '../../app/packages.js'
import { GENDER_PREFERENCES } from '../../app/contact.js'
import Field from '../../components/OnboardingField.jsx'

export default function ClientPackageFields({ packages, policy, draft, errors = {}, onChange: update }) {
  return (
    <div className="onboarding-grid">
      <div className="onboarding-package-fields">
        <Field label="PT Package" required error={errors.packageId}><select aria-label="PT Package" value={draft.packageId} onChange={event => {
          const item = packages.find(item => item.id === event.target.value)
          if (item) update({ packageId: item.id })
        }}><option value="" disabled>Choose package</option>{packages.map(item => <option value={item.id} key={item.id}>{item.name} · {item.validityDays} days</option>)}</select></Field>
        <Field label="Start date" required error={errors.startDate}>
          <input aria-label="Start date" type="date" min={draft.minimumStartDate} value={draft.startDate} onChange={event => update({ startDate: event.target.value })} />
        </Field>
        <Field label="Weekly frequency" required error={errors.sessionsPerWeek}>
          <select aria-label="Weekly frequency" value={draft.sessionsPerWeek} onChange={event => {
            update({ sessionsPerWeek: Number(event.target.value) })
          }}>
            {policy.weeklyFrequencies.map(frequency => <option key={frequency} value={frequency}>{weeklyFrequencyLabel(frequency)}</option>)}
          </select>
        </Field>
        <Field label="Gym membership">
          <input aria-label="Gym membership" readOnly value={freeGymEligible(draft.sessionsPerWeek, policy.freeGymMinimumFrequency) ? 'Included' : 'Not included'} />
        </Field>
      </div>
      <Field label="Trainer preference">
        <select aria-label="Trainer preference" value={draft.genderPreference} onChange={event => update({ genderPreference: event.target.value })}>
          {GENDER_PREFERENCES.map(preference => <option key={preference}>{preference}</option>)}
        </select>
      </Field>
    </div>
  )
}
