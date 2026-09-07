import { StrictMode, useState } from 'react'
import { afterEach, expect, it } from 'vitest'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ConfirmDialog from './ConfirmDialog.jsx'
import { NotificationProvider, useNotifications } from './NotificationProvider.jsx'

function Harness() {
  const [open, setOpen] = useState(false)
  const [nested, setNested] = useState(false)
  const { notify } = useNotifications()
  return <><button onClick={() => setOpen(true)}>Open review</button><input aria-label="Background" />
    <ConfirmDialog open={open} title="Review" confirmLabel="Next" onCancel={() => setOpen(false)} onConfirm={() => setNested(true)}>
      <button onClick={() => notify({ tone: 'error', message: 'Review remains open.' })}>Show banner</button>
    </ConfirmDialog>
    <ConfirmDialog open={nested} title="Confirm review" onCancel={() => setNested(false)} onConfirm={() => setNested(false)} />
  </>
}
const renderHarness = () => render(<StrictMode><NotificationProvider><Harness /></NotificationProvider></StrictMode>)
afterEach(cleanup)

it('focuses a modal, contains Tab and Shift-Tab, isolates the page and restores its trigger', async () => {
  const user = userEvent.setup()
  renderHarness()
  const opener = screen.getByRole('button', { name: 'Open review' })
  await user.click(opener)
  const dialog = screen.getByRole('dialog', { name: 'Review', exact: true })
  expect(dialog).toContainElement(document.activeElement)
  expect(opener.closest('[inert]')).not.toBeNull()
  await user.tab({ shift: true })
  expect(within(dialog).getByRole('button', { name: 'Next' })).toHaveFocus()
  await user.tab()
  expect(within(dialog).getByRole('button', { name: 'Close dialog' })).toHaveFocus()
  await user.click(within(dialog).getByRole('button', { name: 'Cancel' }))
  expect(opener).toHaveFocus()
  expect(opener.closest('[inert]')).toBeNull()
  expect(document.body.style.position).toBe('')
})

it('isolates nested confirmations and restores the parent modal without releasing its scroll lock', async () => {
  const user = userEvent.setup()
  renderHarness()
  await user.click(screen.getByRole('button', { name: 'Open review' }))
  const review = screen.getByRole('dialog', { name: 'Review', exact: true })
  const next = within(review).getByRole('button', { name: 'Next' })
  await user.click(next)
  const confirmation = screen.getByRole('dialog', { name: 'Confirm review', exact: true })
  expect(review.closest('[inert]')).not.toBeNull()
  expect(confirmation).toContainElement(document.activeElement)
  await user.click(within(confirmation).getByRole('button', { name: 'Cancel' }))
  expect(review.closest('[inert]')).toBeNull()
  expect(next).toHaveFocus()
  expect(document.body.style.position).toBe('fixed')
})

it('keeps notification dismissal reachable and returns focus to the open modal when the banner disappears', async () => {
  const user = userEvent.setup()
  renderHarness()
  await user.click(screen.getByRole('button', { name: 'Open review' }))
  const review = screen.getByRole('dialog', { name: 'Review', exact: true })
  await user.click(within(review).getByRole('button', { name: 'Show banner' }))
  const dismiss = screen.getByRole('button', { name: 'Dismiss notification' })
  expect(dismiss.closest('[inert]')).toBeNull()
  within(review).getByRole('button', { name: 'Next' }).focus()
  await user.tab()
  expect(dismiss).toHaveFocus()
  await user.tab()
  expect(within(review).getByRole('button', { name: 'Close dialog' })).toHaveFocus()
  await user.click(dismiss)
  await waitFor(() => expect(review).toContainElement(document.activeElement))
  expect(review).toBeInTheDocument()
})
