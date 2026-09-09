import { requestTypes } from '../app/requestTypes.js'
import { applyWeeklySchedule, availabilityBlocks, businessNow, sameAvailability, sameSlots, sessionTimeChangeError, validateAvailability } from '../app/scheduleChanges.js'
import { delay, mockDb } from './mockDb.js'

const snapshot = session => ({ date: session.date, from: session.from, to: session.to })

export const requestService = {
  async resolve(messageId, decision, actor) {
    await delay(120)
    if (!['approved', 'rejected'].includes(decision)) throw new Error('Choose approve or reject.')
    return mockDb.mutate(db => {
      const owner = db.users.find(user => user.id === actor?.id)
      if (actor?.role !== 'owner' || owner?.role !== 'owner' || (owner.status ?? 'active') !== 'active') {
        throw new Error('Only an active owner can decide requests.')
      }
      const message = db.messages.find(item => item.id === messageId)
      const request = message?.request
      if (!request || !requestTypes.includes(request.type) || message.recipientRole !== 'owner') {
        throw new Error('Request not found.')
      }
      if (message.status !== 'pending') throw new Error('This request has already been decided.')
      const session = db.sessions.find(item => item.id === request.sessionId)
      if (decision === 'approved' && request.type === 'fixed_weekly_schedule') {
        const client = db.clients.find(item => item.id === request.clientId)
        if (!client || client.trainerId !== request.trainerId || !sameSlots(client.fixedWeeklySchedule, request.oldSlots)) {
          throw new Error('The client assignment or weekly schedule changed after this request. Reject it and request the updated change.')
        }
        message.updatedSessions = applyWeeklySchedule(db, client, request.newSlots)
      } else if (decision === 'approved' && request.type === 'trainer_availability') {
        const trainer = db.trainers.find(item => item.id === request.trainerId)
        if (trainer?.status !== 'active') throw new Error('The trainer is no longer active.')
        if (!sameAvailability(trainer.availability, request.oldAvailability)) throw new Error('Availability changed after this request. Reject it and submit a new request.')
        trainer.availability = validateAvailability(availabilityBlocks(request.newAvailability))
      } else if (decision === 'approved') {
        const requester = db.trainers.find(item => item.id === request.trainerId)
        const client = db.clients.find(item => item.id === session?.clientId)
        if (!session || ['completed', 'cancelled'].includes(session.status) || client?.status !== 'active' || requester?.status !== 'active') {
          throw new Error('The session, client or requesting trainer is no longer eligible. Reject this request.')
        }
        if (session.trainerId !== request.trainerId || (request.previous && Object.keys(snapshot(session)).some(key => session[key] !== request.previous[key]))) {
          throw new Error('The session changed after this request. Reject it and request the updated change.')
        }
        if (request.type === 'session_time') {
          const next = request.next
          if (!next || !/^\d{4}-\d{2}-\d{2}$/.test(next.date) || !/^([01]\d|2[0-3]):[0-5]\d$/.test(next.from) || !/^([01]\d|2[0-3]):[0-5]\d$/.test(next.to) || next.from >= next.to) {
            throw new Error('The requested date or time is invalid.')
          }
          const timeError = sessionTimeChangeError(session, next, businessNow(new Date(), db.settings.timeZone))
          if (timeError) throw new Error(`${timeError} Reject this request.`)
          Object.assign(session, { date: next.date, from: next.from, to: next.to })
        } else {
          const replacement = db.trainers.find(item => item.id === request.replacementTrainerId && item.status === 'active')
          if (!replacement || replacement.id === session.trainerId) throw new Error('The replacement trainer is no longer eligible.')
          session.trainerId = replacement.id
        }
        if (db.sessions.some(other => other.id !== session.id && !['completed', 'cancelled'].includes(other.status) && other.date === session.date && (other.trainerId === session.trainerId || other.clientId === session.clientId) && other.from < session.to && session.from < other.to)) {
          throw new Error('The requested change conflicts with another session. Reject it and request another slot.')
        }
        session.detailsUpdatedAt = new Date().toISOString()
      }
      const decidedAt = new Date().toISOString()
      Object.assign(message, { status: decision, decidedAt, decidedBy: owner.id })
      for (const receipt of db.messages.filter(item => item.requestId === message.id)) {
        Object.assign(receipt, { status: decision, decidedAt, decidedBy: owner.id })
      }
      const recipients = new Set([request.trainerId])
      if (decision === 'approved' && request.type === 'session_trainer') recipients.add(request.replacementTrainerId)
      const subject = request.type === 'trainer_availability' ? 'approved availability' : request.type === 'fixed_weekly_schedule' ? 'weekly schedule and eligible future sessions' : 'session'
      for (const trainerId of recipients) {
        db.messages.push({
          id: `decision-${message.id}-${trainerId}`, recipientTrainerId: trainerId,
          sessionId: request.sessionId, clientId: message.clientId, trainerId,
          title: `Request ${decision}: ${message.title}`,
          body: decision === 'approved' ? `The owner approved the request and updated the ${subject}.` : 'The owner rejected the request. No scheduling or availability data was changed.',
          kind: 'request_decision', status: decision, createdAt: decidedAt, read: false, requestId: message.id,
        })
      }
    })
  },
}
