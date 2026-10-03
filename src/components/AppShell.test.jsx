import { act, cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import AppShell from './AppShell.jsx'
import { ActionConfirmationProvider } from './ActionConfirmationProvider.jsx'
import { EditGuardProvider } from './EditGuardProvider.jsx'
import { seed } from '../data/seed.js'
import ConfirmDialog from './ConfirmDialog.jsx'

let media
beforeEach(() => {
  const listeners = new Set()
  media = {
    matches: false,
    addEventListener: (_type, listener) => listeners.add(listener),
    removeEventListener: (_type, listener) => listeners.delete(listener),
    resize(matches) { this.matches = matches; listeners.forEach(listener => listener()) },
  }
  vi.stubGlobal('matchMedia', () => media)
})
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks() })

function shell(overrides = {}) {
  const owner = seed.users.find(user => user.role === 'owner')
  return <ActionConfirmationProvider><EditGuardProvider><AppShell
    user={owner} userId={owner.id} users={seed.users} messages={seed.messages}
    route="dashboard" onRoute={() => {}} {...overrides}
  ><h1>Current page</h1></AppShell></EditGuardProvider></ActionConfirmationProvider>
}

it('starts collapsed and opens only one section by keyboard without exposing hidden links', async () => {
  const user = userEvent.setup()
  const onRoute = vi.fn()
  render(shell({ onRoute }))
  const operations = screen.getByRole('button', { name: 'Operations section' })
  const system = screen.getByRole('button', { name: 'System section' })
  expect(operations).toHaveAttribute('aria-expanded', 'false')
  operations.focus()
  await user.keyboard('{Enter}')
  expect(operations).toHaveAttribute('aria-expanded', 'true')
  await user.keyboard('{Enter}')
  expect(operations).toHaveAttribute('aria-expanded', 'false')
  expect(document.getElementById(operations.getAttribute('aria-controls'))).not.toBeVisible()
  expect(screen.queryByRole('button', { name: 'Clients', exact: true })).not.toBeInTheDocument()
  await user.tab()
  expect(screen.getByRole('button', { name: 'Remuneration section' })).toHaveFocus()
  system.focus(); await user.keyboard(' ')
  expect(system).toHaveAttribute('aria-expanded', 'true')
  await user.keyboard(' ')
  expect(system).toHaveAttribute('aria-expanded', 'false')
  operations.focus(); await user.keyboard(' ')
  expect(screen.getByRole('button', { name: 'Clients', exact: true })).toBeVisible()
  expect(system).toHaveAttribute('aria-expanded', 'false')
  system.focus(); await user.keyboard('{Enter}')
  expect(system).toHaveAttribute('aria-expanded', 'true')
  expect(operations).toHaveAttribute('aria-expanded', 'false')
  expect(screen.queryByRole('button', { name: 'Clients', exact: true })).not.toBeInTheDocument()
  expect(document.querySelectorAll('.nav-group-toggle[aria-expanded="true"]')).toHaveLength(1)
  expect(onRoute).not.toHaveBeenCalled()
  expect(screen.getByRole('heading', { name: 'Current page' })).toBeVisible()
})

it('reveals the destination section and resets collapse state for another account', async () => {
  const user = userEvent.setup()
  const { rerender } = render(shell())
  await user.click(screen.getByRole('button', { name: 'Operations section' }))
  const menu = screen.getByRole('button', { name: 'Open navigation' })
  await user.click(menu)
  expect(menu).toHaveAttribute('aria-expanded', 'true')
  rerender(shell({ route: 'messages', routePath: 'messages/example' }))
  expect(menu).toHaveAttribute('aria-expanded', 'false')
  await user.click(menu)
  expect(menu).toHaveAttribute('aria-expanded', 'true')
  await user.click(screen.getByRole('button', { name: 'Close navigation' }))
  expect(menu).toHaveAttribute('aria-expanded', 'false')
  expect(screen.getByRole('button', { name: 'System section' })).toHaveAttribute('aria-expanded', 'true')
  expect(screen.getByRole('button', { name: 'Operations section' })).toHaveAttribute('aria-expanded', 'false')
  expect(within(screen.getByRole('navigation', { name: 'Portal navigation' })).getByRole('button', { name: 'Messages', exact: true })).toHaveClass('active')
  expect(screen.getByRole('button', { name: 'Management section' })).toHaveAttribute('aria-expanded', 'false')
  await user.click(screen.getByRole('button', { name: 'System section' }))
  rerender(shell({ route: 'messages', routePath: 'messages/another' }))
  expect(screen.getByRole('button', { name: 'System section' })).toHaveAttribute('aria-expanded', 'true')
  await user.click(screen.getByRole('button', { name: 'System section' }))
  const trainer = seed.users.find(item => item.role === 'trainer')
  rerender(shell({ user: trainer, userId: trainer.id }))
  expect(screen.getByRole('button', { name: 'System section' })).toHaveAttribute('aria-expanded', 'false')
  expect(screen.getByRole('button', { name: 'Trainer section' })).toHaveAttribute('aria-expanded', 'false')
  expect(screen.queryByRole('button', { name: 'Management section' })).not.toBeInTheDocument()
})

it('keeps section choices collapsed or expanded consistently across drawer and fixed layouts', async () => {
  const user = userEvent.setup()
  render(shell())
  await user.click(screen.getByRole('button', { name: 'System section' }))
  act(() => media.resize(true))
  expect(screen.getByRole('button', { name: 'System section' })).toHaveAttribute('aria-expanded', 'true')
  expect(screen.getByRole('button', { name: 'Management section' })).toHaveAttribute('aria-expanded', 'false')
  expect(screen.queryByRole('button', { name: 'Exercise Library', exact: true })).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Management section' }))
  expect(screen.getByRole('button', { name: 'Content Management', exact: true })).toBeVisible()
  expect(screen.getByRole('button', { name: 'System section' })).toHaveAttribute('aria-expanded', 'false')
  await user.click(screen.getByRole('button', { name: 'Management section' }))
  act(() => media.resize(false))
  expect(screen.getByRole('button', { name: 'System section' })).toHaveAttribute('aria-expanded', 'false')
  expect(screen.getByRole('button', { name: 'Management section' })).toHaveAttribute('aria-expanded', 'false')
  expect(screen.queryByRole('button', { name: 'Exercise Library', exact: true })).not.toBeInTheDocument()
})

it('locks the page at its current position until the navigation scrim is closed', async () => {
  const user = userEvent.setup()
  vi.stubGlobal('scrollX', 0)
  vi.stubGlobal('scrollY', 320)
  const restore = vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
  document.body.style.overflow = 'auto'
  document.documentElement.style.overscrollBehavior = 'contain'
  try {
    render(shell())
    await user.click(screen.getByRole('button', { name: 'Open navigation' }))
    expect(document.body.style.position).toBe('fixed')
    expect(document.body.style.top).toBe('-320px')
    expect(document.documentElement.style.overflow).toBe('hidden')
    await user.click(screen.getByRole('button', { name: 'Close navigation' }))
    expect(document.body.style.position).toBe('')
    expect(document.body.style.top).toBe('')
    expect(document.body.style.overflow).toBe('auto')
    expect(document.documentElement.style.overscrollBehavior).toBe('contain')
    expect(restore).toHaveBeenCalledWith(0, 320)
  } finally {
    cleanup()
    document.body.style.overflow = ''
    document.documentElement.style.overscrollBehavior = ''
  }
})

it.each(['route', 'account'])('releases the drawer scroll lock when the %s changes', async change => {
  const user = userEvent.setup()
  const { rerender } = render(shell())
  await user.click(screen.getByRole('button', { name: 'Open navigation' }))
  expect(document.body.style.position).toBe('fixed')
  const trainer = seed.users.find(item => item.role === 'trainer')
  rerender(shell(change === 'route' ? { route: 'clients' } : { user: trainer, userId: trainer.id }))
  expect(document.body.style.position).toBe('')
  expect(screen.getByRole('button', { name: 'Open navigation' })).toHaveAttribute('aria-expanded', 'false')
})

it('releases the drawer lock on desktop resize and on unmount', async () => {
  const user = userEvent.setup()
  const { unmount } = render(shell())
  const opener = screen.getByRole('button', { name: 'Open navigation' })
  await user.click(opener)
  expect(document.body.style.position).toBe('fixed')
  act(() => media.resize(true))
  expect(opener).toHaveAttribute('aria-expanded', 'false')
  expect(document.body.style.position).toBe('')
  act(() => media.resize(false))
  await user.click(opener)
  expect(document.body.style.position).toBe('fixed')
  unmount()
  expect(document.body.style.position).toBe('')
  expect(document.documentElement.style.overflow).toBe('')
})

it.each(['drawer', 'dialog'])('keeps the page locked when an overlapping %s closes first', async first => {
  const user = userEvent.setup()
  const view = open => <>{shell()}<ConfirmDialog open={open} title="Overlay" /></>
  const { rerender } = render(view(false))
  await user.click(screen.getByRole('button', { name: 'Open navigation' }))
  expect(document.body.style.position).toBe('fixed')
  rerender(view(true))
  expect(document.body.style.position).toBe('fixed')
  if (first === 'drawer') {
    act(() => media.resize(true))
    expect(document.body.style.position).toBe('fixed')
    rerender(view(false))
  } else {
    rerender(view(false))
    expect(document.body.style.position).toBe('fixed')
    await user.click(screen.getByRole('button', { name: 'Close navigation' }))
  }
  expect(document.body.style.position).toBe('')
  expect(document.documentElement.style.overflow).toBe('')
})
