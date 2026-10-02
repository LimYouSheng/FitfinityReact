import { useId } from 'react'

/** Shared read-only review; the owning form retains the draft and save action. */
export default function OnboardingReview({ sections, onEdit, onOpen }) {
  const id = useId()
  return (
    <div className="onboarding-review" aria-label="Form summary">
      {sections.map(section => (
        <section key={section.key} className="onboarding-review-section" aria-labelledby={`${id}-${section.key}`}>
          <div className="onboarding-review-head">
            <h3 id={`${id}-${section.key}`}>{section.title}</h3>
            <button type="button" className="onboarding-review-edit" aria-label={`Edit ${section.title}`} onClick={() => onEdit(section.key)}>Edit</button>
          </div>
          {section.groups.map((group, index) => (
            <div key={group.title ?? index} className="onboarding-review-group">
              {group.title && <h4>{group.title}</h4>}
              {section.layout === 'assessments' ? <ul className="onboarding-review-assessments" aria-label={`Assessment summary for ${group.title}`}>
                {group.rows.map(item => {
                  const content = <><strong>{item.label}</strong><span className={`onboarding-review-status${item.open ? ' is-filled' : ''}`}>{item.value}</span>
                    {item.detail && <span className="onboarding-review-detail">{item.detail}</span>}</>
                  return <li key={item.label}>{item.open && onOpen
                    ? <button type="button" className="onboarding-review-form" aria-label={`View ${item.label} for ${group.title}`}
                      onClick={event => { event.currentTarget.focus({ preventScroll: true }); onOpen(item.open) }}>{content}</button>
                    : <div className="onboarding-review-form">{content}</div>}</li>
                })}
              </ul> : <dl className="onboarding-review-values">
                {group.rows.map(item => <div key={item.label}>
                  <dt>{item.label}</dt>
                  <dd>{item.value}</dd>
                </div>)}
              </dl>}
            </div>
          ))}
        </section>
      ))}
    </div>
  )
}
