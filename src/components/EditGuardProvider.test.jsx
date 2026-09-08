import { useEffect } from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { ActionConfirmationProvider } from './ActionConfirmationProvider.jsx'
import { EditGuardProvider, useEditGuard } from './EditGuardProvider.jsx'

function NavigationHarness({ destinations }) {
  const { guardNavigation, setActiveEdit } = useEditGuard()

  useEffect(() => {
    setActiveEdit('Trainer rates')
  }, [setActiveEdit])

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
