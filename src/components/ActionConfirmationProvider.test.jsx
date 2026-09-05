import { useState } from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { ActionConfirmationProvider, useActionConfirmation } from './ActionConfirmationProvider.jsx'
import ConfirmDialog from './ConfirmDialog.jsx'

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
      <ActionConfirmationProvider>
        <ReviewHarness outcomes={outcomes} />
      </ActionConfirmationProvider>,
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
