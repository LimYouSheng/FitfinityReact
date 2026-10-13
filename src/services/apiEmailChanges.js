import { ApiError } from './apiClient.js'
import { reconciledCommand } from './apiCommand.js'

const uuid = value => typeof value === 'string' && /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(value)
export function emailChangeState(value) {
  if (!value || !uuid(value.id) || typeof value.email !== 'string' || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.email) || !['requested', 'sending', 'pending', 'verifying', 'completed'].includes(value.state) || typeof value.signedOut !== 'boolean' || (value.signedOut && value.state !== 'completed') || Object.keys(value).some(key => !['id', 'email', 'state', 'signedOut'].includes(key))) throw new ApiError('API_RESPONSE', 'The email verification state could not be verified. Check its status before continuing.')
  return value
}

export function emailCommands(http, actionSession) {
  const request = reconciledCommand(http, actionSession, {
    label: 'Trainer email', path: input => `/api/trainers/${input.id}/email-change`, receiptPath: '/api/trainer-email-requests',
    bodyFor: ({ id: _id, ...body }) => body,
    validate(value, input) {
      const state = emailChangeState(value)
      if (state.email !== input.email) throw new ApiError('API_RESPONSE', 'The pending email does not match this request.')
      return state
    },
  })
  const checkedId = id => {
    if (!uuid(id)) throw new ApiError('INVALID_REQUEST', 'Reload the email verification request.')
    return id
  }
  const pending = async (input, generation, trainer = false) => {
    const { sessionGeneration } = await actionSession(generation)
    const response = await http.get(trainer ? `/api/trainers/${checkedId(input.id)}/email-change` : '/auth/email-change', { expectedGeneration: sessionGeneration })
    if (!response || Object.keys(response).length !== 1 || !Object.hasOwn(response, 'change')) throw new ApiError('API_RESPONSE', 'The pending email could not be loaded.')
    return response.change === null ? null : emailChangeState(response.change)
  }
  const act = async (action, input, generation) => {
    const id = checkedId(input.id)
    if (action === 'verify' && !/^[0-9]{6}$/.test(input.code)) throw new ApiError('INVALID_CODE', 'Enter the six-digit verification code.')
    const { sessionGeneration } = await actionSession(generation)
    return http.post(`/auth/email-change/${id}/${action}`, action === 'verify' ? { code: input.code } : {}, {
      csrf: true, expectedGeneration: sessionGeneration,
      accept(value) {
        const state = emailChangeState(value)
        if (state.id !== id) throw new ApiError('API_RESPONSE', 'The email verification request changed.')
        if (state.signedOut) http.clear()
        return state
      },
    })
  }
  return {
    request({ id, patch, expectedVersion }, generation) {
      if (!patch || Object.keys(patch).length !== 1 || typeof patch.email !== 'string' || !Number.isSafeInteger(expectedVersion) || expectedVersion < 1) throw new ApiError('INVALID_REQUEST', 'Review the new email and reload the trainer before saving.')
      const email = patch.email.trim().toLowerCase()
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) throw new ApiError('INVALID_REQUEST', 'Enter a valid email address.')
      return request({ id: checkedId(id), email, expectedVersion }, generation)
    },
    pendingEmailChange: (input, generation) => pending(input, generation),
    pendingTrainerEmailChange: (input, generation) => pending(input, generation, true),
    sendEmailCode: (input, generation) => act('send', input, generation),
    verifyEmailChange: (input, generation) => act('verify', input, generation),
    reconcileEmailChange: (input, generation) => act('reconcile', input, generation),
  }
}
