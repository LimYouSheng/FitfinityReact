const paths = { close: 'M6 6l12 12M18 6 6 18', back: 'm15 6-6 6 6 6', next: 'm9 6 6 6-6 6', chevron: 'm6 9 6 6 6-6' }

export default function ControlIcon({ name, className = '' }) {
  return <svg className={`control-icon ${className}`} viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d={paths[name]} /></svg>
}
