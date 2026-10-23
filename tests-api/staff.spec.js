import { randomUUID } from 'node:crypto'
import { test, expect, signIn, read, post, account } from './fixtures.js'

for (const role of ['owner', 'admin']) test(`${role} Trainer creation persists profile and invitation receipt without a real provider`, async ({ page }) => {
  await signIn(page, role, account('create', role))
  const name = `Trainer ${randomUUID()}`, email = `${randomUUID()}@example.test`
  await page.goto('/#/trainers/new')
  await page.getByLabel('Trainer name', { exact: true }).fill(name)
  await page.getByLabel('Trainer email', { exact: true }).fill(email)
  await page.getByLabel('Trainer phone number', { exact: true }).fill('91234567')
  await page.getByLabel('Trainer birthday', { exact: true }).fill('1990-01-02')
  await page.getByLabel('Trainer gender', { exact: true }).selectOption('Female')
  await page.getByLabel('Trainer type', { exact: true }).fill('Personal Trainer')
  if (role === 'owner') await page.getByRole('button', { name: 'Continue to Training & Rates', exact: true }).click()
  else await expect(page.getByLabel('Peak session rate', { exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: 'Continue to Trainer Availability', exact: true }).click()
  await page.getByRole('button', { name: 'Monday', exact: true }).click()
  await page.getByRole('button', { name: 'Add Time', exact: true }).click()
  await page.getByRole('button', { name: 'Continue to Owner Approval Needed', exact: true }).click()
  await page.getByRole('button', { name: 'Continue to Review & Confirm', exact: true }).click()
  await page.getByRole('button', { name: 'Create Trainer', exact: true }).click()
  const response = page.waitForResponse(r => r.url().endsWith('/api/staff/trainers') && r.request().method() === 'POST')
  await page.getByRole('dialog', { name: `Create ${name}?`, exact: true }).getByRole('button', { name: 'Create Trainer', exact: true }).click()
  const saved = await response
  expect(saved.status()).toBe(200)
  const result = await saved.json(), key = saved.request().headers()['idempotency-key']
  await expect(page.getByRole('heading', { name, exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name, exact: true })).toBeVisible()
  expect(await read(page, `/api/staff/trainer-creations/${key}`)).toEqual(result)
  const trainer = (await read(page, '/api/directory')).trainers.find(t => t.email === email)
  expect(trainer).toMatchObject({ id: result.id, name, status: 'active' })
  if (role === 'admin') expect(trainer).not.toHaveProperty('peak_rate_cents')
})

test('Owner Admin creation retains one database identity and original receipt after reload', async ({ page }) => {
  await signIn(page, 'owner', account('admincreate'))
  await page.getByRole('button', { name: 'Open profile menu' }).click()
  await page.getByRole('menu', { name: 'Profile menu' }).getByRole('menuitem', { name: 'Create Admin', exact: true }).click()
  const name = `Admin ${randomUUID()}`, email = `${randomUUID()}@example.test`
  await page.getByLabel('Staff name', { exact: true }).fill(name)
  await page.getByLabel('Staff email', { exact: true }).fill(email)
  await page.getByLabel('Staff phone number', { exact: true }).fill('91234567')
  await page.getByLabel('Staff birthday', { exact: true }).fill('1990-01-02')
  await page.getByLabel('Staff gender', { exact: true }).selectOption('Female')
  const response = page.waitForResponse(r => r.url().endsWith('/api/staff/admins') && r.request().method() === 'POST')
  await page.getByRole('dialog', { name: 'Create Admin', exact: true }).getByRole('button', { name: 'Create Admin & Send Invitation', exact: true }).click()
  const saved = await response
  expect(saved.status()).toBe(200)
  const result = await saved.json(), key = saved.request().headers()['idempotency-key'], body = saved.request().postDataJSON()
  expect(result).toMatchObject({ name, email, role: 'admin', invitation: 'sent' })
  await page.getByRole('button', { name: 'Done', exact: true }).click()
  await page.reload()
  const retry = await post(page, '/api/staff/admins', body, key)
  expect(retry.status()).toBe(200)
  expect(await retry.json()).toEqual(result)
  expect((await post(page, '/api/staff/admins', { ...body, name: 'Changed identity' }, key)).status()).toBe(409)
})
