import { test, expect, signIn, read, account, freshContext } from './fixtures.js'

test('Owner contact edits persist across a fresh login without changing login identity', async ({ page, browser }) => {
  await signIn(page, 'owner', account('ownerprofile'))
  const before = await read(page, '/api/owner-profile')
  await page.goto('/#/owner-profile')
  await page.getByRole('button', { name: 'Edit', exact: true }).click()
  await expect(page.getByLabel('Owner email', { exact: true })).toHaveAttribute('readonly', '')
  await page.getByLabel('Owner name', { exact: true }).fill('Updated Owner Contact')
  await page.getByLabel('Owner phone number', { exact: true }).fill('91234567')
  await page.getByLabel('Owner birthday', { exact: true }).fill('1990-01-02')
  await page.getByLabel('Owner gender', { exact: true }).selectOption('Other')
  await page.getByRole('button', { name: 'Save Changes', exact: true }).click()
  await page.getByRole('dialog', { name: 'Save Owner details?', exact: true }).getByRole('button', { name: 'Save Changes', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Updated Owner Contact', exact: true })).toBeVisible()
  const saved = await read(page, '/api/owner-profile')
  expect(saved).toMatchObject({ id: before.id, email: before.email, version: before.version + 1, name: 'Updated Owner Contact', phone_country_code: '+65', phone_number: '91234567', birthday: '1990-01-02', gender: 'Other' })
  const context = await freshContext(browser, page)
  try {
    const fresh = await context.newPage()
    await signIn(fresh, 'owner', account('ownerprofile'))
    await fresh.goto('/#/owner-profile')
    await expect(fresh.getByRole('heading', { name: 'Updated Owner Contact', exact: true })).toBeVisible()
    expect(await read(fresh, '/api/owner-profile')).toEqual(saved)
  } finally { await context.close() }
})
