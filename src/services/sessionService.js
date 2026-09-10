import { ensureClientPackageReferences, packageForRecord, requireActiveSessionClient } from '../app/clientPackages.js'
import { exerciseVideoExpired, exerciseVideoExpiresAt, exerciseVideoFileValidation, exerciseVideoValidation } from '../app/video.js'
import { validSignature } from '../app/signature.js'
import { validateExerciseResults, updateClientProgress, exerciseResultsFor } from '../app/progress.js'
import { hasSessionDebit, normalizeExercisePlan, validateExercisePlan, sessionActionError, sessionDurationMinutes } from '../app/sessionRules.js'
import { businessClock } from '../app/clock.js'
import { appendRenewalMessage } from '../app/renewals.js'
import { sessionTimeChangeError, requireActiveActor } from '../app/scheduleChanges.js'
import { delay, mockDb } from './mockDb.js'
import { appendSavedEditMessage } from './editMessage.js'
import { loadExerciseVideoBlob, saveExerciseVideoBlob, removeExerciseVideoBlob } from './exerciseVideoStore.js'
import { flushExerciseVideoDeletions, pruneExpiredExerciseVideos, queueExerciseVideoDeletion } from './exerciseVideoRetention.js'

const clone = value => JSON.parse(JSON.stringify(value))

const messageId = prefix => `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`

function requireSession(db, sessionId) {
  const session = db.sessions.find(item => item.id === sessionId)
  if (!session) throw new Error('Session not found.')
  return session
}

function requireTrainingDate(db, session) {
  const error = sessionActionError(session, businessClock(new Date(), db.settings.timeZone).date)
  if (error) throw new Error(error)
}

function requireAcknowledgementActor(db, session, actor) {
  const staff = requireActiveActor(db, actor)
  if (staff.role !== 'owner' && (staff.role !== 'trainer' || staff.trainerId !== session.trainerId)) throw new Error('This session is unavailable for your account.')
  return { id: staff.id, name: staff.name, role: staff.role }
}

function acknowledgementInput(value) {
  return {
    method: value.method,
    signerName: value.method === 'signature' ? value.signerName?.trim() ?? '' : '',
    signature: value.method === 'signature' ? value.signature : null,
    note: value.note?.trim() ?? '',
  }
}

function acknowledgementUnchanged(previous, input) {
  return previous && JSON.stringify(acknowledgementInput(previous)) === JSON.stringify(input)
}

function requireAcknowledgementTransition(previous, input) {
  if (previous?.method === 'signature') throw new Error('The client signature is permanent and cannot be changed or removed.')
  if (previous?.method === 'late_no_show' && input.method !== 'signature') throw new Error('A trainer acknowledgement can only be corrected to a client signature.')
}

function previousPlan(db, session) {
  return db.sessions
    .filter(candidate =>
      candidate.id !== session.id &&
      candidate.clientId === session.clientId &&
      candidate.date < session.date &&
      candidate.exercisePlan?.length
    )
    .sort((a, b) => `${b.date}T${b.from}`.localeCompare(`${a.date}T${a.from}`))[0]
}

function requireEditableSession(db, sessionId) {
  const session = requireSession(db, sessionId)
  requireActiveSessionClient(db.clients.find(item => item.id === session.clientId), session)
  if (session.status === 'completed') throw new Error('Completed sessions are locked.')
  return session
}

function requireValidSchedule(patch) {
  if (!patch.date || !patch.from || !patch.to || patch.from >= patch.to) {
    throw new Error('Choose a valid date, start time and end time.')
  }
}

function requireAssignedTrainer(db, session, actor) {
  if (actor.role !== 'trainer' || actor.trainerId !== session.trainerId) {
    throw new Error('Only the assigned trainer can change this session.')
  }

  const trainer = db.trainers.find(item => item.id === actor.trainerId)
  if (!trainer || trainer.status === 'inactive') throw new Error('Assigned trainer is not active.')
  return trainer
}

function scheduleSnapshot(session) {
  return { date: session.date, from: session.from, to: session.to }
}

function appendSessionEdit(db, session, title, body) {
  const client = db.clients.find(item => item.id === session.clientId)
  appendSavedEditMessage(db, {
    sessionId: session.id,
    clientId: session.clientId,
    trainerId: session.trainerId,
    title: `${title}: ${client?.name ?? session.id}`,
    body,
  })
}

export const sessionService = {
  async loadVideo(sessionId, exerciseId) {
    const db = mockDb.read()
    const session = requireSession(db, sessionId)
    const exercise = session.exercisePlan?.find(item => item.id === exerciseId)
    if (!exercise?.videoAttached) return null
    if (exerciseVideoExpired(exercise.video, new Date(), db.settings.videoRetentionDays)) {
      await pruneExpiredExerciseVideos()
      throw new Error('This video has expired and is no longer available.')
    }
    const blob = await loadExerciseVideoBlob(sessionId, exerciseId, exercise.video?.id)
    if (exerciseVideoExpired(exercise.video, new Date(), db.settings.videoRetentionDays)) {
      await pruneExpiredExerciseVideos()
      throw new Error('This video has expired and is no longer available.')
    }
    return blob
  },
  async saveVideo(sessionId, exerciseId, file, metadata) {
    const snapshot = mockDb.read()
    const session = requireEditableSession(snapshot, sessionId)
    const exercise = session.exercisePlan?.find(item => item.id === exerciseId)
    if (!exercise) throw new Error('Exercise not found.')
    const deferredProcessing = metadata?.processingStatus === 'deferred'
    const error = deferredProcessing
      ? exerciseVideoFileValidation(file)
      : exerciseVideoValidation(file, metadata?.duration)
    if (error) throw new Error(error)
    if (!deferredProcessing && metadata?.audioIncluded !== false) throw new Error('Prepare a silent exercise video before saving.')
    const attachedAt = new Date().toISOString()
    const expiresAt = exerciseVideoExpiresAt({ attachedAt }, snapshot.settings.videoRetentionDays)
    if (!expiresAt) throw new Error('The video retention policy is unavailable. Refresh and try again.')
    const previous = JSON.stringify(exercise.video ?? null)
    const mediaId = await saveExerciseVideoBlob(sessionId, exerciseId, file, { expiresAt })
    try {
      mockDb.mutate(db => {
        const currentSession = requireEditableSession(db, sessionId)
        const current = currentSession.exercisePlan?.find(item => item.id === exerciseId)
        if (!current || JSON.stringify(current.video ?? null) !== previous) throw new Error('The exercise video changed. Refresh and try again.')
        if (current.videoAttached) queueExerciseVideoDeletion(db, sessionId, exerciseId, current.video?.id)
        current.videoAttached = true
        current.video = { ...metadata, id: mediaId, type: file.type, size: file.size, attachedAt, expiresAt }
        appendSessionEdit(db, currentSession, 'Exercise video saved', current.name)
      })
    } catch (error) {
      await removeExerciseVideoBlob(sessionId, exerciseId, mediaId).catch(() => {})
      throw error
    }
    await flushExerciseVideoDeletions()
    return { id: mediaId }
  },
  async removeVideo(sessionId, exerciseId) {
    mockDb.mutate(db => {
      const session = requireEditableSession(db, sessionId)
      const exercise = session.exercisePlan?.find(item => item.id === exerciseId)
      if (!exercise) throw new Error('Exercise not found.')
      if (exercise.videoAttached) queueExerciseVideoDeletion(db, sessionId, exerciseId, exercise.video?.id)
      exercise.videoAttached = false; exercise.video = null
      appendSessionEdit(db, session, 'Exercise video removed', exercise.name)
    })
    await flushExerciseVideoDeletions()
  },
  async updateDetails(sessionId, patch) {
    await delay()
    requireValidSchedule(patch)

    const state = mockDb.mutate(db => {
      const session = requireEditableSession(db, sessionId)
      const replacement = db.trainers.find(item => item.id === patch.trainerId && item.status !== 'inactive')
      if (!replacement) throw new Error('Choose an active trainer.')

      Object.assign(session, {
        date: patch.date,
        from: patch.from,
        to: patch.to,
        trainerId: patch.trainerId,
        detailsUpdatedAt: new Date().toISOString(),
      })
      if (session.outcome) session.outcome.durationMinutes = sessionDurationMinutes(session)
      appendSessionEdit(db, session, 'Session details saved', `${session.date} · ${session.from}–${session.to}`)
    })

    return state.sessions.find(item => item.id === sessionId)
  },

  async requestTimeChange(sessionId, actor, patch) {
    await delay()
    requireValidSchedule(patch)
    let outcome = 'applied'

    const state = mockDb.mutate(db => {
      const session = requireEditableSession(db, sessionId)
      const trainer = requireAssignedTrainer(db, session, actor)
      const client = db.clients.find(item => item.id === session.clientId)
      const previous = scheduleSnapshot(session)
      const next = { date: patch.date, from: patch.from, to: patch.to }
      const timeError = sessionTimeChangeError(session, next, businessClock(new Date(), db.settings.timeZone))
      if (timeError) throw new Error(timeError)

      if (trainer.approvalNeeded?.sessionTime) {
        outcome = 'requested'
        const requestId = messageId('session-time-owner')
        db.messages.push({
          id: requestId,
          createdAt: new Date().toISOString(),
          recipientRole: 'owner',
          sessionId: session.id,
          clientId: session.clientId,
          trainerId: trainer.id,
          title: `Session time change: ${client?.name ?? session.id}`,
          body: `${trainer.name} requested a session time change from ${previous.date} ${previous.from}–${previous.to} to ${next.date} ${next.from}–${next.to}.`,
          kind: 'session_time_request',
          status: 'pending',
          read: false,
          request: { type: 'session_time', sessionId, trainerId: trainer.id, previous, next },
        })
        db.messages.push({
          id: messageId('session-time-trainer'),
          requestId,
          createdAt: new Date().toISOString(),
          recipientTrainerId: trainer.id,
          sessionId: session.id,
          clientId: session.clientId,
          trainerId: trainer.id,
          title: `Time-change request sent: ${client?.name ?? session.id}`,
          body: 'The session remains unchanged until the owner approves the request.',
          kind: 'session_time_request',
          status: 'pending',
          read: false,
        })
        return
      }

      Object.assign(session, next, { detailsUpdatedAt: new Date().toISOString() })
      if (session.outcome) session.outcome.durationMinutes = sessionDurationMinutes(session)
      db.messages.push({
        id: messageId('session-time-direct'),
        createdAt: new Date().toISOString(),
        recipientRole: 'owner',
        sessionId: session.id,
        clientId: session.clientId,
        trainerId: trainer.id,
        title: `Session time updated: ${client?.name ?? session.id}`,
        body: `${trainer.name} updated the session directly from ${previous.date} ${previous.from}–${previous.to} to ${next.date} ${next.from}–${next.to}.`,
        kind: 'session_time_update',
        read: false,
      })
    })

    return { outcome, session: state.sessions.find(item => item.id === sessionId) }
  },

  async requestTrainerChange(sessionId, actor, replacementTrainerId) {
    await delay()
    let outcome = 'applied'

    const state = mockDb.mutate(db => {
      const session = requireEditableSession(db, sessionId)
      const trainer = requireAssignedTrainer(db, session, actor)
      const replacement = db.trainers.find(item => item.id === replacementTrainerId && item.status !== 'inactive')
      const client = db.clients.find(item => item.id === session.clientId)
      if (!replacement || replacement.id === trainer.id) throw new Error('Choose another active trainer.')

      if (trainer.approvalNeeded?.trainerReassignment) {
        outcome = 'requested'
        const requestId = messageId('session-trainer-owner')
        db.messages.push({
          id: requestId,
          createdAt: new Date().toISOString(),
          recipientRole: 'owner',
          sessionId: session.id,
          clientId: session.clientId,
          trainerIds: [trainer.id, replacement.id],
          title: `Trainer-change request: ${client?.name ?? session.id}`,
          body: `${trainer.name} requested that ${replacement.name} take the session on ${session.date} at ${session.from}.`,
          kind: 'session_trainer_request',
          status: 'pending',
          read: false,
          request: {
            type: 'session_trainer',
            sessionId,
            trainerId: trainer.id,
            previousTrainerId: trainer.id,
            previous: scheduleSnapshot(session),
            replacementTrainerId: replacement.id,
          },
        })
        db.messages.push({
          id: messageId('session-trainer-requester'),
          requestId,
          createdAt: new Date().toISOString(),
          recipientTrainerId: trainer.id,
          sessionId: session.id,
          clientId: session.clientId,
          trainerIds: [trainer.id, replacement.id],
          title: `Trainer-change request sent: ${client?.name ?? session.id}`,
          body: 'The assigned trainer remains unchanged until the owner approves the request.',
          kind: 'session_trainer_request',
          status: 'pending',
          read: false,
        })
        return
      }

      session.trainerId = replacement.id
      session.detailsUpdatedAt = new Date().toISOString()
      db.messages.push({
        id: messageId('session-trainer-direct'),
        createdAt: new Date().toISOString(),
        recipientRole: 'owner',
        sessionId: session.id,
        clientId: session.clientId,
        trainerIds: [trainer.id, replacement.id],
        title: `Session trainer updated: ${client?.name ?? session.id}`,
        body: `${trainer.name} changed the assigned trainer directly to ${replacement.name}.`,
        kind: 'session_trainer_update',
        read: false,
      })
    })

    return { outcome, session: state.sessions.find(item => item.id === sessionId) }
  },

  async saveExercisePlan(sessionId, items) {
    await delay()
    const validation = validateExercisePlan(items)
    if (validation) throw new Error(validation)

    const state = mockDb.mutate(db => {
      const session = requireEditableSession(db, sessionId)
      session.exercisePlan = normalizeExercisePlan(items)
      if (session.status !== 'completed') session.status = 'planned'
      session.planUpdatedAt = new Date().toISOString()
      appendSessionEdit(db, session, 'Exercise plan saved', `${session.exercisePlan.length} exercise${session.exercisePlan.length === 1 ? '' : 's'} saved.`)
    })

    return state.sessions.find(session => session.id === sessionId)
  },

  previousPlanFor(sessionId) {
    const db = mockDb.read()
    const session = requireSession(db, sessionId)
    return clone(previousPlan(db, session)?.exercisePlan ?? [])
  },

  async copyPreviousPlan(sessionId) {
    await delay()

    const state = mockDb.mutate(db => {
      const session = requireEditableSession(db, sessionId)
      const source = previousPlan(db, session)
      if (!source) throw new Error('No previous exercise plan is available.')

      session.exercisePlan = clone(source.exercisePlan).map((item, index) => ({
        ...item,
        id: `exercise-${session.id}-copy-${index + 1}`,
      }))
      if (session.status !== 'completed') session.status = 'planned'
      session.planUpdatedAt = new Date().toISOString()
      session.copiedFromSessionId = source.id
      appendSessionEdit(db, session, 'Exercise plan saved', `Copied ${session.exercisePlan.length} exercise${session.exercisePlan.length === 1 ? '' : 's'} from the previous session.`)
    })

    return state.sessions.find(session => session.id === sessionId)
  },

  async saveOutcome(sessionId, outcome) {
    await delay()

    const state = mockDb.mutate(db => {
      const session = requireSession(db, sessionId)
      requireActiveSessionClient(db.clients.find(item => item.id === session.clientId), session)
      session.outcome = {
        durationMinutes: sessionDurationMinutes(session),
        trainerComments: outcome.trainerComments?.trim() ?? '',
      }
      if (outcome.exerciseResults) session.exerciseResults = validateExerciseResults(outcome.exerciseResults)
      updateClientProgress(db, session.clientId)
      appendSessionEdit(db, session, 'Session outcome saved', `${session.outcome.durationMinutes} minutes recorded.`)
    })

    return state.sessions.find(session => session.id === sessionId)
  },

  async saveClientSummary(sessionId, summary) {
    await delay()

    const state = mockDb.mutate(db => {
      const session = requireSession(db, sessionId)
      requireActiveSessionClient(db.clients.find(item => item.id === session.clientId), session)
      session.clientSummary = summary.trim()
      appendSessionEdit(db, session, 'Client-facing summary saved', 'The client-facing session summary was updated.')
    })

    return state.sessions.find(session => session.id === sessionId)
  },

  async markWhatsAppOpened(sessionId) {
    await delay(20)

    const state = mockDb.mutate(db => {
      const session = requireSession(db, sessionId)
      requireActiveSessionClient(db.clients.find(item => item.id === session.clientId), session)
      requireTrainingDate(db, session)
      session.whatsappOpenedAt = new Date().toISOString()
      session.whatsappOpenCount = (session.whatsappOpenCount ?? 0) + 1
    })

    return state.sessions.find(session => session.id === sessionId)
  },

  async acknowledge(sessionId, acknowledgement, actor) {
    await delay()

    if (!['signature', 'late_no_show'].includes(acknowledgement.method)) {
      throw new Error('Choose a valid acknowledgement method.')
    }
    if (acknowledgement.method === 'signature' && !acknowledgement.signerName?.trim()) {
      throw new Error('Enter the client or representative name.')
    }

    if (acknowledgement.method === 'signature' && !validSignature(acknowledgement.signature)) throw new Error('Draw the client signature before completing the session.')

    const input = acknowledgementInput(acknowledgement)
    const current = mockDb.read()
    const existing = requireSession(current, sessionId)
    requireActiveSessionClient(current.clients.find(item => item.id === existing.clientId), existing)
    requireAcknowledgementActor(current, existing, actor)
    requireTrainingDate(current, existing)
    if (acknowledgementUnchanged(existing.acknowledgement, input)) {
      return { session: existing, transactions: (current.packageCreditTransactions ?? []).filter(item => item.sessionId === sessionId) }
    }
    requireAcknowledgementTransition(existing.acknowledgement, input)

    const state = mockDb.mutate(db => {
      const session = requireSession(db, sessionId)
      requireActiveSessionClient(db.clients.find(item => item.id === session.clientId), session)
      const recordedBy = requireAcknowledgementActor(db, session, actor)
      requireAcknowledgementTransition(session.acknowledgement, input)
      const client = db.clients.find(item => item.id === session.clientId)
      requireTrainingDate(db, session)
      if (!client) throw new Error('Session client not found.')
      ensureClientPackageReferences(db, client)
      const purchasedPackage = packageForRecord(client, session)
      if (!purchasedPackage) throw new Error('This session needs a package assignment before completion.')

      db.packageCreditTransactions ??= []
      const alreadyDebited = hasSessionDebit(db.packageCreditTransactions, session.id)

      if (!alreadyDebited) {
        db.packageCreditTransactions.push({
          id: `credit-${session.id}`,
          type: 'session_debit',
          sessionId: session.id,
          clientId: client.id,
          packageId: purchasedPackage.id,
          amount: -1,
          createdAt: new Date().toISOString(),
        })

        purchasedPackage.used = Math.min(purchasedPackage.total, purchasedPackage.used + 1)
        if (purchasedPackage.id === client.package.id) appendRenewalMessage(db, client)
      }

      session.status = 'completed'
      if (acknowledgement.method === 'signature' && !session.exerciseResults) {
        session.exerciseResults = validateExerciseResults(exerciseResultsFor(session))
      }
      const previous = session.acknowledgement
      const entry = { ...structuredClone(input), recordedAt: new Date().toISOString(), recordedBy }
      session.acknowledgementHistory = [...(session.acknowledgementHistory ?? (previous ? [structuredClone(previous)] : [])), entry]
      session.acknowledgement = structuredClone(entry)
      updateClientProgress(db, session.clientId)
      appendSessionEdit(db, session, 'Session acknowledgement saved', acknowledgement.method === 'signature'
        ? `Acknowledged by ${acknowledgement.signerName.trim()}.`
        : 'Late / no-show acknowledgement recorded.')
    })

    return {
      session: state.sessions.find(session => session.id === sessionId),
      transactions: state.packageCreditTransactions.filter(item => item.sessionId === sessionId),
    }
  },
}
