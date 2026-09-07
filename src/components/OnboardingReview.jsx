import { useId } from 'react'

/** Shared read-only review; the owning form retains the draft and save action. */
export default function OnboardingReview({ sections, onEdit }) {
  const id = useId()
  return (
    <div className="onboarding-review" aria-label="Form summary">
      <p className="onboarding-hint">Review the details below. Nothing is saved until you confirm creation.</p>
      {sections.map(section => (
        <section key={section.key} className="onboarding-review-section" aria-labelledby={`${id}-${section.key}`}>
          <div className="onboarding-review-head">
            <h3 id={`${id}-${section.key}`}>{section.title}</h3>
            <button type="button" className="onboarding-review-edit" aria-label={`Edit ${section.title}`} onClick={() => onEdit(section.key)}>Edit</button>
          </div>
          {section.groups.map((group, index) => (
            <div key={group.title ?? index} className="onboarding-review-group">
              {group.title && <h4>{group.title}</h4>}
              <dl className="onboarding-review-values">
                {group.rows.map(item => <div key={item.label}><dt>{item.label}</dt><dd>{item.value}</dd></div>)}
              </dl>
            </div>
          ))}
        </section>
      ))}
    </div>
  )
}
