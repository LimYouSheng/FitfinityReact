export const csrfToken = 'a'.repeat(64)
export const staff = { id: '00000000-0000-4000-8000-000000000001', name: 'Owner', email: 'owner@example.test', role: 'owner', trainerId: null }
export const sessionInfo = () => ({ user: staff, csrfToken, expiresAt: new Date(Date.now() + 3600000).toISOString(), accessExpiresAt: new Date(Date.now() + 300000).toISOString() })
export const authPolicy = { password: { minimumLength: 15, maximumLength: 128, spacesAllowed: false, requiresCharacterMix: false, scheduledRotation: false }, mfa: { required: true, method: 'totp' }, recovery: 'verified_email' }
export const challenge = (step = 'SOFTWARE_TOKEN_MFA') => ({ challenge: step, expiresAt: new Date(Date.now() + 300000).toISOString(), ...(step === 'MFA_SETUP' ? { secretCode: 'ABCDEFGHIJKLMNOP234567' } : {}) })
export const jsonResponse = (data, status = 200) => ({ ok: status < 400, status, headers: new Headers({ 'Content-Type': 'application/json' }), json: async () => data })
export const failure = (code, status = 401) => jsonResponse({ error: { code, message: 'Request failed safely.', requestId: 'request-one' } }, status)
