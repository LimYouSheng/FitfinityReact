import { expect, test, waitForPortal, mockPhysicalOrientation } from './fixtures.js'

const KEY = 'fitfinity-m2-demo-db-v4'

test('trainer reassignment dropdown waits for release and permits scrolling from the field', async ({ page, browserName, hasTouch }) => {
  await mockPhysicalOrientation(page)
  await page.setViewportSize({ width: 390, height: 480 })
  await page.goto('/')
  await waitForPortal(page)
  await page.evaluate(key => {
    const db = JSON.parse(localStorage.getItem(key))
    for (const trainer of db.trainers) trainer.status = ['t1', 't3'].includes(trainer.id) ? 'active' : 'inactive'
    db.trainers.find(trainer => trainer.id === 't3').availability = {}
    const client = db.clients.find(item => item.id === 'c1')
    client.status = 'active'; client.package.status = 'active'
    db.sessions = Array.from({ length: 10 }, (_, index) => ({ id: `scroll-reassignment-${index}`, clientId: client.id,
      packageId: client.package.id, trainerId: 't1', date: `2027-06-${String(index + 7).padStart(2, '0')}`,
      from: '18:00', to: '19:00', status: 'planned', sessionNumber: index + 1, packageTotal: 12, exercisePlan: [] }))
    localStorage.setItem(key, JSON.stringify(db))
  }, KEY)
  await page.goto('/#/trainers/t1')
  await page.reload()
  await waitForPortal(page)
  const summary = page.locator('.profile-menu > summary')
  if (await summary.isVisible()) await summary.click()
  await page.getByRole('button', { name: 'Deactivate Trainer', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Deactivate Marcus Tan?', exact: true })
  const select = dialog.getByRole('combobox', { name: 'Reassign Amanda Lim' }).first()
  await expect(select).toBeEnabled()
  await select.scrollIntoViewIfNeeded()
  await select.dispatchEvent('pointerdown', { pointerId: 1, pointerType: 'touch', clientX: 150, clientY: 280 })
  await expect(select).toHaveAttribute('aria-expanded', 'false')
  await select.dispatchEvent('pointermove', { pointerId: 1, pointerType: 'touch', clientX: 150, clientY: 100 })
  await select.dispatchEvent('pointercancel', { pointerId: 1, pointerType: 'touch' })
  await expect(select).toHaveAttribute('aria-expanded', 'false')
  await expect.poll(() => dialog.evaluate(element => element.scrollHeight - element.clientHeight)).toBeGreaterThan(0)
  const beforeScroll = await dialog.evaluate(element => element.scrollTop)
  if (browserName === 'chromium') {
    const input = await page.context().newCDPSession(page)
    try {
      await input.send('Emulation.setTouchEmulationEnabled', { enabled: true, maxTouchPoints: 1 })
      const box = await select.boundingBox()
      await input.send('Input.synthesizeScrollGesture', {
        x: Math.round(box.x + box.width / 2), y: Math.round(box.y + box.height / 2),
        yDistance: -140, gestureSourceType: 'touch',
      })
    } finally {
      await input.send('Emulation.setTouchEmulationEnabled', { enabled: false })
      await input.detach()
    }
  } else {
    // Assert real modal overflow plus the cancelled pointer sequence on WebKit;
    // native swipe cancellation is exercised above with Chromium touch input.
    await dialog.evaluate(element => { element.scrollTop += 140 })
  }
  await expect.poll(() => dialog.evaluate(element => element.scrollTop)).toBeGreaterThan(beforeScroll)
  await expect(page.getByRole('listbox')).toHaveCount(0)
  await expect(select).toHaveValue('')
  await select.scrollIntoViewIfNeeded()
  const box = await select.boundingBox()
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.down()
  await expect(select).toHaveAttribute('aria-expanded', 'false')
  await page.mouse.up()
  const choices = page.getByRole('listbox', { name: 'Reassign Amanda Lim' })
  await expect(choices).toBeVisible()
  const replacement = await select.locator('option[value="t3"]').textContent()
  await choices.getByRole('option', { name: replacement, exact: true }).click()
  await expect(select).toHaveValue('t3')
  if (hasTouch) {
    await select.tap()
    await expect(choices).toBeVisible()
    await page.keyboard.press('Escape')
  }
  await dialog.getByRole('button', { name: 'Cancel', exact: true }).click()
  await expect(dialog).toHaveCount(0)
  await expect(page.locator('body')).not.toHaveCSS('position', 'fixed')
  const saved = await page.evaluate(key => JSON.parse(localStorage.getItem(key)), KEY)
  expect(saved.trainers.find(trainer => trainer.id === 't1').status).toBe('active')
  expect(saved.sessions.every(session => session.trainerId === 't1')).toBe(true)
})

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
