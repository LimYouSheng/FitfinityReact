import { createContext, useCallback, useContext, useEffect, useId, useMemo, useState } from 'react'

const PageLoadingContext = createContext(null)

/** Keep pending readers mounted while presenting one loader in the content body. */
export function PageLoadingBoundary({ children, section = false }) {
  const [requests, setRequests] = useState({})
  const register = useCallback((id, label) => {
    setRequests(current => ({ ...current, [id]: label }))
    return () => setRequests(current => { const next = { ...current }; delete next[id]; return next })
  }, [])
  const context = useMemo(() => ({ register }), [register])
  const labels = Object.values(requests)
  return <PageLoadingContext.Provider value={context}>
    <div className="page-load-content" inert={labels.length > 0} aria-hidden={labels.length ? true : undefined} data-loading={labels.length > 0}>{children}</div>
    {labels.length > 0 && <div className={section ? 'section-loading-overlay' : 'page-loading-overlay'}><LoadingMark label={labels.join(' ')} /></div>}
  </PageLoadingContext.Provider>
}

/** Animated brand mark; the status remains available to assistive technology. */
export default function LoadingIndicator({ label = 'Loading…' }) {
  const context = useContext(PageLoadingContext)
  const id = useId()
  useEffect(() => context?.register(id, label), [context, id, label])
  return context ? null : <LoadingMark label={label} />
}

function LoadingMark({ label }) {
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
    <span className="loading-caption" aria-hidden="true">Lifting the weights...</span>
    <span className="loading-status-text">{label}</span>
  </span>
}
