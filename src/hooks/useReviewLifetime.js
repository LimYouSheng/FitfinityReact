import { useCallback, useEffect, useRef } from 'react'

/** Bind an opening review to this enabled record; later edits cannot revive it. */
export default function useReviewLifetime(disabled, identity = '') {
  const lifetime = useRef(null)
  useEffect(() => {
    lifetime.current = {}
    return () => { lifetime.current = null }
  }, [disabled, identity])
  return useCallback(() => {
    const started = lifetime.current
    return () => started !== null && lifetime.current === started
  }, [])
}
