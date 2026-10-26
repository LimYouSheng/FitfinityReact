import { useEffect, useState } from 'react'

// Notes use a scoped read only while this profile is open. Never retain a result
// across changed directory data, selected client or login generation. An equivalent
// periodic directory snapshot must not unmount a profile with an open editor.
export default function useClientNotes(client, enabled, clientService, generation, readClientNotes) {
  const [result, setResult] = useState(null)
  const [retry, setRetry] = useState(0)
  const source = JSON.stringify(client)
  const clientId = client.id
  useEffect(() => {
    if (!enabled) return
    let current = true
    const request = readClientNotes ? readClientNotes(JSON.parse(source)) : clientService.getById({ id: clientId })
    request.then(value => {
      if (!value) throw new Error('This client is no longer available. Reload the portal.')
      if (current) setResult({ source, generation, value })
    }).catch(error => {
      if (current) setResult({ source, generation, error })
    })
    return () => { current = false }
  }, [source, clientId, clientService, enabled, generation, retry, readClientNotes])
  const matched = result?.source === source && result.generation === generation
  return { client: enabled ? matched && result.value : client, error: enabled && matched && result.error,
    retry: () => { setResult(null); setRetry(value => value + 1) } }
}
