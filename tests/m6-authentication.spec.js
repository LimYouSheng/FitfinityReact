import { expect, passwordSignIn, test, verifyAuthenticator } from './auth-api-fixture.js'

test('completed MFA loads independently of a pending anonymous account read', async ({ page, staffApi }) => {
  staffApi.state.step = 'SOFTWARE_TOKEN_MFA'
  await page.goto(staffApi.origin)
  await passwordSignIn(page)
  await expect(page.getByLabel('Authenticator code')).toBeVisible()
  const held = staffApi.holdNextAnonymousSession()
  try {
    await page.evaluate(() => window.dispatchEvent(new Event('focus')))
    await expect.poll(() => held.request).toEqual({ path: '/me', signedIn: false })
    await verifyAuthenticator(page)
    expect(held.sent).toBe(false)
    const stale = page.waitForResponse(response => response.url().endsWith('/me') && response.status() === 401)
    held.release()
    await stale
    await expect.poll(() => held.sent).toBe(true)
    await expect(page.getByRole('heading', { name: 'Your account', exact: true })).toBeVisible()
    expect(staffApi.state.mutations.filter(row => row.path === '/auth/challenge')).toHaveLength(1)
    await page.reload()
    await expect(page.getByRole('heading', { name: 'Your account', exact: true })).toBeVisible()
    expect(staffApi.state.refreshes).toBe(0)
  } finally { held.release() }
})

test('real-mode temporary password, MFA enrollment, account reload and cookie logout', async ({ page, context, staffApi }) => {
  await page.goto(staffApi.origin)
  await passwordSignIn(page)
  await expect(page.getByRole('heading', { name: 'Choose a new password' })).toBeVisible()
  await page.getByLabel('New password', { exact: true }).fill('long-lowercase-passphrase')
  await page.getByLabel('Confirm new password').fill('long-lowercase-passphrase')
  await page.getByRole('button', { name: 'Continue', exact: true }).click()
  await expect(page.getByLabel('Authenticator setup key')).toHaveText('ABCDEFGHIJKLMNOP234567')
  await page.getByLabel('Authenticator code').fill('000000')
  await page.getByRole('button', { name: 'Continue', exact: true }).click()
  await expect(page.getByRole('alert')).toHaveText('The code is incorrect.')
  await verifyAuthenticator(page)
  await expect(page.getByText('owner@example.test', { exact: true })).toBeVisible()
  await expect(page.getByText('Reset Demo', { exact: true })).toHaveCount(0)
  await expect(page.getByLabel('Authenticator setup key')).toHaveCount(0)
  expect(await page.evaluate(() => document.cookie)).not.toContain('staff-session')
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Your account', exact: true })).toBeVisible()
  const logout = page.waitForResponse(response => response.url().endsWith('/auth/sign-out') && response.status() === 200)
  await page.getByRole('button', { name: 'Sign Out', exact: true }).click()
  expect((await logout).headers()['set-cookie']).toBeUndefined()
  expect((await context.cookies(staffApi.origin)).some(cookie => cookie.name === 'staff-session' && cookie.httpOnly)).toBe(true)
  await expect(page.getByRole('heading', { name: 'Sign in', exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Sign in', exact: true })).toBeVisible()
  expect(staffApi.state.mutations.at(-1)).toMatchObject({ path: '/auth/sign-out', keys: ['allSessions'], csrf: 'a'.repeat(64) })
})

test('verified-email recovery and authenticated password change return to sign-in', async ({ page, staffApi }) => {
  staffApi.state.step = 'SOFTWARE_TOKEN_MFA'
  await page.goto(staffApi.origin)
  await page.getByLabel('Email', { exact: true }).fill('owner@example.test')
  await page.getByRole('button', { name: 'Forgot password?' }).click()
  await page.getByRole('button', { name: 'Send recovery code' }).click()
  await page.getByLabel('Recovery code').fill('123456')
  await page.getByLabel('New password', { exact: true }).fill('recovered-passphrase')
  await page.getByLabel('Confirm new password').fill('recovered-passphrase')
  await page.getByRole('button', { name: 'Reset Password', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('Password reset')
  await passwordSignIn(page)
  await verifyAuthenticator(page)
  await page.getByRole('button', { name: 'Change Password', exact: true }).click()
  await page.getByLabel('Current password').fill('recovered-passphrase')
  await page.getByLabel('New password', { exact: true }).fill('replacement-passphrase')
  await page.getByLabel('Confirm new password').fill('replacement-passphrase')
  await page.getByRole('button', { name: 'Save Password' }).click()
  const confirmation = page.getByRole('dialog')
  await expect(confirmation).toContainText('signs out all sessions')
  await confirmation.getByRole('button', { name: 'Change Password', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Sign in', exact: true })).toBeVisible()
  expect(staffApi.state.mutations.at(-1)).toMatchObject({ path: '/auth/change-password', keys: ['currentPassword', 'newPassword'], csrf: 'a'.repeat(64) })
})

test('expired-access reload recovers CSRF; private responses stay out of storage and failures show no demo', async ({ page, staffApi }) => {
  staffApi.state.step = 'SOFTWARE_TOKEN_MFA'
  await page.goto(staffApi.origin)
  await passwordSignIn(page)
  await verifyAuthenticator(page)
  staffApi.state.accessExpired = true
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Your account', exact: true })).toBeVisible()
  expect(staffApi.state.refreshes).toBe(1)
  await page.evaluate(async () => { await navigator.serviceWorker.ready })
  const persisted = await page.evaluate(async () => ({
    local: JSON.stringify(localStorage), session: JSON.stringify(sessionStorage),
    caches: (await Promise.all((await caches.keys()).map(async name => (await (await caches.open(name)).keys()).map(request => new URL(request.url).pathname)))).flat(),
  }))
  for (const secret of ['initial-password', 'ABCDEFGHIJKLMNOP234567', 'a'.repeat(64), 'owner@example.test']) {
    expect(persisted.local).not.toContain(secret); expect(persisted.session).not.toContain(secret)
  }
  expect(persisted.local).not.toContain('fitfinity-demo')
  expect(persisted.caches.some(path => path.startsWith('/auth/') || path === '/me' || path.startsWith('/api/'))).toBe(false)
  staffApi.state.unavailable = true
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Unable to load the portal' })).toBeVisible()
  await expect(page.getByText('Amanda Lim', { exact: true })).toHaveCount(0)
  await expect(page.getByText('Demo password:', { exact: false })).toHaveCount(0)
  staffApi.state.unavailable = false
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Your account', exact: true })).toBeVisible()
})
