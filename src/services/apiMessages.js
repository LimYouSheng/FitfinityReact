import { validSessionDate } from '../app/sessionRules.js'
import { adminMessageAllowed } from '../app/adminProjection.js'
import { ApiError } from './apiClient.js'
import { reconciledCommand } from './apiCommand.js'

const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
const uuid = value => typeof value === 'string' && /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(value)
const version = value => Number.isSafeInteger(value) && value >= 0
const timestamp = value => typeof value === 'string' && Number.isFinite(Date.parse(value))
const fail = () => { throw new ApiError('API_RESPONSE', 'The personal message could not be verified. Reload before continuing.') }
const clock = value => { if (typeof value !== 'string' || !/^([01]\d|2[0-3]):[0-5]\d(:00)?$/.test(value)) fail(); return value.slice(0, 5) }

export function messageReadState(value, strict = true) {
  if (!value || !uuid(value.id) || !version(value.version) || typeof value.read !== 'boolean'
    || (value.read ? !timestamp(value.readAt) || value.version === 0 : value.readAt !== null)
    || (strict && Object.keys(value).some(key => !['id', 'version', 'read', 'readAt'].includes(key)))) fail()
  return { id: value.id, version: value.version, read: value.read, readAt: value.readAt }
}

function proposal(value) {
  if (!value || !uuid(value.id) || !uuid(value.trainer_id) || !version(value.version) || !value.version
    || !version(value.expected_version) || !value.expected_version
    || !['session_time', 'session_trainer', 'fixed_weekly_schedule', 'trainer_availability'].includes(value.kind)
    || !['pending', 'approved', 'rejected', 'cancelled', 'superseded'].includes(value.status)
    || !['client_id', 'purchase_id', 'session_id', 'replacement_trainer_id'].every(key => value[key] === null || uuid(value[key]))
    || typeof value.resolution_note !== 'string' || (value.status === 'pending' ? value.resolved_at !== null : !timestamp(value.resolved_at))
    || Object.keys(value).some(key => !['id', 'version', 'kind', 'status', 'trainer_id', 'client_id', 'purchase_id', 'session_id', 'expected_version', 'replacement_trainer_id', 'old_date', 'old_start', 'old_end', 'new_date', 'new_start', 'new_end', 'resolved_at', 'resolution_note', 'slots'].includes(key))
    || !Array.isArray(value.slots)) fail()
  const slots = value.slots.map(slot => {
    if (!slot || Object.keys(slot).some(key => !['side', 'slot_identity', 'weekday', 'starts_at', 'ends_at'].includes(key)) || !['old', 'new'].includes(slot.side) || !uuid(slot.slot_identity) || !Number.isInteger(slot.weekday) || !days[slot.weekday]) fail()
    const from = clock(slot.starts_at), to = clock(slot.ends_at)
    if (from >= to) fail()
    return { side: slot.side, id: slot.slot_identity, day: days[slot.weekday], from, to }
  })
  const result = { type: value.kind, trainerId: value.trainer_id, clientId: value.client_id, clientPackageId: value.purchase_id, sessionId: value.session_id }
  if (value.kind === 'trainer_availability') {
    for (const [side, field] of [['old', 'oldAvailability'], ['new', 'newAvailability']]) result[field] = Object.fromEntries(days.map(day => [day, slots.filter(slot => slot.side === side && slot.day === day).map(slot => [slot.from, slot.to])]))
  } else if (value.kind === 'fixed_weekly_schedule') {
    if (!value.client_id || !value.purchase_id) fail()
    result.oldSlots = slots.filter(slot => slot.side === 'old')
    result.newSlots = slots.filter(slot => slot.side === 'new')
    if (!result.oldSlots.length || result.oldSlots.length !== result.newSlots.length) fail()
  } else {
    if (!value.session_id || !value.client_id || !value.purchase_id) fail()
    if (value.kind === 'session_time') {
      if (!validSessionDate(value.old_date) || !validSessionDate(value.new_date)) fail()
      result.previous = { date: value.old_date, from: clock(value.old_start), to: clock(value.old_end) }
      result.next = { date: value.new_date, from: clock(value.new_start), to: clock(value.new_end) }
      if (result.previous.from >= result.previous.to || result.next.from >= result.next.to) fail()
    } else {
      if (!value.replacement_trainer_id || value.replacement_trainer_id === value.trainer_id) fail()
      result.previousTrainerId = value.trainer_id
      result.replacementTrainerId = value.replacement_trainer_id
    }
  }
  return result
}

export function personalMessage(value, user) {
  const state = messageReadState(value, false)
  const links = ['clientId', 'purchaseId', 'sessionId', 'trainerId', 'requestId', 'exerciseId', 'packageId', 'contentId']
  const keys = ['id', 'version', 'read', 'readAt', 'recipientUserId', 'kind', 'title', 'body', 'createdAt', 'actorId', 'actorName', ...links, 'remunerationCycle', 'request', 'renewalStatus']
  if (Object.keys(value).some(key => !keys.includes(key)) || value.recipientUserId !== user.id
    || !uuid(value.actorId) || !['kind', 'title', 'actorName'].every(key => typeof value[key] === 'string' && value[key].trim())
    || typeof value.body !== 'string' || !timestamp(value.createdAt) || !links.every(key => value[key] === null || uuid(value[key]))
    || (value.remunerationCycle !== null && !/^\d{4}-(0[1-9]|1[0-2])$/.test(value.remunerationCycle))
    || (value.kind === 'renewal' ? !['active', 'renewed'].includes(value.renewalStatus) : value.renewalStatus !== null)
    || (user.role === 'admin' && !adminMessageAllowed(value))) fail()
  if (value.requestId ? value.request?.id !== value.requestId : value.request !== null) fail()
  return { ...value, ...state, ...(value.request ? { request: proposal(value.request), status: value.request.status } : {}) }
}

export function messageCommands(http, actionSession) {
  const save = reconciledCommand(http, actionSession, {
    label: 'Message read state', roles: ['owner', 'admin', 'trainer'],
    path: input => `/api/messages/${input.id}/read-state`, receiptPath: '/api/message-read-saves',
    bodyFor: ({ expectedVersion, read }) => ({ expectedVersion, read }),
    validate(value, input) {
      const result = messageReadState(value)
      if (result.id !== input.id || result.version !== input.expectedVersion + 1 || result.read !== input.read) fail()
      return result
    },
  })
  return {
    save({ id, expectedVersion }, read, generation) {
      if (!uuid(id) || !version(expectedVersion)) throw new ApiError('INVALID_REQUEST', 'Reload the message before changing its read state.')
      return save({ id, expectedVersion, read }, generation)
    },
    async read(generation) {
      const session = await actionSession(generation)
      if (save.pendingInput(session.sessionGeneration)) await save.reconcile(session.sessionGeneration)
      const value = await http.get('/api/messages', { expectedGeneration: session.sessionGeneration })
      if (!Array.isArray(value) || value.length > 2000) fail()
      const messages = value.map(row => personalMessage(row, session.user))
      if (new Set(messages.map(row => row.id)).size !== messages.length) fail()
      return { messages, pending: save.pendingInput(session.sessionGeneration) }
    },
  }
}
