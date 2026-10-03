import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { ActionConfirmationProvider } from '../../components/ActionConfirmationProvider.jsx'
import MessageUndo from './MessageUndo.jsx'

const base = Date.parse('2026-10-03T01:00:00Z')
const message = { id: 'message', title: 'Sessions postponed', undo: { id: 'operation', status: 'available', expiresAt: '2026-10-04T01:00:00Z', count: 3 } }
const show = (onUndo = vi.fn().mockResolvedValue({ status: 'undone' }), data = message) => {
  const view = render(<ActionConfirmationProvider><MessageUndo message={data} timeZone="Asia/Singapore" onUndo={onUndo} /></ActionConfirmationProvider>)
  return { ...view, onUndo }
}
beforeEach(() => { vi.useFakeTimers({ toFake: ['Date', 'setTimeout', 'clearTimeout'] }); vi.setSystemTime(base) })
afterEach(() => { cleanup(); vi.useRealTimers() })
it('shows a prominent Undo and deadline, requires confirmation and prevents duplicate clicks', async () => {
  const { onUndo } = show()
  expect(screen.getByText(/Until/)).toHaveTextContent('04 Oct 2026')
  const button = screen.getByRole('button', { name: 'Undo Sessions postponed' })
  expect(button).toHaveClass('primary-button')
  fireEvent.click(button); fireEvent.click(button)
  expect(screen.getAllByRole('dialog', { name: 'Undo session change?' })).toHaveLength(1)
  expect(screen.getByText(/all 3 affected sessions/)).toBeVisible()
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Undo Change' })))
  expect(onUndo).toHaveBeenCalledExactlyOnceWith('message')
  expect(screen.getByRole('status')).toHaveTextContent('Undone')
})
it('cancels without submitting or changing the deadline', async () => {
  const { onUndo } = show()
  fireEvent.click(screen.getByRole('button', { name: 'Undo Sessions postponed' }))
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Cancel', exact: true })))
  expect(onUndo).not.toHaveBeenCalled(); expect(screen.getByRole('button', { name: 'Undo Sessions postponed' })).toBeEnabled()
})
it('expires at exactly 24 hours while the Message stays open', async () => {
  show(); await act(async () => vi.advanceTimersByTime(86400000))
  expect(screen.getByText('Undo expired')).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Undo Sessions postponed' })).not.toBeInTheDocument()
})
it('refuses confirmation if its 24-hour deadline passed while reviewing', async () => {
  const { onUndo } = show(); fireEvent.click(screen.getByRole('button', { name: 'Undo Sessions postponed' }))
  await act(async () => vi.advanceTimersByTime(86400000))
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Undo Change' })))
  expect(onUndo).not.toHaveBeenCalled(); expect(screen.getByRole('alert')).toHaveTextContent('expired')
})
it('keeps an unavailable Undo visible with its dependency reason', () => {
  show(undefined, { ...message, undo: { ...message.undo, status: 'blocked', reason: 'The session changed again.' } })
  expect(screen.getByRole('button', { name: 'Undo Sessions postponed' })).toBeDisabled()
  expect(screen.getByText('The session changed again.')).toBeVisible()
})
it('preserves retry feedback after failure without claiming the change was undone', async () => {
  const onUndo = vi.fn().mockRejectedValue(new Error('New booking conflicts'))
  show(onUndo); fireEvent.click(screen.getByRole('button', { name: 'Undo Sessions postponed' }))
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Undo Change' })))
  expect(screen.getByRole('alert')).toHaveTextContent('New booking conflicts')
  expect(screen.getByRole('button', { name: 'Undo Sessions postponed' })).toBeEnabled()
  expect(screen.queryByText('Undone')).not.toBeInTheDocument()
})
it('does not submit a confirmation after its owning Message unmounts', async () => {
  function Host({ visible, onUndo }) { return <ActionConfirmationProvider>{visible && <MessageUndo message={message} onUndo={onUndo} />}</ActionConfirmationProvider> }
  const onUndo = vi.fn(); const view = render(<Host visible onUndo={onUndo} />)
  fireEvent.click(screen.getByRole('button', { name: 'Undo Sessions postponed' }))
  view.rerender(<Host visible={false} onUndo={onUndo} />)
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Undo Change' })))
  expect(onUndo).not.toHaveBeenCalled()
})
