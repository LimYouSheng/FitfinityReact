import { act, cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import AppShell from './AppShell.jsx'
import { ActionConfirmationProvider } from './ActionConfirmationProvider.jsx'
import { EditGuardProvider } from './EditGuardProvider.jsx'
import { seed } from '../data/seed.js'

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
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

function shell(overrides = {}) {
  const owner = seed.users.find(user => user.role === 'owner')
  return <ActionConfirmationProvider><EditGuardProvider><AppShell
    user={owner} userId={owner.id} users={seed.users} messages={seed.messages}
    route="dashboard" onRoute={() => {}} {...overrides}
  ><h1>Current page</h1></AppShell></EditGuardProvider></ActionConfirmationProvider>
}

it('starts collapsed and toggles sections independently by keyboard without exposing hidden links', async () => {
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
  expect(onRoute).not.toHaveBeenCalled()
  expect(screen.getByRole('heading', { name: 'Current page' })).toBeVisible()
})

it('reveals the destination section and resets collapse state for another account', async () => {
  const user = userEvent.setup()
  const { rerender } = render(shell())
  rerender(shell({ route: 'messages', routePath: 'messages/example' }))
  expect(screen.getByRole('button', { name: 'System section' })).toHaveAttribute('aria-expanded', 'true')
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

it('keeps hamburger groups expanded and restores the fixed sidebar state after resizing', async () => {
  const user = userEvent.setup()
  render(shell())
  await user.click(screen.getByRole('button', { name: 'System section' }))
  act(() => media.resize(true))
  expect(screen.queryByRole('button', { name: / section$/ })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Exercise Library', exact: true })).toBeVisible()
  expect(screen.getByRole('button', { name: 'Content Management', exact: true })).toBeVisible()
  act(() => media.resize(false))
  expect(screen.getByRole('button', { name: 'System section' })).toHaveAttribute('aria-expanded', 'true')
  expect(screen.getByRole('button', { name: 'Management section' })).toHaveAttribute('aria-expanded', 'false')
  expect(screen.queryByRole('button', { name: 'Exercise Library', exact: true })).not.toBeInTheDocument()
})
