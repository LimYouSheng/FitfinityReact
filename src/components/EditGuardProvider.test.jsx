import { useEffect } from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { ActionConfirmationProvider } from './ActionConfirmationProvider.jsx'
import { EditGuardProvider, useEditGuard } from './EditGuardProvider.jsx'

function NavigationHarness({ destinations, edit = 'Trainer rates' }) {
  const { guardNavigation, setActiveEdit } = useEditGuard()

  useEffect(() => {
    setActiveEdit(edit)
  }, [setActiveEdit, edit])

  return (
    <>
      <button type="button" onClick={() => guardNavigation(() => destinations.push('clients'))}>Clients</button>
      <button type="button" onClick={() => guardNavigation(() => destinations.push('sessions'))}>Sessions</button>
    </>
  )
}

describe('edit navigation guard', () => {
  it('accepts only the first navigation request while its confirmation is open', async () => {
    const destinations = []
    render(
      <ActionConfirmationProvider>
        <EditGuardProvider>
          <NavigationHarness destinations={destinations} />
        </EditGuardProvider>
      </ActionConfirmationProvider>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Clients' }))
    fireEvent.click(screen.getByRole('button', { name: 'Sessions' }))

    expect(screen.getAllByRole('dialog', { name: 'Leave this edit?' })).toHaveLength(1)
    fireEvent.click(screen.getByRole('button', { name: 'Leave Without Saving' }))
    await waitFor(() => expect(destinations).toEqual(['clients']))
  })
})

afterEach(cleanup)


it.each([null, 'Replacement record'])('cancels the old navigation decision when its edit becomes %s', async edit => {
  const destinations = []
  const app = active => <ActionConfirmationProvider><EditGuardProvider><NavigationHarness destinations={destinations} edit={active} /></EditGuardProvider></ActionConfirmationProvider>
  const view = render(app('Original record'))
  fireEvent.click(screen.getByRole('button', { name: 'Clients', exact: true }))
  expect(screen.getByRole('dialog', { name: 'Leave this edit?' })).toBeVisible()
  view.rerender(app(edit))
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  expect(destinations).toEqual([])
  fireEvent.click(screen.getByRole('button', { name: 'Sessions', exact: true }))
  if (edit) {
    expect(screen.getByRole('dialog')).toHaveTextContent('Replacement record')
    fireEvent.click(screen.getByRole('button', { name: 'Leave Without Saving', exact: true }))
  }
  await waitFor(() => expect(destinations).toEqual(['sessions']))
})
