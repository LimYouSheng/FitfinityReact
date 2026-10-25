import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { useState } from 'react'
import { PortalData } from '../../hooks/usePortalData.js'
import { ActionConfirmationProvider } from '../../components/ActionConfirmationProvider.jsx'
import ClientEditableText from './ClientEditableText.jsx'

afterEach(cleanup)

it('restores the original draft and reviewed version after remount, and clears only on confirmed save', async () => {
  const drafts = new Map()
  const recovery = { get: key => drafts.get(key), set: (key, value) => drafts.set(key, value), remove: key => drafts.delete(key) }
  const onSave = vi.fn().mockRejectedValueOnce(new Error('Offline')).mockResolvedValueOnce({})
  function Editor() {
    const [editing, setEditing] = useState(false)
    return <ClientEditableText title="Remarks" value="Stored" editable multiline version={3} recoveryKey="client/one/remarks" editing={editing} onBeginEdit={() => setEditing(true)} onEndEdit={() => setEditing(false)} onSave={onSave} />
  }
  const show = () => render(<PortalData.Provider value={{ draftRecovery: recovery }}><ActionConfirmationProvider><Editor /></ActionConfirmationProvider></PortalData.Provider>)
  const first = show()
  fireEvent.click(screen.getByRole('button', { name: 'Edit', exact: true }))
  fireEvent.change(screen.getByRole('textbox', { name: 'Remarks' }), { target: { value: 'Unsaved private draft' } })
  first.unmount()
  show()
  expect(screen.getByRole('status')).toHaveTextContent('unsaved draft')
  fireEvent.click(screen.getByRole('button', { name: 'Edit', exact: true }))
  expect(screen.getByRole('textbox', { name: 'Remarks' })).toHaveValue('Unsaved private draft')
  for (let attempt = 0; attempt < 2; attempt++) {
    fireEvent.click(screen.getByRole('button', { name: 'Save', exact: true }))
    await act(async () => { fireEvent.click(await screen.findByRole('button', { name: 'Save Changes', exact: true })) })
    if (!attempt) expect(screen.getByRole('textbox', { name: 'Remarks' })).toHaveValue('Unsaved private draft')
  }
  await waitFor(() => expect(screen.queryByRole('textbox')).not.toBeInTheDocument())
  expect(onSave).toHaveBeenLastCalledWith('Unsaved private draft', { expectedVersion: 3 })
  expect(drafts.size).toBe(0)
})
