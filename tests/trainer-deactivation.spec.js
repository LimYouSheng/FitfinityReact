import { expect, test, waitForPortal } from './fixtures.js'

const KEY = 'fitfinity-m2-demo-db-v4'

test('trainer deactivation offers free replacements only and saves the chosen assignment', async ({ page }) => {
  await page.goto('/')
  await waitForPortal(page)
  await page.evaluate(key => {
    const db = JSON.parse(localStorage.getItem(key))
    for (const trainer of db.trainers) trainer.status = ['t1', 't2', 't3'].includes(trainer.id) ? 'active' : 'inactive'
    db.trainers.find(trainer => trainer.id === 't3').availability = {}
    for (const client of db.clients.filter(item => ['c1', 'c2'].includes(item.id))) {
      client.status = 'active'; client.package.status = 'active'
    }
    db.sessions = ['c1', 'c2'].map((id, index) => ({ id: `replacement-fixture-${index}`, clientId: id,
      packageId: db.clients.find(client => client.id === id).package.id, trainerId: index === 0 ? 't1' : 't2',
      date: '2027-06-07', from: index === 0 ? '18:00' : '18:30', to: index === 0 ? '19:00' : '19:30',
      status: 'planned', sessionNumber: 1, packageTotal: 12, exercisePlan: [] }))
    localStorage.setItem(key, JSON.stringify(db))
  }, KEY)
  await page.goto('/#/trainers/t1')
  await page.reload()
  await waitForPortal(page)
  const summary = page.locator('.profile-menu > summary')
  if (await summary.isVisible()) await summary.click()
  await page.getByRole('button', { name: 'Deactivate Trainer', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Deactivate Marcus Tan?', exact: true })
  const select = dialog.getByRole('combobox', { name: 'Reassign Amanda Lim' })
  await expect(select.locator('option[value="t1"]')).toHaveCount(0)
  await expect(select.locator('option[value="t2"]')).toHaveCount(0)
  await expect(select.locator('option[value="t4"]')).toHaveCount(0)
  await expect(select.locator('option[value="t3"]')).toHaveCount(1)
  await expect(dialog.getByRole('button', { name: 'Deactivate Trainer', exact: true })).toBeDisabled()
  await select.selectOption('t3')
  expect(await page.evaluate(key => JSON.parse(localStorage.getItem(key)).sessions[0].trainerId, KEY)).toBe('t1')
  await dialog.getByRole('button', { name: 'Deactivate Trainer', exact: true }).click()
  await expect(dialog).toHaveCount(0)
  await expect(page).toHaveURL(/#\/trainers$/)
  await waitForPortal(page)
  await page.getByLabel('Search trainer', { exact: true }).fill('Marcus Tan')
  await page.getByLabel('Search trainer', { exact: true }).press('Tab')
  const row = page.getByLabel('Trainer list', { exact: true }).locator('.compact-list-row')
    .filter({ has: page.getByRole('button', { name: 'View Marcus Tan', exact: true }) })
  await expect(row).toContainText('Inactive')
  await row.getByRole('button', { name: 'View Marcus Tan', exact: true }).click()
  await expect(page).toHaveURL(/#\/trainers\/t1$/)
  await expect(page.getByLabel('Trainer status', { exact: true })).toContainText('Inactive')
  const saved = await page.evaluate(key => JSON.parse(localStorage.getItem(key)), KEY)
  expect(saved.trainers.find(trainer => trainer.id === 't1').status).toBe('inactive')
  expect(saved.sessions.map(session => session.trainerId)).toEqual(['t3', 't2'])
  expect(saved.users.find(user => user.trainerId === 't1').status).toBe('inactive')
  expect(saved.sessions[0].packageId).toBe(saved.clients.find(client => client.id === 'c1').package.id)
})
