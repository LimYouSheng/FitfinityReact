import { Children, cloneElement, isValidElement, useId } from 'react'

// Derive the empty-required treatment from controlled values, including grouped phone controls.
function requiredTreatment(children) {
  return Children.map(children, child => {
    if (!isValidElement(child)) return child
    const props = child.props
    const required = props.required || props['aria-required'] === true || props['aria-required'] === 'true'
    const empty = props.type === 'checkbox' ? !props.checked : String(props.value ?? '').trim() === ''
    return cloneElement(child, {
      ...(required ? { 'data-required-empty': empty || undefined } : {}),
      ...(props.children ? { children: requiredTreatment(props.children) } : {}),
    })
  })
}

/** One owner for the labels, required treatment and errors in onboarding forms. */
export default function OnboardingField({ label, required = false, error, group = false, className = '', children }) {
  const id = useId()
  const classes = ['onboarding-field', required && 'required', error && 'has-error', className].filter(Boolean).join(' ')
  const caption = <><span>{label}</span>{required && <span className="onboarding-required">Required</span>}</>

  if (group) {
    return (
      <fieldset className={classes} aria-describedby={error ? `${id}-error` : undefined}>
        <legend className="onboarding-label">{caption}</legend>
        {requiredTreatment(children)}
        {error && <span className="onboarding-field-error" id={`${id}-error`}>{error}</span>}
      </fieldset>
    )
  }

  return (
    <div className={classes}>
      <label className="onboarding-label" htmlFor={id}>{caption}</label>
      {requiredTreatment(cloneElement(children, {
        id,
        required,
        'aria-required': required || undefined,
        'aria-invalid': Boolean(error),
        'aria-describedby': error ? `${id}-error` : undefined,
      }))}
      {error && <span className="onboarding-field-error" id={`${id}-error`}>{error}</span>}
    </div>
  )
}
