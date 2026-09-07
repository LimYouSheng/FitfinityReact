import { cloneElement, useId } from 'react'

/** One owner for the labels, required treatment and errors in onboarding forms. */
export default function OnboardingField({ label, required = false, error, group = false, className = '', children }) {
  const id = useId()
  const classes = ['onboarding-field', required && 'required', error && 'has-error', className].filter(Boolean).join(' ')
  const caption = <><span>{label}</span>{required && <span className="onboarding-required">Required</span>}</>

  if (group) {
    return (
      <fieldset className={classes} aria-describedby={error ? `${id}-error` : undefined}>
        <legend className="onboarding-label">{caption}</legend>
        {children}
        {error && <span className="onboarding-field-error" id={`${id}-error`}>{error}</span>}
      </fieldset>
    )
  }

  return (
    <div className={classes}>
      <label className="onboarding-label" htmlFor={id}>{caption}</label>
      {cloneElement(children, {
        id,
        required,
        'aria-required': required || undefined,
        'aria-invalid': Boolean(error),
        'aria-describedby': error ? `${id}-error` : undefined,
      })}
      {error && <span className="onboarding-field-error" id={`${id}-error`}>{error}</span>}
    </div>
  )
}
