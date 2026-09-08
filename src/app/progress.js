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

export function updateClientProgress(db, clientId) {
  const client = db.clients.find(item => item.id === clientId)
  if (!client) return
  client.progressBaseline ??= structuredClone(client.strengthProgress ?? [])
  const exercises = structuredClone(client.progressBaseline)
  for (const session of db.sessions.filter(item => item.clientId === clientId && item.status === 'completed')) {
    for (const result of session.exerciseResults ?? []) {
      let exercise = exercises.find(item => item.name.toLowerCase() === result.name.toLowerCase())
      if (!exercise) { exercise = { id: `progress-${result.id}`, name: result.name, points: [] }; exercises.push(exercise) }
      exercise.points.push({ id: `result-${session.id}-${result.id}`, sessionId: session.id, date: session.date, load: result.loadKg, reps: result.reps, sets: result.sets })
    }
  }
  for (const exercise of exercises) exercise.points.sort((a, b) => `${a.date}|${a.id}`.localeCompare(`${b.date}|${b.id}`))
  client.strengthProgress = exercises.filter(exercise => exercise.points.length)
}
