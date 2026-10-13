import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { assessmentForm } from '../../app/assessmentForms.js'
import { ActionConfirmationProvider } from '../../components/ActionConfirmationProvider.jsx'
import { assessmentRecord } from '../../services/apiAssessmentRecords.js'
import { assessmentRevision } from '../../test/assessmentApi.js'
import { directoryId } from '../../test/directory.js'
import AssessmentRecordDialog from './AssessmentRecordDialog.jsx'

afterEach(cleanup)
const definition = assessmentForm('balance')
const person = { id: directoryId(3), version: 4, name: 'Current client', birthday: '1990-01-01' }
function show(props = {}) {
  const callbacks = { onSave: vi.fn().mockResolvedValue({}), onClose: vi.fn(), onSaved: vi.fn(), onEditChange: vi.fn(), ...props }
  render(<ActionConfirmationProvider><AssessmentRecordDialog definition={definition} person={person}
    businessDate="2026-10-13" viewer={{ name: 'Current owner' }} timeZone="Asia/Singapore" editable services={{}} {...callbacks} /></ActionConfirmationProvider>)
  return callbacks
}

it('explicitly saves an empty durable draft with the reviewed person', async () => {
  const actions = show()
  fireEvent.click(screen.getByRole('button', { name: 'Save Draft', exact: true }))
  await waitFor(() => expect(actions.onSaved).toHaveBeenCalledTimes(1))
  expect(actions.onSave.mock.calls[0][0]).toMatchObject({ personId: person.id, expectedPersonVersion: 4, event: 'draft', formId: 'balance', record: { answers: {} } })
  expect(actions.onSave.mock.calls[0][0]).not.toHaveProperty('assessmentId')
})

it('requires a completion answer and preserves a measured zero', async () => {
  const actions = show()
  fireEvent.click(screen.getByRole('button', { name: 'Complete Assessment' }))
  expect(actions.onSave).not.toHaveBeenCalled()
  expect(screen.getByRole('alert').textContent).toContain('Record at least one answer')
  fireEvent.change(screen.getByLabelText('Eyes open — trial 1 (seconds)', { exact: true }), { target: { value: '0' } })
  fireEvent.click(screen.getByRole('button', { name: 'Complete Assessment' }))
  await waitFor(() => expect(actions.onSaved).toHaveBeenCalledTimes(1))
  expect(actions.onSave.mock.calls[0][0]).toMatchObject({ event: 'completed', record: { answers: { eyes_open_1: 0 } } })
})

it('views historical identity then starts a blank reviewed reassessment without changing it', async () => {
  const record = assessmentRecord(assessmentRevision({ client_name: 'Original client' }))
  const actions = show({ record })
  expect(screen.getAllByText('Original client').length).toBeGreaterThan(0)
  expect(screen.queryByRole('button', { name: 'Complete Assessment' })).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Start Reassessment', exact: true }))
  const confirmation = await screen.findByRole('dialog', { name: 'Start a new Static Balance assessment?' })
  fireEvent.click(within(confirmation).getByRole('button', { name: 'Start Reassessment' }))
  const answer = await screen.findByRole('spinbutton', { name: 'Eyes open — trial 1 (seconds)', exact: true })
  expect(answer.value).toBe('')
  fireEvent.change(answer, { target: { value: '3' } })
  fireEvent.click(screen.getByRole('button', { name: 'Complete Assessment' }))
  await waitFor(() => expect(actions.onSaved).toHaveBeenCalled())
  expect(actions.onSave.mock.calls[0][0]).toMatchObject({ previousAssessmentId: record.assessmentId, expectedPreviousVersion: record.revision, record: { answers: { eyes_open_1: 3 } } })
  expect(record.answers).toEqual({ eyes_open_1: 0 })
})

it('resumes a saved draft on the same occasion and version', async () => {
  const record = assessmentRecord(assessmentRevision({ revision: 1, previous_revision: null, status: 'draft', event: 'draft', answers: {} }))
  const actions = show({ record })
  fireEvent.click(screen.getByRole('button', { name: 'Resume Draft' }))
  fireEvent.click(screen.getByRole('button', { name: 'Save Draft', exact: true }))
  await waitFor(() => expect(actions.onSaved).toHaveBeenCalled())
  expect(actions.onSave.mock.calls[0][0]).toMatchObject({ assessmentId: record.assessmentId, expectedVersion: 1, event: 'draft' })
  expect(actions.onSave.mock.calls[0][0]).not.toHaveProperty('previousAssessmentId')
})

it('keeps inactive records readable without a resume or reassessment action', () => {
  show({ record: assessmentRecord(assessmentRevision()), editable: false })
  expect(screen.getByRole('button', { name: 'View Assessment History' })).toBeTruthy()
  expect(screen.queryByRole('button', { name: 'Start Reassessment' })).toBeNull()
  expect(screen.queryByRole('button', { name: 'Complete Assessment' })).toBeNull()
})

it('freezes an uncertain draft and checks its original draft event and answers', async () => {
  const onSave = vi.fn().mockRejectedValueOnce(Object.assign(new Error('Unknown outcome'), { status: 503 })).mockResolvedValue({})
  const actions = show({ onSave })
  fireEvent.click(screen.getByRole('button', { name: 'Save Draft', exact: true }))
  const check = await screen.findByRole('button', { name: 'Check Assessment Save' })
  expect(screen.queryByRole('spinbutton')).toBeNull()
  expect(screen.getByRole('button', { name: 'Save Draft', exact: true }).disabled).toBe(true)
  fireEvent.click(check)
  await waitFor(() => expect(actions.onSaved).toHaveBeenCalled())
  expect(onSave.mock.calls[1][0]).toEqual(onSave.mock.calls[0][0])
  expect(onSave.mock.calls[1][0].event).toBe('draft')
})

it('opens occasion and immutable revision history without exposing editing controls', async () => {
  const record = assessmentRecord(assessmentRevision({ client_name: 'Original client' }))
  const services = { readAssessmentHistory: vi.fn().mockResolvedValue({ items: [record], offset: 0, hasMore: false }) }
  show({ record, services })
  fireEvent.click(screen.getByRole('button', { name: 'View Assessment History' }))
  fireEvent.click(await screen.findByRole('button', { name: 'View Revisions' }))
  await waitFor(() => expect(services.readAssessmentHistory).toHaveBeenLastCalledWith({ personId: person.id, formId: 'balance', assessmentId: record.assessmentId, offset: 0 }))
  fireEvent.click(await screen.findByRole('button', { name: 'View Saved Form' }))
  expect(screen.getAllByText('Original client').length).toBeGreaterThan(0)
  expect(screen.queryByRole('button', { name: 'Complete Assessment' })).toBeNull()
})
