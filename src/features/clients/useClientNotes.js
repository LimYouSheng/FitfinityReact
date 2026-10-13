import { useEffect, useState } from 'react'

// Notes use a scoped read only while this profile is open. Never retain a result
// across a different directory snapshot, selected client or login generation.
export default function useClientNotes(client, enabled, clientService, generation) {
  const [result, setResult] = useState(null)
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    if (!enabled) return
    let current = true
    clientService.getById({ id: client.id }).then(value => {
      if (!value) throw new Error('This client is no longer available. Reload the portal.')
      if (current) setResult({ source: client, generation, value })
    }).catch(error => {
      if (current) setResult({ source: client, generation, error })
    })
    return () => { current = false }
  }, [client, clientService, enabled, generation, retry])
  const matched = result?.source === client && result.generation === generation
  return { client: enabled ? matched && result.value : client, error: enabled && matched && result.error,
    retry: () => { setResult(null); setRetry(value => value + 1) } }
}
