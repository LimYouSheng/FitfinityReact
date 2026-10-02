import { emptyDirectory } from '../src/test/directory.js'
// Controlled HTTP boundary for browser transport/UI coverage; not live Cognito acceptance.
import { createServer } from 'node:http'
import { readFile } from 'node:fs/promises'
import { extname, resolve } from 'node:path'
import { test as base, expect } from './fixtures.js'
import { authPolicy, challenge, csrfToken, sessionInfo } from '../src/test/api.js'

export { expect }
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.png': 'image/png', '.jpg': 'image/jpeg', '.webmanifest': 'application/manifest+json' }
export const test = base.extend({
  demoSignedIn: false,
  staffApi: async ({}, use) => {
    const directory = resolve('dist-api-test')
    const state = { csrfToken, signedIn: false, step: 'NEW_PASSWORD_REQUIRED', flow: false, accessExpired: false, unavailable: false, refreshes: 0, mutations: [], directory: emptyDirectory(), user: sessionInfo().user, adminAccounts: new Map(), adminCreateFailure: false }
    const currentSession = () => ({ ...sessionInfo(), user: state.user, csrfToken: state.csrfToken })
    let nextAdminExpiry = null
    const heldAdminExpiries = new Set()
    let nextAnonymousSession = null
    const heldAnonymousSessions = new Set()
    const holdNextAnonymousSession = () => {
      if (nextAnonymousSession) throw new Error('An anonymous session read is already queued.')
      const held = { request: null, sent: false }
      held.pending = new Promise(resolveRelease => { held.release = resolveRelease })
      nextAnonymousSession = held
      heldAnonymousSessions.add(held)
      return held
    }
    const holdNextAdminExpiry = () => {
      if (nextAdminExpiry) throw new Error('An Admin expiry is already queued.')
      const held = { request: null, sent: false }
      held.pending = new Promise(resolveRelease => { held.release = resolveRelease })
      nextAdminExpiry = held
      heldAdminExpiries.add(held)
      return held
    }
    const server = createServer(async (request, response) => {
      const path = new URL(request.url, 'http://localhost').pathname
      response.setHeader('Cache-Control', 'no-store')
      const json = (value, status = 200) => { response.writeHead(status, { 'Content-Type': 'application/json' }); response.end(JSON.stringify(value)) }
      const error = (code, status = 401) => json({ error: { code, message: code === 'AUTH_FAILED' ? 'The code is incorrect.' : 'Staff service unavailable. Please retry.', requestId: 'browser-fixture' } }, status)
      try {
        if (path.startsWith('/auth/') || path === '/me' || path.startsWith('/api/')) {
          if (state.unavailable) { error('service_unavailable', 503); return }
          if (request.method === 'GET') {
            if (path === '/auth/policy') { json(authPolicy); return }
            if (!state.signedIn || !request.headers.cookie?.includes('staff-session=browser-test')) {
              if (path === '/me' && nextAnonymousSession) {
                const held = nextAnonymousSession
                nextAnonymousSession = null
                held.request = { path, signedIn: false }
                response.once('finish', () => { held.sent = true })
                await held.pending
                heldAnonymousSessions.delete(held)
              }
              if (!response.destroyed) error('SESSION_EXPIRED')
              return
            }
            if (path === '/api/directory') { if (state.accessExpired) error('TOKEN_EXPIRED'); else json(state.directory); return }
            if (path === '/auth/session') { json({ csrfToken: state.csrfToken, expiresAt: sessionInfo().expiresAt }); return }
            if (path === '/me') { if (state.accessExpired) error('TOKEN_EXPIRED'); else json(currentSession()); return }
          }
          if (request.method !== 'POST' || request.headers.origin !== `http://${request.headers.host}` || request.headers['content-type'] !== 'application/json') { error('ORIGIN_REJECTED', 403); return }
          let bytes = ''
          for await (const chunk of request) bytes += chunk
          const body = JSON.parse(bytes)
          state.mutations.push({ path, keys: Object.keys(body), csrf: request.headers['x-csrf-token'] })
          if (path === '/auth/sign-in' || path === '/auth/forgot-password') {
            state.flow = true
            response.setHeader('Set-Cookie', 'staff-flow=browser-test; HttpOnly; SameSite=Lax; Path=/')
            json(path === '/auth/sign-in' ? challenge(state.step) : { message: 'If eligible, check your email.' }); return
          }
          if (path === '/auth/challenge' || path === '/auth/reset-password') {
            if (!state.flow || !request.headers.cookie?.includes('staff-flow=browser-test')) { error('SESSION_EXPIRED'); return }
            if (path === '/auth/reset-password') { state.flow = false; state.signedIn = false; json({ passwordReset: true, signedOut: true }); return }
            if (state.step === 'NEW_PASSWORD_REQUIRED') {
              if (!body.newPassword || /\s/.test(body.newPassword) || body.newPassword.length < 15) { error('PASSWORD_POLICY', 422); return }
              state.step = 'MFA_SETUP'; json(challenge(state.step)); return
            }
            if (body.code !== '123456') { error('AUTH_FAILED'); return }
            state.signedIn = true; state.flow = false; state.accessExpired = false
            response.setHeader('Set-Cookie', 'staff-session=browser-test; HttpOnly; SameSite=Lax; Path=/')
            json(currentSession()); return
          }
          if (!state.signedIn || request.headers['x-csrf-token'] !== state.csrfToken || !request.headers.cookie?.includes('staff-session=browser-test')) { error('CSRF_REJECTED', 403); return }
          if (path === '/api/staff/admins') {
            if (state.user.role !== 'owner') { error('forbidden', 403); return }
            const key = request.headers['idempotency-key']
            state.mutations.at(-1).idempotencyKey = key
            state.mutations.at(-1).body = body
            if (!key || !body.name || !body.email) { error('validation_error', 422); return }
            // Delay the real HTTP reply after normal cookie/CSRF/input checks.
            // Browser interception is unnecessary, including under the active PWA worker.
            if (nextAdminExpiry) {
              const held = nextAdminExpiry
              nextAdminExpiry = null
              held.request = { ...state.mutations.at(-1) }
              response.once('finish', () => { held.sent = true })
              await held.pending
              heldAdminExpiries.delete(held)
              if (!response.destroyed) error('SESSION_EXPIRED')
              return
            }
            let account = state.adminAccounts.get(key)
            if (!account) {
              account = { id: '20000000-0000-4000-8000-000000000001', name: body.name, email: body.email, role: 'admin', invitation: state.adminCreateFailure ? 'unknown' : 'sent' }
              state.adminAccounts.set(key, account)
              if (state.adminCreateFailure) { state.adminCreateFailure = false; error('INVITATION_DELIVERY_UNKNOWN', 503); return }
            }
            json(account); return
          }
          if (path === '/auth/refresh') { state.refreshes++; state.accessExpired = false; json({ refreshed: true, accessExpiresAt: sessionInfo().accessExpiresAt, expiresAt: sessionInfo().expiresAt }); return }
          if (path === '/auth/change-password' || path === '/auth/sign-out') {
            state.signedIn = false
            json({ signedOut: true, ...(path.endsWith('change-password') ? { passwordChanged: true } : {}) }); return
          }
          error('not_found', 404); return
        }
        const file = resolve(directory, path === '/' ? 'index.html' : path.slice(1))
        if (!file.startsWith(`${directory}/`)) { response.writeHead(404).end(); return }
        response.setHeader('Content-Type', mime[extname(file)] ?? 'application/octet-stream')
        response.end(await readFile(file))
      } catch { if (!response.headersSent) error('not_found', 404); else response.end() }
    })
    await new Promise(resolveListening => server.listen(0, '127.0.0.1', resolveListening))
    try { await use({ origin: `http://127.0.0.1:${server.address().port}`, state, holdNextAdminExpiry, holdNextAnonymousSession }) }
    finally {
      for (const held of heldAdminExpiries) held.release()
      for (const held of heldAnonymousSessions) held.release()
      server.closeAllConnections()
      await new Promise(resolveClosed => server.close(resolveClosed))
    }
  },
})

export async function passwordSignIn(page) {
  await page.getByLabel('Email', { exact: true }).fill('owner@example.test')
  await page.getByLabel('Password', { exact: true }).fill('initial-password')
  await page.getByRole('button', { name: 'Sign In', exact: true }).click()
}

export async function verifyAuthenticator(page) {
  await page.getByLabel('Authenticator code').fill('123456')
  await page.getByRole('button', { name: 'Continue', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Your account', exact: true })).toBeVisible()
}
