import { useEffect, useState } from 'react'

/** Refresh persisted charts without retaining another client's or login's measurements. */
export default function useClientProgress(id, enabled, services, generation, serverAt) {
  const [state, setState] = useState(null)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    if (!enabled) return
    let current = true
    services.readClientProgress({ id }).then(exercises => {
      if (current) setState({ id, generation, exercises })
    }).catch(error => { if (current) setState({ id, generation, error }) })
    return () => { current = false }
  }, [id, enabled, services, generation, serverAt, attempt])
  const matching = state?.id === id && state.generation === generation
  return { exercises: enabled && matching ? state.exercises : undefined,
    loading: enabled && !matching, error: enabled && matching ? state.error : null,
    retry: () => setAttempt(n => n + 1) }
}
