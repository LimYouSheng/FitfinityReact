import { test, expect } from '@playwright/test'
export { test, expect }

export async function signIn(page, role = 'owner') {
  await page.goto('/')
  await page.getByLabel('Email', { exact: true }).fill(`${role}@example.test`)
  await page.getByLabel('Password', { exact: true }).fill('browser-test-password-only')
  await page.getByRole('button', { name: 'Sign In', exact: true }).click()
  await page.getByLabel('Authenticator code').fill('123456')
  await page.getByRole('button', { name: 'Continue', exact: true }).click()
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
