import { webcrypto } from 'node:crypto'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import App from './App.jsx'
import { ActionConfirmationProvider } from './components/ActionConfirmationProvider.jsx'
import { EditGuardProvider } from './components/EditGuardProvider.jsx'
import { NotificationProvider } from './components/NotificationProvider.jsx'
import { mockDb } from './services/mockDb.js'
import { MOCK_SESSION_KEY } from './services/authService.js'
import { OWNER_NAV, TRAINER_NAV } from './app/constants.js'
import { withNavigationHistory } from './test/fixtures/navigation.js'

const click = name => fireEvent.click(screen.getByRole('button', { name, exact: true }))
const route = async path => waitFor(() => expect(location.hash).toBe(`#/${path}`))
const traverse = async direction => act(async () => { history.go(direction) })
function touch(type, x) {
  const point = { identifier: 1, clientX: x, clientY: 180 }
  fireEvent(document.querySelector('.portal-main'), Object.assign(new Event(type, { bubbles: true, cancelable: true }), {
    touches: type === 'touchend' ? [] : [point], changedTouches: [point],
  }))
}
const swipe = () => { touch('touchstart', 10); touch('touchmove', 160); touch('touchend', 180) }
async function show(path = 'dashboard', id = 'u-owner') {
  localStorage.setItem(MOCK_SESSION_KEY, JSON.stringify({ userId: id, expiresAt: Date.now() + 3600000 }))
  history.replaceState(null, '', `/#/${path}`)
  render(<NotificationProvider><ActionConfirmationProvider><EditGuardProvider><App /></EditGuardProvider></ActionConfirmationProvider></NotificationProvider>)
  await waitFor(() => expect(document.querySelector('.portal-shell')).toHaveAttribute('data-user-id', id))
}
function nav(item) {
  const group = screen.getByRole('button', { name: `${item.group} section`, exact: true })
  if (group.getAttribute('aria-expanded') === 'false') fireEvent.click(group)
  fireEvent.click(within(screen.getByRole('navigation', { name: 'Portal navigation' })).getByRole('button', { name: item.label, exact: true }))
}
beforeEach(() => {
  localStorage.clear(); mockDb.reset(); vi.stubGlobal('crypto', webcrypto)
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
  vi.stubGlobal('matchMedia', () => ({ matches: false, addEventListener() {}, removeEventListener() {} }))
})
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

const mainRoutes = [['owner', 'u-owner', OWNER_NAV], ['trainer', 'u-marcus', TRAINER_NAV]]
  .flatMap(([role, id, items]) => items.filter(item => item.key !== 'dashboard').map(item => [role, item.key, id, item]))
it.each(mainRoutes)('supports %s %s Back and Forward including a revisited Dashboard', async (_, key, id, item) => {
  await show('dashboard', id)
  expect(screen.queryByRole('button', { name: 'Back', exact: true })).not.toBeInTheDocument()
    nav(item); await route(item.key)
    expect(screen.getByRole('button', { name: 'Back', exact: true })).toBeVisible()
    const depth = history.state.fitfinityDepth
    nav(item); expect(history.state.fitfinityDepth).toBe(depth)
    click('Back'); await route('dashboard')
    await traverse(1); await route(item.key)
    click('Home'); await route('dashboard')
    expect(screen.getByRole('button', { name: 'Back', exact: true })).toBeVisible()
    click('Back'); await route(item.key)
    click('Back'); await route('dashboard')
})

it('restores a previous remuneration cycle, independent list pages and shown amounts through a session and native history', async () => {
  mockDb.mutate(withNavigationHistory)
  await show('remuneration')
  click('View pay cycle 2020-09')
  await route('remuneration/2020-09')
  click('Show remuneration amounts'); click('Next')
  expect(screen.getByLabelText('List pages')).toHaveTextContent('Page 2 of 2')
  click('View remuneration for Marcus Tan')
  await route('remuneration/2020-09/t1')
  expect(screen.queryByRole('button', { name: 'Back to Pay Cycle' })).not.toBeInTheDocument()
  expect(screen.getByLabelText('List pages')).toHaveTextContent('Page 1 of 3')
  click('Next')
  const first = document.querySelector('.remuneration-session').dataset.sessionId
  const writes = vi.spyOn(history, 'replaceState')
  fireEvent.click(within(document.querySelector('.remuneration-session')).getByRole('button'))
  await screen.findByRole('heading', { name: 'Session Overview' })
  await traverse(-1); await route('remuneration/2020-09/t1')
  expect(screen.getByLabelText('List pages')).toHaveTextContent('Page 2 of 3')
  expect(document.querySelector('.remuneration-session')).toHaveAttribute('data-session-id', first)
  expect(screen.getByRole('button', { name: 'Hide remuneration amounts' })).toBeVisible()
  await act(async () => { window.dispatchEvent(new Event('focus')) })
  await waitFor(() => expect(document.querySelector('.remuneration-session')).toHaveAttribute('data-session-id', first))
  click('Back'); await route('remuneration/2020-09')
  expect(document.querySelector('.remuneration-cycle-caption')).toHaveTextContent('16 Aug 2020 – 15 Sept 2020')
  expect(screen.getByLabelText('List pages')).toHaveTextContent('Page 2 of 2')
  await traverse(1); await route('remuneration/2020-09/t1')
  expect(screen.getByLabelText('List pages')).toHaveTextContent('Page 2 of 3')
  // A history transition should not trigger the former alternating pager loop.
  expect(writes.mock.calls.length).toBeLessThan(20)
})

it('returns from View All Renewals to the same calendar mode and period', async () => {
  await show()
  click('Monthly'); click('Next calendar period')
  const month = document.querySelector('.calendar-range option:checked').textContent
  click('View All Renewals'); await route('messages/renewals')
  click('Back'); await route('dashboard')
  expect(screen.getByRole('button', { name: 'Monthly', exact: true })).toHaveAttribute('aria-pressed', 'true')
  expect(document.querySelector('.calendar-range option:checked')).toHaveTextContent(month)
})

it('provides a parent fallback for a directly opened trainer cycle and the password screen', async () => {
  mockDb.mutate(withNavigationHistory)
  await show('remuneration/2020-09/t1')
  click('Back'); await route('remuneration/2020-09')
  expect(document.querySelector('.remuneration-cycle-caption')).toHaveTextContent('16 Aug 2020 – 15 Sept 2020')
  click('Back'); await route('remuneration')
  click('Back'); await route('dashboard')
  click('Open profile menu')
  fireEvent.click(screen.getByRole('menuitem', { name: 'Change Password', exact: true }))
  await route('change-password')
  click('Back'); await route('dashboard')
  cleanup()
  await show('remuneration/2020-09/t1', 'u-marcus')
  expect(screen.getByLabelText('Cycle session breakdown')).toBeVisible()
  click('Back'); await route('remuneration')
  expect(screen.getByLabelText('Pay cycles')).toBeVisible()
})

it('retains a client swipe across a service refresh and restores the filtered client list', async () => {
  await show('clients')
  fireEvent.change(screen.getByLabelText('Search client'), { target: { value: 'Amanda' } })
  click('View Amanda Lim'); await route('clients/c1')
  touch('touchstart', 10)
  mockDb.mutate(db => { db.clients.find(item => item.id === 'c1').name = 'Amanda Refreshed' })
  await act(async () => { window.dispatchEvent(new Event('focus')) })
  await screen.findByRole('heading', { name: 'Amanda Refreshed' })
  touch('touchmove', 160); touch('touchend', 180)
  await route('clients')
  expect(screen.getByLabelText('Search client')).toHaveValue('Amanda')
})

it('guards an unsaved content swipe, retains the draft on Cancel and leaves exactly one entry on confirmation', async () => {
  await show('content')
  click('Add Content')
  fireEvent.change(screen.getByLabelText('Content title'), { target: { value: 'Retain draft' } })
  swipe()
  await screen.findByRole('dialog', { name: 'Leave this edit?' })
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel', exact: true }))
  expect(screen.getByLabelText('Content title')).toHaveValue('Retain draft')
  expect(location.hash).toBe('#/content/new')
  swipe()
  await screen.findByRole('dialog', { name: 'Leave this edit?' })
  click('Leave Without Saving'); await route('content')
  expect(history.state.fitfinityDepth).toBe(0)
})

it.each([
  ['content', 'Add Content'], ['packages', 'Add Package'], ['exercises', 'Add Exercise'],
])('returns the %s creation Cancel control through history without adding a new list entry', async (path, add) => {
  await show(path)
  click(add); await route(`${path}/new`)
  click('Cancel')
  if (screen.queryByRole('dialog', { name: 'Leave this edit?' })) click('Leave Without Saving')
  await route(path)
  expect(history.state.fitfinityDepth).toBe(0)
})
