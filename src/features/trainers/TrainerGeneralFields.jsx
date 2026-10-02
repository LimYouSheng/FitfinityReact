import StaffPersonalFields from '../../components/StaffPersonalFields.jsx'
import SuggestionField from '../../components/SuggestionField.jsx'
import SelectField from '../../components/SelectField.jsx'
import { useMemo } from 'react'
import Field from '../../components/OnboardingField.jsx'

/** One owner for trainer personal controls in creation and profile editing. */
export default function TrainerGeneralFields({ draft, errors = {}, policy, trainers, onChange: update, requireComplete = false }) {
  const types = useMemo(() => [...new Set([...policy.trainerTypes, ...trainers.map(trainer => trainer.trainerType).filter(Boolean)])].sort(), [policy.trainerTypes, trainers])
  return (
    <div className="onboarding-grid">
      <StaffPersonalFields label="Trainer" draft={draft} errors={errors} onChange={update} requireComplete={requireComplete} />
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
