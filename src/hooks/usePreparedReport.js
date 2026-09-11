import { useEffect, useMemo, useState } from 'react'

// Equivalent snapshots do not re-render a PDF on the portal's clock refresh.
// A changed selection invalidates the old file immediately, including before
// its effect runs. Late completions after a change or unmount are discarded.
export default function usePreparedReport(prepare, source, enabled = true) {
  const key = JSON.stringify(source)
  const input = useMemo(() => JSON.parse(key), [key])
  const [attempt, setAttempt] = useState(0)
  const [result, setResult] = useState(null)
  useEffect(() => {
    if (!enabled) return
    let active = true
    Promise.resolve().then(() => active ? prepare(input) : null).then(file => {
      if (active) setResult({ key, prepare, attempt, file, error: '' })
    }).catch(error => {
      if (active) setResult({ key, prepare, attempt, file: null, error: error.message || 'The PDF could not be prepared.' })
    })
    return () => { active = false }
  }, [prepare, input, key, attempt, enabled])
  const current = enabled && result?.key === key && result.prepare === prepare && result.attempt === attempt ? result : null
  return { file: current?.file ?? null, error: current?.error ?? '', preparing: enabled && !current, retry: () => setAttempt(value => value + 1) }
}
