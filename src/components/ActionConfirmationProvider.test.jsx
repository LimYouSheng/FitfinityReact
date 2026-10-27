import { StrictMode, useLayoutEffect, useState } from 'react'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { ActionConfirmationProvider, useActionConfirmation } from './ActionConfirmationProvider.jsx'
import ConfirmDialog from './ConfirmDialog.jsx'
import { PORTAL_SESSION_ENDED } from '../hooks/usePortalData.js'

function ReviewHarness({ outcomes }) {
  const confirmAction = useActionConfirmation()
  const [open, setOpen] = useState(true)

  return (
    <ConfirmDialog
      open={open}
      title="Review change"
      confirmLabel="Review"
      onCancel={() => setOpen(false)}
      onConfirm={async () => {
        setOpen(false)
        outcomes.review = await confirmAction({ title: 'Submit change?', message: 'Confirm the API action.' })
      }}
    />
  )
}

describe('action confirmation', () => {
  it('allows a confirmation to follow a review dialog', async () => {
    const outcomes = {}
    render(
      <StrictMode><ActionConfirmationProvider>
        <ReviewHarness outcomes={outcomes} />
      </ActionConfirmationProvider></StrictMode>,
    )

    expect(document.body.style.position).toBe('fixed')
    expect(document.documentElement.style.overflow).toBe('hidden')
    fireEvent.click(screen.getByRole('button', { name: 'Review' }))
    expect(screen.getByRole('dialog', { name: 'Submit change?' })).toBeVisible()
    expect(document.body.style.position).toBe('fixed')
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }))
    await waitFor(() => expect(outcomes.review).toBe(true))
    await waitFor(() => expect(document.body.style.position).toBe(''))
    expect(document.documentElement.style.overflow).toBe('')
  })
})

afterEach(cleanup)


function Caller({ capture }) {
  const confirm = useActionConfirmation()
  useLayoutEffect(() => { capture.current = confirm }, [capture, confirm])
  return null
}

it('retires a private confirmation and rejects it when its calling screen unmounts', async () => {
  const caller = {}
  const app = visible => <ActionConfirmationProvider>{visible && <Caller capture={caller} />}</ActionConfirmationProvider>
  const view = render(app(true))
  let pending
  act(() => { pending = caller.current({ title: 'Save private record?', message: 'Private reviewed values' }) })
  expect(screen.getByText('Private reviewed values')).toBeVisible()
  view.rerender(app(false))
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(await pending).toBe(false)
})

it('does not reopen a confirmation from a late callback belonging to a retired screen', async () => {
  const caller = {}
  const app = visible => <ActionConfirmationProvider>{visible && <Caller capture={caller} />}</ActionConfirmationProvider>
  const view = render(app(true))
  const retired = caller.current
  view.rerender(app(false))
  let pending
  act(() => { pending = retired({ title: 'Old confirmation', message: 'Old account detail' }) })
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(await pending).toBe(false)
})

it('retiring an older caller cannot dismiss a newer caller confirmation', async () => {
  const first = {}, second = {}
  const app = both => <ActionConfirmationProvider>{both && <Caller capture={first} />}<Caller capture={second} /></ActionConfirmationProvider>
  const view = render(app(true))
  let original, replacement
  act(() => { original = first.current({ title: 'First', message: 'First details' }) })
  act(() => { replacement = second.current({ title: 'Second', message: 'Second details' }) })
  expect(await original).toBe(false)
  view.rerender(app(false))
  expect(screen.getByRole('dialog', { name: 'Second' })).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: 'Confirm', exact: true }))
  expect(await replacement).toBe(true)
})

it('session termination retires a confirmation even when its caller remains mounted', async () => {
  const caller = {}
  render(<ActionConfirmationProvider><Caller capture={caller} /></ActionConfirmationProvider>)
  let pending
  act(() => { pending = caller.current({ title: 'Leave old edit?', message: 'Old account detail' }) })
  act(() => { window.dispatchEvent(new Event(PORTAL_SESSION_ENDED)) })
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(await pending).toBe(false)
})

it('provider teardown resolves a pending decision as cancelled', async () => {
  const caller = {}, outcome = {}
  const view = render(<ActionConfirmationProvider><Caller capture={caller} /></ActionConfirmationProvider>)
  act(() => { void caller.current({ title: 'Pending decision' }).then(value => { outcome.value = value }) })
  view.unmount()
  await waitFor(() => expect(outcome.value).toBe(false))
})

it('an old abort signal cannot dismiss a replacement confirmation', async () => {
  const caller = {}, firstSignal = new AbortController(), nextSignal = new AbortController()
  render(<ActionConfirmationProvider><Caller capture={caller} /></ActionConfirmationProvider>)
  let first, next
  act(() => { first = caller.current({ title: 'First', signal: firstSignal.signal }) })
  act(() => { next = caller.current({ title: 'Next', signal: nextSignal.signal }) })
  expect(await first).toBe(false)
  act(() => firstSignal.abort())
  expect(screen.getByRole('dialog', { name: 'Next' })).toBeVisible()
  act(() => nextSignal.abort())
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(await next).toBe(false)
})

it('an already retired request cannot replace a live confirmation', async () => {
  const caller = {}, retired = new AbortController()
  retired.abort()
  render(<ActionConfirmationProvider><Caller capture={caller} /></ActionConfirmationProvider>)
  let live, rejected
  act(() => { live = caller.current({ title: 'Live request' }) })
  act(() => { rejected = caller.current({ title: 'Retired request', signal: retired.signal }) })
  expect(await rejected).toBe(false)
  expect(screen.getByRole('dialog', { name: 'Live request' })).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: 'Confirm', exact: true }))
  expect(await live).toBe(true)
})
