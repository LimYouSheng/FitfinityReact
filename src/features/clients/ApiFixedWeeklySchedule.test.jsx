import { useEffect, useState } from 'react'
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { ActionConfirmationProvider } from '../../components/ActionConfirmationProvider.jsx'
import { EditGuardProvider, useEditGuard } from '../../components/EditGuardProvider.jsx'
import { weeklyInput, weeklyReview, weeklyResult } from '../../test/clientWeeklySchedule.js'
import { weeklySlots } from '../../services/apiClientWeeklySchedule.js'
import ApiFixedWeeklySchedule from './ApiFixedWeeklySchedule.jsx'
afterEach(cleanup)
function Harness({ workflow }) {
  const [editing, setEditing] = useState(false)
  const { setActiveEdit, guardNavigation } = useEditGuard()
  useEffect(() => { setActiveEdit(editing ? 'Weekly schedule' : null) }, [editing, setActiveEdit])
  return <ApiFixedWeeklySchedule client={{ fixedWeeklySchedule: weeklySlots(weeklyReview()) }} workflow={{ ...workflow, saved: () => guardNavigation(workflow.saved) }} editable editing={editing} onEditing={setEditing} />
}
const workflowFor = patch => ({ review: vi.fn().mockResolvedValue({ reviewed: weeklyReview(), slots: weeklySlots(weeklyReview()), uncertain: false }), preview: vi.fn().mockResolvedValue({ outcome: 'applied', updatedSessions: 1 }), save: vi.fn().mockResolvedValue(weeklyResult()), saved: vi.fn().mockResolvedValue({ refreshed: true }), ...patch })
const show = workflow => render(<ActionConfirmationProvider><EditGuardProvider><Harness workflow={workflow} /></EditGuardProvider></ActionConfirmationProvider>)
async function confirm() {
  fireEvent.click(screen.getByRole('button', { name: 'Edit', exact: true }))
  fireEvent.change(await screen.findByLabelText('Monday from'), { target: { value: '12:00' } })
  fireEvent.change(screen.getByLabelText('Monday to'), { target: { value: '13:00' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save', exact: true }))
  const dialog = await screen.findByRole('dialog', { name: 'Save fixed weekly schedule?' })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Save Schedule', exact: true }))
}
it('previews before confirmation, releases editing before refresh and permits a fresh review', async () => {
  const workflow = workflowFor(); show(workflow); await confirm()
  await waitFor(() => expect(workflow.saved).toHaveBeenCalledTimes(1))
  expect(workflow.preview).toHaveBeenCalledWith({ reviewed: weeklyReview(), slots: weeklyInput().slots })
  expect(workflow.save).toHaveBeenCalledWith({ reviewed: weeklyReview(), slots: weeklyInput().slots })
  expect(screen.queryByRole('dialog')).toBeNull()
  fireEvent.click(await screen.findByRole('button', { name: 'Edit', exact: true }))
  await waitFor(() => expect(workflow.review).toHaveBeenCalledTimes(2))
  expect(workflow.save).toHaveBeenCalledTimes(1)
})
it('freezes uncertain times and explicitly checks the original intent without previewing again', async () => {
  const workflow = workflowFor({ save: vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValue(weeklyResult()) }); show(workflow); await confirm()
  const check = await screen.findByRole('button', { name: 'Check Schedule' })
  expect(screen.getByLabelText('Monday from')).toBeDisabled()
  fireEvent.click(check)
  await waitFor(() => expect(workflow.saved).toHaveBeenCalledTimes(1))
  expect(workflow.save.mock.calls[1]).toEqual(workflow.save.mock.calls[0])
  expect(workflow.preview).toHaveBeenCalledTimes(1)
})
it('keeps a confirmed save after failed refresh and never invites another write', async () => {
  const workflow = workflowFor({ saved: vi.fn().mockRejectedValue(new Error('refresh unavailable')) }); show(workflow); await confirm()
  await waitFor(() => expect(workflow.saved).toHaveBeenCalledTimes(1))
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(screen.queryByRole('button', { name: 'Edit', exact: true })).toBeNull()
  expect(workflow.save).toHaveBeenCalledTimes(1)
})
