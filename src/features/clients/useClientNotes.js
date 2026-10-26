import { useEffect, useState } from 'react'

// Preserve the reviewed profile while editing so background versions cannot erase
// child drafts. A changed identity, assignment or active status retires it immediately.
export default function useClientNotes(client, enabled, clientService, generation, readClientNotes, editing = false) {
  const [result, setResult] = useState(null)
  const [retry, setRetry] = useState(0)
  const source = JSON.stringify(client)
  const clientId = client.id
  const scope = JSON.stringify([clientId, generation, client.trainerId, client.status, client.people?.map(person => person.id)])
  const holding = editing && result?.scope === scope && Boolean(result.value) && !result.error
  useEffect(() => {
    if (!enabled || holding) return
    let current = true
    const request = readClientNotes ? readClientNotes(JSON.parse(source)) : clientService.getById({ id: clientId })
    request.then(value => {
      if (!value) throw Object.assign(new Error('This client is no longer available. Reload the portal.'), { status: 404 })
      if (current) setResult(previous => editing && previous?.scope === scope && previous.value ? { ...previous, error: null } : { source, scope, generation, value })
    }).catch(error => {
      if (current) setResult(previous => ({ source, scope, generation, error, value: ![401, 403, 404].includes(error.status) && !['SESSION_CHANGED', 'SESSION_EXPIRED', 'forbidden', 'unauthorized', 'not_found'].includes(error.code) && previous?.scope === scope ? previous.value : null }))
    })
    return () => { current = false }
  }, [source, clientId, clientService, enabled, generation, retry, readClientNotes, editing, scope, holding])
  const matched = result?.scope === scope
  return { client: enabled ? matched && result.value : client, error: enabled && matched && result.error,
    retry: () => setRetry(value => value + 1) }
}
