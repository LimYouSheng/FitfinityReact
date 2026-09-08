import { mockDb, delay } from './mockDb.js'
import { mockAccountPassword, mockPolicy } from '../data/mockPolicy.js'

export const MOCK_SESSION_KEY = 'fitfinity-demo-session-v1'
const CREDENTIALS_KEY = 'fitfinity-demo-credentials-v1'
const read = key => { try { const value = localStorage.getItem(key); return value ? JSON.parse(value) : null } catch { return null } }
const saveSession = userId => localStorage.setItem(MOCK_SESSION_KEY, JSON.stringify({ userId, expiresAt: userId ? Date.now() + mockDb.read().settings.sessionHours * 3600000 : null }))
const active = user => user && (user.status ?? 'active') === 'active'
const denied = () => Object.assign(new Error('Your session has ended. Sign in again.'), { code: 'SESSION_EXPIRED' })

async function digest(password, salt) {
  if (!globalThis.crypto?.subtle) throw new Error('Open the portal over HTTPS or localhost to use account passwords.')
  const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(password), 'PBKDF2', false, ['deriveBits'])
  const bits = await crypto.subtle.deriveBits({ name: 'PBKDF2', salt: new TextEncoder().encode(salt), iterations: 100000, hash: 'SHA-256' }, key, 256)
  return Array.from(new Uint8Array(bits), byte => byte.toString(16).padStart(2, '0')).join('')
}

async function matches(userId, password) {
  const record = (read(CREDENTIALS_KEY) ?? {})[userId]
  return record ? record.hash === await digest(password, record.salt) : password === mockAccountPassword
}

export const authService = {
  current() {
    const session = read(MOCK_SESSION_KEY)
    if (!session?.userId || (!Number.isFinite(session.expiresAt) || session.expiresAt <= Date.now())) return null
    const user = mockDb.read().users.find(item => item.id === session.userId)
    return active(user) ? user : null
  },
  requireCurrent() { const user = this.current(); if (!user) throw denied(); return user },
  async signIn({ identifier, password }) {
    await delay()
    const user = mockDb.read().users.find(item => item.id === identifier || item.email?.toLowerCase() === identifier.trim().toLowerCase())
    if (!active(user) || !await matches(user.id, password)) throw new Error('The account or password is incorrect, or the account is inactive.')
    saveSession(user.id)
    return user
  },
  async signOut() { saveSession(null) },
  async switchDemoIdentity(id) {
    this.requireCurrent()
    const user = mockDb.read().users.find(item => item.id === id)
    if (!active(user)) throw new Error('Choose an active demo account.')
    saveSession(user.id)
    return user
  },
  async changePassword({ currentPassword, newPassword, confirmation }) {
    const user = this.requireCurrent()
    const policy = mockDb.read().settings?.password ?? mockPolicy.password
    if (newPassword.length < policy.minimumLength || newPassword.length > policy.maximumLength) throw new Error(`Use ${policy.minimumLength}–${policy.maximumLength} characters for the new password.`)
    if (newPassword !== confirmation) throw new Error('The new passwords do not match.')
    if (newPassword === currentPassword) throw new Error('Choose a different new password.')
    if (!await matches(user.id, currentPassword)) throw new Error('The current password is incorrect.')
    const salt = Array.from(crypto.getRandomValues(new Uint8Array(16)), byte => byte.toString(16).padStart(2, '0')).join('')
    const record = { salt, hash: await digest(newPassword, salt) }
    if (this.requireCurrent().id !== user.id) throw denied()
    localStorage.setItem(CREDENTIALS_KEY, JSON.stringify({ ...(read(CREDENTIALS_KEY) ?? {}), [user.id]: record }))
    return { changed: true }
  },
}
