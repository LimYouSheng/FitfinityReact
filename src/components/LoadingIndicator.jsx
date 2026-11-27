/** Animated brand mark; the status remains available to assistive technology. */
export default function LoadingIndicator({ label = 'Loading…' }) {
  return <span className="loading-indicator" role="status">
    <svg viewBox="0 0 108 80" aria-hidden="true" focusable="false">
      <path className="loading-wave" d="M6 29v28" />
      <path className="loading-wave" d="M21 16v54" />
      <g className="loading-wave loading-person">
        <circle cx="54" cy="22" r="6" />
        <path d="M36 7v14a18 18 0 0 0 36 0V7M36 78V61a18 18 0 0 1 36 0v17" />
      </g>
      <path className="loading-wave" d="M87 16v54" />
      <path className="loading-wave" d="M102 29v28" />
    </svg>
    <span className="loading-status-text">{label}</span>
  </span>
}
