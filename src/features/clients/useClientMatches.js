import { useEffect, useState } from 'react'
import { clientMatchBody } from '../../services/apiClientCreation.js'

export default function useClientMatches(preview, draft, trainers, enabled) {
  const [result, setResult] = useState({ request: null, matches: [], error: '' })
  const [attempt, setAttempt] = useState(0)
  const query = preview && enabled ? JSON.stringify(clientMatchBody(draft)) : null
  const request = query ? JSON.stringify([query, attempt, trainers.map(t => [t.id, t.version, t.status])]) : null
  useEffect(() => {
    if (!request) return
    let current = true
    void preview(JSON.parse(query)).then(matches => {
      const resolved = matches.map(match => {
        const trainer = trainers.find(t => t.id === match.trainerId && t.version === match.trainerVersion && t.status === 'active')
        if (!trainer) throw new Error('Trainer details changed. Reload and review matching again.')
        return { ...match, trainer, schedule: match.schedule.map((s, i) => ({ ...s, id: `new-slot-${i + 1}` })) }
      })
      if (current) setResult({ request, matches: resolved, error: '' })
    }).catch(error => { if (current) setResult({ request, matches: [], error: error.message }) })
    return () => { current = false }
  }, [query, request, preview, trainers])
  const retry = () => setAttempt(value => value + 1)
  return result.request === request ? { ...result, loading: false, retry } : { matches: [], error: '', loading: Boolean(request), retry }
}
