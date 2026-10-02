import { expect, test, fillClientRequiredFields, waitForPortal } from './fixtures.js'

async function begin(page, couple = false) {
  await page.goto('/#/clients/new')
  await waitForPortal(page)
  if (couple) await page.getByLabel('Client type', { exact: true }).selectOption('Couple')
  for (let i = 0; i < (couple ? 2 : 1); i++) {
    const prefix = couple ? `Client ${i + 1}` : 'Client'
    if (couple) await page.getByRole('button', { name: prefix, exact: true }).click()
    await page.getByLabel(`${prefix} name`, { exact: true }).fill(`Assessment Person ${i + 1}`)
    await fillClientRequiredFields(page, prefix)
  }
  await page.getByRole('button', { name: 'Continue to Health & Assessments', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Health & Assessments', exact: true })).toBeVisible()
}

test('assessment grid saves every form directly, reopens answers and keeps new-client records unwritten', async ({ page }) => {
  await begin(page)
  const before = await page.evaluate(() => localStorage.getItem('fitfinity-m2-demo-db-v4'))
  const cards = page.locator('.assessment-card')
  await expect(cards).toHaveCount(11)
  const names = await cards.locator('strong').allTextContents()
  const paperAnswers = {
    'Lifestyle & Health History': ['Health details', 'Recorded health details'],
    'Upper Body Flexibility': ['Shoulder flexion — observations', 'Recorded shoulder observation'],
    'Lower Body Flexibility': ['Hip flexion — observations', 'Recorded hip observation'],
    'Hurdle Step Screen': ['Front view: feet — reference finding observed', 'checkbox'],
    'Bend & Lift': ['Front view: feet — compensation observed', 'Recorded bend observation'],
    'Single-Leg Assessment': ['Front view: feet — compensation observed', 'Recorded single-leg observation'],
    'Push Assessment': ['Side view: scapulothoracic — compensation observed', 'Recorded push observation'],
    'Pull Assessment': ['Side view: lumbar spine — compensation observed', 'Recorded pull observation'],
    'Rotation Assessment': ['Front / rear view: trunk (1) — compensation observed', 'Recorded rotation observation'],
    'Static Balance': ['Eyes open — trial 1 (seconds)', '12'],
    'Anthropometric Measurements': ['Weight (kg)', '60'],
  }
  for (const name of names) {
    const card = page.getByRole('button', { name: `${name} — Not filled`, exact: true })
    await expect(card).not.toHaveClass(/is-filled/)
    await card.click()
    const dialog = page.getByRole('dialog', { name, exact: true })
    const metadata = dialog.getByRole('group', { name: 'Form details', exact: true })
    // These independent reads share one stable dialog; finish all before editing it.
    await Promise.all([
      expect(dialog.getByRole('link', { name: /Open original PDF/ })).toHaveAttribute('href', /assessment-forms\/.+\.pdf$/),
      expect(metadata).toContainText('Assessment Person 1'),
      expect(metadata.locator('input, textarea, select, [contenteditable]')).toHaveCount(0),
      expect(dialog.getByLabel('Additional observations / items not assessed', { exact: true })).toHaveCount(0),
    ])
    const [label, value] = paperAnswers[name]
    const answer = dialog.getByLabel(label, { exact: true })
    if (value === 'checkbox') await answer.check()
    else await answer.fill(value)
    await dialog.getByRole('button', { name: 'Save', exact: true }).click()
    const saved = page.getByRole('button', { name: `${name} — Filled`, exact: true })
    await Promise.all([
      expect(dialog).toHaveCount(0),
      expect(saved).toHaveClass(/is-filled/),
      expect(saved).toBeFocused(),
    ])
    await saved.click()
    if (value === 'checkbox') await expect(answer).toBeChecked()
    else await expect(answer).toHaveValue(value)
    await dialog.getByRole('button', { name: 'Cancel', exact: true }).click()
  }
  await expect(page.getByText('11 of 11 filled', { exact: true })).toBeVisible()
  expect(await page.evaluate(() => localStorage.getItem('fitfinity-m2-demo-db-v4'))).toBe(before)
  await page.getByRole('button', { name: 'Continue to Package & Preferences', exact: true }).click()
  await page.getByRole('button', { name: 'Back to Health & Assessments', exact: true }).click()
  await expect(page.locator('.assessment-card.is-filled')).toHaveCount(11)
})

test('blank saves and cancelled popup edits never make a form green', async ({ page }) => {
  await begin(page)
  await page.getByRole('button', { name: 'Static Balance — Not filled', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Static Balance', exact: true })
  await dialog.getByRole('button', { name: 'Save', exact: true }).click()
  await expect(dialog.getByRole('alert')).toContainText('at least one answer')
  await dialog.getByLabel('Eyes open — trial 1 (seconds)', { exact: true }).fill('0')
  await dialog.getByRole('button', { name: 'Cancel', exact: true }).click()
  const discard = page.getByRole('dialog', { name: 'Discard form changes?', exact: true })
  await discard.getByRole('button', { name: 'Cancel', exact: true }).click()
  await expect(dialog.getByLabel('Eyes open — trial 1 (seconds)', { exact: true })).toHaveValue('0')
  await dialog.getByRole('button', { name: 'Close dialog', exact: true }).click()
  await discard.getByRole('button', { name: 'Discard Changes', exact: true }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Static Balance — Not filled', exact: true })).toBeVisible()
})

test('couple assessment statuses and answers belong to the selected person', async ({ page }) => {
  await begin(page, true)
  await page.getByRole('button', { name: 'Client 1', exact: true }).click()
  await page.getByRole('button', { name: 'Single-Leg Assessment — Not filled', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Single-Leg Assessment', exact: true })
  await expect(dialog.getByRole('group', { name: 'Form details', exact: true })).toContainText('Assessment Person 1')
  await dialog.getByLabel('Front view: feet — compensation observed', { exact: true }).fill('First person observation')
  await dialog.getByRole('button', { name: 'Save', exact: true }).click()
  await page.getByRole('button', { name: 'Client 2', exact: true }).click()
  await expect(page.locator('.assessment-card.is-filled')).toHaveCount(0)
  await page.getByRole('button', { name: 'Single-Leg Assessment — Not filled', exact: true }).click()
  await expect(dialog.getByLabel('Front view: feet — compensation observed', { exact: true })).toHaveValue('')
  await dialog.getByRole('button', { name: 'Cancel', exact: true }).click()
  await page.getByRole('button', { name: 'Client 1', exact: true }).click()
  await page.getByRole('button', { name: 'Single-Leg Assessment — Filled', exact: true }).click()
  await expect(dialog.getByLabel('Front view: feet — compensation observed', { exact: true })).toHaveValue('First person observation')
})

test('long health popup scrolls independently, keeps actions reachable and contains keyboard focus', async ({ page }) => {
  await begin(page)
  const card = page.getByRole('button', { name: 'Lifestyle & Health History — Not filled', exact: true })
  await card.click()
  const dialog = page.getByRole('dialog', { name: 'Lifestyle & Health History', exact: true })
  await expect(page.locator('body')).toHaveCSS('position', 'fixed')
  const dimensions = await dialog.evaluate(element => ({ width: element.getBoundingClientRect().width,
    pageWidth: element.querySelector('.assessment-paper-page').getBoundingClientRect().width,
    pageHeight: element.querySelector('.assessment-paper-page').getBoundingClientRect().height }))
  const viewport = page.viewportSize().width
  expect(dimensions.width).toBeLessThanOrEqual(viewport)
  expect(dimensions.pageWidth).toBeGreaterThanOrEqual(816)
  expect(dimensions.pageWidth / dimensions.pageHeight).toBeCloseTo(612 / 792, 2)
  if (viewport > 1050) expect(dimensions.width).toBeGreaterThan(1000)
  await expect(dialog.locator('.assessment-paper-page')).toHaveCount(4)
  // Later artwork loads as its paper page approaches the viewport. Verify every page.
  for (let index = 0; index < 4; index += 1) {
    const paper = dialog.getByRole('region', { name: `Paper page ${index + 1}`, exact: true })
    await paper.scrollIntoViewIfNeeded()
    await expect.poll(() => paper.locator('.assessment-paper-art').evaluate(image => image.complete && image.naturalWidth > 0)).toBe(true)
    expect(await dialog.evaluate(element => ({ left: element.scrollLeft, overflow: element.scrollWidth - element.clientWidth })))
      .toEqual({ left: 0, overflow: 0 })
  }
  const firstPage = dialog.getByRole('region', { name: 'Paper page 1', exact: true })
  expect(await firstPage.getAttribute('data-no-swipe')).not.toBeNull()
  const birthday = dialog.getByLabel('Date of birth', { exact: true })
  // Establish the row's vertical position before separately checking sideways panning.
  await birthday.scrollIntoViewIfNeeded()
  await firstPage.evaluate(element => { element.scrollLeft = 0 })
  await firstPage.evaluate(element => { element.scrollLeft = element.scrollWidth })
  await expect(birthday).toBeInViewport()
  expect(await dialog.evaluate(element => element.scrollLeft)).toBe(0)
  if (viewport < 816) expect(await firstPage.evaluate(element => element.scrollLeft)).toBeGreaterThan(0)
  await expect(birthday).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)')
  await birthday.focus()
  await expect(birthday).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)')
  await firstPage.evaluate(element => { element.scrollLeft = 0 })
  await expect(dialog.getByRole('checkbox', { name: 'Asthma', exact: true })).not.toBeChecked()
  expect(await dialog.evaluate(element => element.scrollHeight > element.clientHeight)).toBe(true)
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(0)
  await dialog.getByRole('region', { name: 'Paper page 4', exact: true }).scrollIntoViewIfNeeded()
  expect(await dialog.evaluate(element => ({ left: element.scrollLeft, overflow: element.scrollWidth - element.clientWidth })))
    .toEqual({ left: 0, overflow: 0 })
  await expect(dialog.getByRole('button', { name: 'Close dialog', exact: true })).toBeInViewport()
  await expect(dialog.getByRole('button', { name: 'Save', exact: true })).toBeInViewport()
  await dialog.getByRole('button', { name: 'Save', exact: true }).focus()
  await page.keyboard.press('Tab')
  await expect(dialog.getByRole('button', { name: 'Close dialog', exact: true })).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(dialog).toHaveCount(0)
  await expect(card).toBeFocused()
  await expect(page.locator('body')).not.toHaveCSS('position', 'fixed')
})

test('owner fills an unfilled form from View Client and saved answers survive reload as read-only', async ({ page }) => {
  await page.goto('/#/clients/c1')
  await waitForPortal(page)
  const empty = page.getByRole('button', { name: 'Static Balance — Not filled', exact: true })
  await expect(empty).toBeEnabled()
  await empty.click()
  const dialog = page.getByRole('dialog', { name: 'Static Balance', exact: true })
  await dialog.getByLabel('Eyes open — trial 1 (seconds)', { exact: true }).fill('0')
  await dialog.getByRole('button', { name: 'Cancel', exact: true }).click()
  await page.getByRole('dialog', { name: 'Discard form changes?', exact: true }).getByRole('button', { name: 'Discard Changes', exact: true }).click()
  await expect(empty).toBeFocused()
  await empty.click()
  await expect(dialog.getByLabel('Eyes open — trial 1 (seconds)', { exact: true })).toHaveValue('')
  await dialog.getByLabel('Eyes open — trial 1 (seconds)', { exact: true }).fill('0')
  await dialog.getByRole('button', { name: 'Save', exact: true }).click()
  await expect(dialog).toHaveCount(0)
  const filled = page.getByRole('button', { name: 'Static Balance — Filled', exact: true })
  await expect(filled).toHaveClass(/is-filled/)
  await expect(filled).toBeFocused()
  await page.reload()
  await waitForPortal(page)
  await filled.click()
  await expect(dialog.getByLabel('Eyes open — trial 1 (seconds)', { exact: true })).toHaveText('0')
  await expect(dialog.locator('input, textarea, select')).toHaveCount(0)
  await expect(dialog.getByRole('button', { name: 'Save', exact: true })).toHaveCount(0)
  await dialog.getByRole('button', { name: 'Close', exact: true }).click()
  await expect(filled).toBeFocused()
})
