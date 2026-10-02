import { useState } from 'react'
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, within, waitFor } from '@testing-library/react'
import { ActionConfirmationProvider } from '../../components/ActionConfirmationProvider.jsx'
import ClientAssessments from './ClientAssessments.jsx'
import { businessClock } from '../../app/clock.js'
import { saveAssessment } from '../../app/assessmentForms.js'

afterEach(() => { cleanup(); vi.restoreAllMocks() })
function Harness({ readOnly = false, initial }) {
  const [people, setPeople] = useState(initial ?? [
    { name: 'Alpha', birthday: '1990-01-02', assessments: {} }, { name: 'Beta', birthday: '1992-03-04', assessments: {} },
  ])
  const [activePerson, setActivePerson] = useState(0)
  return <ActionConfirmationProvider><ClientAssessments people={people} activePerson={activePerson} setActivePerson={setActivePerson}
    onChange={setPeople} readOnly={readOnly} assessor="Signed-in Owner" timeZone="Asia/Singapore" /></ActionConfirmationProvider>
}
const card = name => within(document.querySelector('.assessment-grid')).getByRole('button', { name, exact: true })
const actions = () => within(document.querySelector('.assessment-dialog .modal-actions'))
const open = () => fireEvent.click(card('Static Balance — Not filled'))
const fill = () => fireEvent.change(screen.getByLabelText('Eyes open — trial 1 (seconds)'), { target: { value: '0' } })

it('starts with eleven grey cards, saves directly to green, restores focus and reopens exact answers', () => {
  render(<Harness />)
  expect(within(document.querySelector('.assessment-grid')).getAllByRole('button', { name: /— Not filled$/ })).toHaveLength(11)
  // fireEvent.click leaves focus unchanged, matching touch browsers that do not focus a tapped button.
  expect(card('Static Balance — Not filled')).not.toHaveFocus(); open(); fill()
  const paper = screen.getByRole('region', { name: 'Paper page 1' })
  expect(within(paper).getAllByRole('spinbutton')).toHaveLength(6)
  expect(paper.querySelector('img')).toHaveAttribute('src', '/assessment-forms/pages/balance-1.svg')
  expect(paper).toHaveAttribute('data-no-swipe')
  expect(paper.querySelector('.assessment-paper-page')).toHaveStyle({ aspectRatio: '612 / 792' })
  expect(screen.getByRole('link', { name: /Open original PDF/ })).toHaveAttribute('href', '/assessment-forms/35_Static_Balance_Assessment_Form.pdf')
  fireEvent.click(actions().getByRole('button', { name: 'Save', exact: true }))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  const saved = card('Static Balance — Filled')
  expect(saved).toHaveClass('is-filled'); expect(saved).toHaveFocus()
  expect(screen.getByText('1 of 11 filled')).toBeVisible()
  fireEvent.click(saved)
  expect(screen.getByLabelText('Eyes open — trial 1 (seconds)')).toHaveValue(0)
  expect(screen.getByLabelText('Eyes closed — trial 1 (seconds)')).toHaveValue(null)
  fireEvent.click(actions().getByRole('button', { name: 'Cancel', exact: true }))
  fireEvent.click(card('Lifestyle & Health History — Not filled'))
  const pages = document.querySelectorAll('.assessment-paper-scroll')
  expect(pages).toHaveLength(4)
  const health = within(pages[0])
  expect(health.getByLabelText('Client name')).toHaveTextContent('Alpha')
  expect(health.getByLabelText('Assessment date').tagName).toBe('SPAN')
  expect(health.getByLabelText('Date of birth')).toHaveTextContent('1990-01-02')
  for (const label of ['Client name', 'Date of birth', 'Assessment date']) {
    expect(health.getByLabelText(label).parentElement).toHaveClass('is-metadata')
  }
  fireEvent.click(health.getByLabelText('Asthma', { exact: true }))
  const alcohol = within(pages[2])
  fireEvent.click(alcohol.getByLabelText('Alcohol use? — Yes', { exact: true }))
  fireEvent.click(alcohol.getByLabelText('Alcohol use? — No', { exact: true }))
  expect(alcohol.getByLabelText('Alcohol use? — Yes', { exact: true })).not.toBeChecked()
  // Editing a different page must preserve this page's answers and focused control.
  const otherConditions = health.getByLabelText('Other conditions')
  otherConditions.focus()
  fireEvent.change(otherConditions, { target: { value: 'Owner notes' } })
  expect(otherConditions).toHaveFocus()
  expect(health.getByLabelText('Asthma', { exact: true })).toBeChecked()
  fireEvent.click(actions().getByRole('button', { name: 'Save', exact: true }))
  fireEvent.click(card('Lifestyle & Health History — Filled'))
  expect(screen.getByLabelText('Asthma', { exact: true })).toBeChecked()
  expect(screen.getByLabelText('Alcohol use? — No', { exact: true })).toBeChecked()
  expect(screen.getByLabelText('Other conditions')).toHaveValue('Owner notes')
})

it('locks prefilled headers, blocks blank balance Save and allows an explicitly saved unchecked hurdle checklist', () => {
  render(<Harness />); open()
  const details = document.querySelector('.assessment-metadata')
  for (const value of ['Alpha', '1990-01-02', businessClock().date, 'Signed-in Owner']) expect(within(details).getByText(value)).toBeVisible()
  expect(details.querySelectorAll('input, textarea, select, [contenteditable]')).toHaveLength(0)
  fireEvent.click(actions().getByRole('button', { name: 'Save', exact: true }))
  expect(screen.getByRole('alert')).toHaveTextContent('at least one answer')
  expect(screen.getByRole('dialog', { name: 'Static Balance' })).toBeVisible()
  fireEvent.click(actions().getByRole('button', { name: 'Cancel', exact: true }))
  fireEvent.click(card('Hurdle Step Screen — Not filled'))
  const dialog = document.querySelector('.assessment-dialog')
  expect(dialog.querySelectorAll('input[type="checkbox"]')).toHaveLength(6)
  expect(dialog.querySelector('textarea, input:not([type="checkbox"]), details')).toBeNull()
  expect(within(dialog).queryByText('Additional observations')).not.toBeInTheDocument()
  expect([...dialog.querySelectorAll('input')].every(input => !input.checked)).toBe(true)
  fireEvent.click(actions().getByRole('button', { name: 'Save', exact: true }))
  expect(card('Hurdle Step Screen — Filled')).toHaveFocus()
  fireEvent.click(card('Hurdle Step Screen — Filled'))
  expect([...document.querySelectorAll('.assessment-dialog input')].every(input => !input.checked)).toBe(true)
})

it('keeps couple records and their prefilled identities independent', () => {
  render(<Harness />); open(); fill(); fireEvent.click(actions().getByRole('button', { name: 'Save', exact: true }))
  fireEvent.click(screen.getByRole('button', { name: 'Client 2' }))
  expect(screen.getAllByRole('button', { name: /— Not filled$/ })).toHaveLength(11)
  open()
  expect(within(document.querySelector('.assessment-metadata')).getByText('Beta')).toBeVisible()
  expect(within(document.querySelector('.assessment-metadata')).getByText('1992-03-04')).toBeVisible()
  expect(screen.getByLabelText('Eyes open — trial 1 (seconds)')).toHaveValue(null)
  fireEvent.click(actions().getByRole('button', { name: 'Cancel', exact: true }))
  fireEvent.click(screen.getByRole('button', { name: 'Client 1' }))
  expect(card('Static Balance — Filled')).toBeVisible()
})

it('Escape offers discard confirmation; staying retains changes and discard leaves the card grey', async () => {
  render(<Harness />); open(); fill()
  fireEvent.keyDown(screen.getByLabelText('Eyes open — trial 1 (seconds)'), { key: 'Escape' })
  let dialog = screen.getByRole('dialog', { name: 'Discard form changes?' })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
  await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Discard form changes?' })).not.toBeInTheDocument())
  expect(screen.getByLabelText('Eyes open — trial 1 (seconds)')).toHaveValue(0)
  fireEvent.click(screen.getByRole('button', { name: 'Close dialog' }))
  dialog = screen.getByRole('dialog', { name: 'Discard form changes?' })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Discard Changes' }))
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(card('Static Balance — Not filled')).toHaveFocus()
})

it('displays saved answers and original headers on profiles without introducing a reassessment edit action', () => {
  const balance = saveAssessment('balance', { date: '2026-09-01', assessor: 'Original Assessor', answers: { eyes_open_1: 0, notes: 'Earlier narrative retained' } })
  render(<Harness readOnly initial={[{ name: 'Alpha', assessments: { balance } }]} />)
  expect(card('Single-Leg Assessment — Not filled')).toBeDisabled()
  fireEvent.click(card('Static Balance — Filled'))
  expect(screen.getByText('0')).toBeVisible()
  expect(within(document.querySelector('.assessment-metadata')).getByText('2026-09-01')).toBeVisible()
  expect(screen.getByText('Original Assessor')).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Save', exact: true })).not.toBeInTheDocument()
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  expect(screen.queryByText('Earlier narrative retained')).not.toBeInTheDocument()
  expect(balance.answers.notes).toBe('Earlier narrative retained')
})


it('profile Save awaits persistence, retains a failed draft and opens completed forms read-only', async () => {
  let reject, resolve
  const persist = vi.fn().mockImplementationOnce(() => new Promise((_, fail) => { reject = fail }))
    .mockImplementationOnce(() => new Promise(done => { resolve = done }))
  const onEdit = vi.fn()
  function Profile() {
    const [people, setPeople] = useState([{ name: 'Alpha', birthday: '1990-01-02', assessments: {} }])
    return <ActionConfirmationProvider><ClientAssessments people={people} activePerson={0} setActivePerson={() => {}}
      readOnly fillUnfilled assessor="Owner" timeZone="Asia/Singapore" onEditChange={onEdit}
      onSaveForm={async (index, formId, record) => {
        await persist(index, formId, record)
        setPeople([{ ...people[0], assessments: { [formId]: record } }])
      }} /></ActionConfirmationProvider>
  }
  render(<Profile />); open(); fill()
  expect(onEdit).toHaveBeenLastCalledWith(true)
  expect(screen.queryByText(/until you select Create Client/)).not.toBeInTheDocument()
  fireEvent.click(actions().getByRole('button', { name: 'Save', exact: true }))
  expect(actions().getByRole('button', { name: 'Saving…' })).toBeDisabled()
  fireEvent.click(actions().getByRole('button', { name: 'Cancel', exact: true }))
  expect(screen.getByRole('dialog', { name: 'Static Balance' })).toBeVisible()
  reject(new Error('Storage unavailable'))
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Storage unavailable'))
  expect(screen.getByLabelText('Eyes open — trial 1 (seconds)')).toHaveValue(0)
  fireEvent.click(actions().getByRole('button', { name: 'Save', exact: true }))
  resolve()
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(card('Static Balance — Filled')).toHaveFocus()
  expect(onEdit).toHaveBeenLastCalledWith(false)
  fireEvent.click(card('Static Balance — Filled'))
  expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Save', exact: true })).not.toBeInTheDocument()
  expect(screen.getByLabelText('Eyes open — trial 1 (seconds)')).toHaveTextContent('0')
  expect(persist).toHaveBeenCalledTimes(2)
})
