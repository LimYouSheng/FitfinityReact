import { test as base, expect } from '@playwright/test'
export { expect }
export const test = base.extend({
  extraHTTPHeaders: async ({ extraHTTPHeaders }, use, info) => {
    await use({ ...extraHTTPHeaders, 'X-Fitfinity-Browser-Worker': String(info.workerIndex) })
  },
})

/** Fresh authentication context, retaining this worker's isolated real database. */
export function freshContext(browser, page) {
  return browser.newContext({ baseURL: new URL(page.url()).origin,
    extraHTTPHeaders: { 'X-Fitfinity-Browser-Worker': String(test.info().workerIndex) } })
}

export async function signIn(page, role = 'owner', email = `${role}@example.test`) {
  await page.goto('/')
  await page.getByLabel('Email', { exact: true }).fill(email)
  await page.getByLabel('Password', { exact: true }).fill('browser-test-password-only')
  const login = page.waitForResponse(response => response.url().endsWith('/auth/sign-in'))
  await page.getByRole('button', { name: 'Sign In', exact: true }).click()
  expect((await login).status()).toBe(200)
  // Finish the page's accessible stage-focus transition before entering the code.
  await expect(page.getByRole('heading', { name: 'Authenticator verification', exact: true })).toBeFocused()
  await page.getByLabel('Authenticator code').fill('123456')
  const challenge = page.waitForResponse(response => response.url().endsWith('/auth/challenge'))
  await page.getByRole('button', { name: 'Continue', exact: true }).click()
  expect((await challenge).status()).toBe(200)
  await expect(page.getByRole('heading', { name: `${role[0].toUpperCase()}${role.slice(1)} Dashboard`, exact: true })).toBeVisible()
}

export async function read(page, path) {
  const response = await page.request.get(path)
  expect(response.status()).toBe(200)
  return response.json()
}

export async function confirm(page, action) {
  await page.getByRole('button', { name: action, exact: true }).click()
  await page.getByRole('dialog').getByRole('button', { name: action, exact: true }).click()
}

export async function post(page, path, data, key = crypto.randomUUID()) {
  const session = await read(page, '/auth/session')
  return page.request.post(path, { data, headers: {
    Origin: new URL(page.url()).origin,
    'X-CSRF-Token': session.csrfToken,
    'Idempotency-Key': key,
  } })
}

/** Choose a seeded real identity with a scenario-specific authentication budget. */
export function account(scope, role = 'owner') {
  return `${test.info().project.name}-${scope}-${role}@example.test`
}
