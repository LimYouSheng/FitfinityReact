export const PROGRESS_REPORT_ACTIONS = {
  csv_export: 'CSV export',
  whatsapp_opened: 'WhatsApp opened',
}

export function validateExerciseResults(results) {
  if (!Array.isArray(results)) throw new Error('Recorded exercise results are required.')
  const ids = new Set()
  return results.filter(row => row.loadKg !== '' && row.loadKg != null).map(row => {
    const load = Number(row.loadKg), reps = Number(row.reps), sets = Number(row.sets)
    if (!row.id || ids.has(row.id) || !row.name?.trim() || !Number.isFinite(load) || load < 0 || load > 2000 || !Number.isInteger(reps) || reps < 1 || reps > 1000 || !Number.isInteger(sets) || sets < 1 || sets > 100) throw new Error('Each recorded result needs a load of 0–2000 kg, 1–1000 reps and 1–100 sets.')
    ids.add(row.id)
    return { id: row.id, name: row.name.trim(), loadKg: load, reps, sets }
  })
}

// A signed plan supplies defaults; explicit measured results take precedence.
export function exerciseResultsFor(session) {
  return (session.exercisePlan ?? []).map(item => {
    const saved = session.exerciseResults?.find(result => result.id === item.id)
    if (saved) return { ...saved }
    const match = String(item.weight ?? '').trim().match(/^(\d+(?:\.\d+)?)\s*(?:kg)?$/i)
    const load = match ? Number(match[1]) : null
    const reps = Number(item.reps), sets = Number(item.rounds)
    const usable = load != null && load <= 2000 && Number.isInteger(reps) && reps >= 1 && reps <= 1000 && Number.isInteger(sets) && sets >= 1 && sets <= 100
    return { id: item.id, name: item.name, loadKg: usable && !session.exerciseResults ? load : '', reps: item.reps, sets: item.rounds }
  })
}

export function updateClientProgress(db, clientId) {
  const client = db.clients.find(item => item.id === clientId)
  if (!client) return
  client.progressBaseline ??= structuredClone(client.strengthProgress ?? []).map(exercise => ({
    ...exercise, points: exercise.points.filter(point => !point.sessionId),
  }))
  const exercises = structuredClone(client.progressBaseline)
  for (const session of db.sessions.filter(item => item.clientId === clientId && item.status === 'completed')) {
    if (session.acknowledgement?.method === 'late_no_show') continue
    const results = session.exerciseResults ?? (session.acknowledgement?.method === 'signature' ? validateExerciseResults(exerciseResultsFor(session)) : [])
    for (const result of results) {
      let exercise = exercises.find(item => item.name.toLowerCase() === result.name.toLowerCase())
      if (!exercise) { exercise = { id: `progress-${result.id}`, name: result.name, points: [] }; exercises.push(exercise) }
      exercise.points.push({ id: `result-${session.id}-${result.id}`, sessionId: session.id, date: session.date, load: result.loadKg, reps: result.reps, sets: result.sets })
    }
  }
  for (const exercise of exercises) exercise.points.sort((a, b) => `${a.date}|${a.id}`.localeCompare(`${b.date}|${b.id}`))
  client.strengthProgress = exercises.filter(exercise => exercise.points.length)
}
