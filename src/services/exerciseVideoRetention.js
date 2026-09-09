import { exerciseVideoExpired, exerciseVideoExpiresAt } from '../app/video.js'
import { mockDb } from './mockDb.js'
import { pruneExerciseVideoBlobs, removeExerciseVideoBlob } from './exerciseVideoStore.js'

const deletionKey = ({ sessionId, exerciseId, mediaId }) => JSON.stringify([sessionId, exerciseId, mediaId ?? null])

export function queueExerciseVideoDeletion(db, sessionId, exerciseId, mediaId) {
  const entry = { sessionId, exerciseId, mediaId: mediaId ?? null }
  db.pendingVideoDeletions ??= []
  if (!db.pendingVideoDeletions.some(item => deletionKey(item) === deletionKey(entry))) db.pendingVideoDeletions.push(entry)
}

export async function flushExerciseVideoDeletions() {
  const pending = mockDb.read().pendingVideoDeletions ?? []
  if (!pending.length) return
  const results = await Promise.allSettled(pending.map(({ sessionId, exerciseId, mediaId }) =>
    removeExerciseVideoBlob(sessionId, exerciseId, mediaId ?? undefined),
  ))
  const deleted = new Set(pending.filter((_, index) => results[index].status === 'fulfilled').map(deletionKey))
  if (!deleted.size) return
  try {
    mockDb.mutate(db => {
      db.pendingVideoDeletions = (db.pendingVideoDeletions ?? []).filter(item => !deleted.has(deletionKey(item)))
    })
  } catch {
    // Keep the durable queue when saving it fails. Repeating a blob deletion is safe.
  }
}

export async function pruneExpiredExerciseVideos(now = new Date()) {
  const snapshot = mockDb.read()
  const expired = session => (session.exercisePlan ?? []).some(item =>
    item.videoAttached && exerciseVideoExpired(item.video, now, snapshot.settings.videoRetentionDays),
  )
  if (snapshot.sessions.some(expired)) {
    mockDb.mutate(db => {
      for (const session of db.sessions) {
        for (const exercise of session.exercisePlan ?? []) {
          if (!exercise.videoAttached || !exerciseVideoExpired(exercise.video, now, db.settings.videoRetentionDays)) continue
          queueExerciseVideoDeletion(db, session.id, exercise.id, exercise.video?.id)
          exercise.videoAttached = false
          exercise.video = null
        }
      }
    })
  }
  await flushExerciseVideoDeletions()
  const current = mockDb.read()
  const retainedExpiries = Object.fromEntries(current.sessions.flatMap(session => (session.exercisePlan ?? [])
    .filter(exercise => exercise.videoAttached)
    .map(exercise => [exercise.video?.id ?? `${session.id}:${exercise.id}`, exerciseVideoExpiresAt(exercise.video, current.settings.videoRetentionDays)])))
  // The same refresh retries failed sweeps; expired metadata is already unavailable to callers.
  await pruneExerciseVideoBlobs(now, retainedExpiries).catch(() => {})
}
