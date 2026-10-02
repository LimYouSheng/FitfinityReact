import { StrictMode, useState } from 'react'
import { afterEach, expect, it } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
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

it.each([
  { order: 'together', focusLost: false },
  { order: 'parent first', focusLost: false },
  { order: 'together', focusLost: true },
  { order: 'parent first', focusLost: true },
])('returns focus after stacked dialogs close $order with focus lost: $focusLost', async ({ order, focusLost }) => {
  const user = userEvent.setup()
  function ClosingDialogs() {
    const [parent, setParent] = useState(false)
    const [confirmation, setConfirmation] = useState(false)
    return <><button onClick={() => setParent(true)}>Open form</button>
      <ConfirmDialog open={parent} title="Form" confirmLabel="Discard" onConfirm={() => setConfirmation(true)} />
      <ConfirmDialog open={confirmation} title="Discard form changes?" confirmLabel="Discard Changes" onConfirm={() => {
        setParent(false)
        if (order === 'together') setConfirmation(false)
      }}>
        <button onClick={() => setConfirmation(false)}>Finish confirmation</button>
      </ConfirmDialog>
    </>
  }
  render(focusLost ? <ClosingDialogs /> : <StrictMode><ClosingDialogs /></StrictMode>)
  const opener = screen.getByRole('button', { name: 'Open form', exact: true })
  await user.click(opener)
  const discard = within(screen.getByRole('dialog', { name: 'Form', exact: true })).getByRole('button', { name: 'Discard', exact: true })
  if (focusLost) {
    // Model a touch click that blurs the previous control without focusing the button.
    document.activeElement.blur()
    expect(document.activeElement).toBe(document.body)
    fireEvent.click(discard)
  } else await user.click(discard)
  const confirmation = screen.getByRole('dialog', { name: 'Discard form changes?', exact: true })
  fireEvent.click(within(confirmation).getByRole('button', { name: 'Discard Changes', exact: true }))
  expect(screen.queryByRole('dialog', { name: 'Form', exact: true })).not.toBeInTheDocument()
  if (order === 'parent first') {
    expect(confirmation).toContainElement(document.activeElement)
    expect(opener.closest('[inert]')).not.toBeNull()
    expect(document.body.style.position).toBe('fixed')
    await user.click(within(confirmation).getByRole('button', { name: 'Finish confirmation', exact: true }))
  }
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(opener).toHaveFocus()
  expect(opener.closest('[inert]')).toBeNull()
  expect(document.body.style.position).toBe('')
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
