import { StrictMode } from 'react'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { NotificationProvider, useNotifications } from './NotificationProvider.jsx'
import { ActionConfirmationProvider } from './ActionConfirmationProvider.jsx'
import { EditGuardProvider, useEditGuard } from './EditGuardProvider.jsx'
import AppShell from './AppShell.jsx'

let notifications
function Consumer({ page = 'Draft' }) {
  notifications = useNotifications()
  return <input aria-label={page} />
}
const deferred = () => {
  let resolve, reject
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
const show = (page = 'Draft') => render(<StrictMode><NotificationProvider><Consumer page={page} /></NotificationProvider></StrictMode>)
const advance = ms => act(() => vi.advanceTimersByTime(ms))
afterEach(() => { cleanup(); vi.useRealTimers() })

it('waits for persistence, returns the exact result and survives navigation without moving focus', async () => {
  const view = show(), action = deferred()
  const input = screen.getByRole('textbox')
  input.focus()
  const pending = notifications.runAction(() => action.promise, { message: 'Client created.' })
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
  const created = { id: 'c-new' }
  await act(async () => { action.resolve(created); expect(await pending).toBe(created) })
  expect(input).toHaveFocus()
  expect(screen.getByRole('status')).toHaveTextContent('Client created.')
  view.rerender(<StrictMode><NotificationProvider><Consumer page="Profile" /></NotificationProvider></StrictMode>)
  expect(screen.getByRole('status')).toHaveTextContent('Client created.')
  fireEvent.click(screen.getByRole('button', { name: 'Dismiss notification' }))
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
})

it('shows a persistent red failure, rethrows it and replaces it only after a successful retry', async () => {
  vi.useFakeTimers(); show()
  const error = new Error('Storage full. Try again.')
  await act(async () => {
    await expect(notifications.runAction(() => Promise.reject(error), { message: 'Exercise saved.' })).rejects.toBe(error)
  })
  expect(screen.getByRole('alert').closest('.notification-banner')).toHaveAttribute('data-tone', 'error')
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
  advance(30000)
  expect(screen.getByRole('alert')).toHaveTextContent('Storage full.')
  await act(async () => { await notifications.runAction(() => Promise.resolve(), { message: 'Exercise saved.' }) })
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  expect(screen.getByRole('status')).toHaveTextContent('Exercise saved.')
})

it('pauses automatic dismissal while hovered or keyboard focused', () => {
  vi.useFakeTimers(); show()
  act(() => notifications.notify({ tone: 'info', message: 'Request submitted.' }))
  const banner = screen.getByRole('status').closest('.notification-banner')
  fireEvent.mouseEnter(banner)
  advance(20000)
  expect(banner).toBeInTheDocument()
  fireEvent.mouseLeave(banner)
  act(() => screen.getByRole('button', { name: 'Dismiss notification' }).focus())
  advance(20000)
  expect(banner).toBeInTheDocument()
  act(() => screen.getByRole('textbox').focus())
  advance(5999)
  expect(banner).toBeInTheDocument()
  advance(1)
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
})

it('replaces the previous banner and gives even an identical new message its full display time', () => {
  vi.useFakeTimers(); show()
  act(() => notifications.notify({ message: 'Details saved.' }))
  advance(5000)
  act(() => notifications.notify({ message: 'Details saved.' }))
  advance(1000)
  expect(screen.getAllByRole('status')).toHaveLength(1)
  advance(4999)
  expect(screen.getByRole('status')).toHaveTextContent('Details saved.')
  advance(1)
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
})

it('clears the previous identity and suppresses its late results while passive reads stay quiet', async () => {
  show()
  const previous = deferred()
  const pending = notifications.runAction(() => previous.promise, { message: 'Previous trainer saved.' })
  act(() => { notifications.notify({ message: 'Old notice' }); notifications.clear() })
  await act(async () => { previous.resolve(); await pending })
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
  await act(async () => { await notifications.runAction(() => Promise.resolve(), null) })
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
  const failed = deferred()
  const rejection = notifications.runAction(() => failed.promise, { message: 'Old save' }).catch(error => error)
  act(() => notifications.clear())
  await act(async () => { failed.reject(new Error('Previous identity error')); await rejection })
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

it('keeps banner dismissal outside the app edit lock and leaves the active draft intact', () => {
  function Editor() {
    const { setActiveEdit, activeEdit } = useEditGuard()
    const { notify } = useNotifications()
    return <div className="editing-section"><input aria-label="Draft" defaultValue="Keep me" />
      <button onClick={() => { setActiveEdit('Test draft'); notify({ tone: 'warning', message: 'Request rejected.' }) }}>Begin</button>
      <span>{activeEdit}</span>
    </div>
  }
  const user = { id: 'owner', role: 'owner', name: 'Owner' }
  render(<NotificationProvider><ActionConfirmationProvider><EditGuardProvider>
    <AppShell user={user} users={[user]} userId={user.id} route="clients" messages={[]}>
      <Editor />
    </AppShell>
  </EditGuardProvider></ActionConfirmationProvider></NotificationProvider>)
  fireEvent.click(screen.getByRole('button', { name: 'Begin' }))
  expect(document.querySelector('main .notification-banner')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Dismiss notification' }))
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
  expect(screen.getByRole('textbox', { name: 'Draft' })).toHaveValue('Keep me')
  expect(screen.getByText('Test draft')).toBeVisible()
})
