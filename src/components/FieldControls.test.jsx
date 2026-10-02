import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { useEffect, useState } from 'react'
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import SelectField from './SelectField.jsx'
import Field from './OnboardingField.jsx'
import DateField from './DateField.jsx'
import PortraitOrientation from './PortraitOrientation.jsx'
import SuggestionField from './SuggestionField.jsx'
import AppShell from './AppShell.jsx'
import { ActionConfirmationProvider } from './ActionConfirmationProvider.jsx'
import { EditGuardProvider, useEditGuard } from './EditGuardProvider.jsx'
import ModalPortal from './ModalPortal.jsx'
import { seed } from '../data/seed.js'
import userEvent from '@testing-library/user-event'
import ClientsPage from '../features/clients/ClientsPage.jsx'
import TrainersPage from '../features/trainers/TrainersPage.jsx'

beforeEach(() => {
  vi.stubGlobal('matchMedia', () => ({ matches: false, addEventListener() {}, removeEventListener() {} }))
  window.scrollTo = vi.fn()
})

function EditingShell({ children, modal = false, onOutside = () => {} }) {
  const { setActiveEdit } = useEditGuard()
  useEffect(() => { setActiveEdit('Information'); return () => setActiveEdit(null) }, [setActiveEdit])
  const owner = seed.users.find(user => user.role === 'owner')
  return <AppShell user={owner} userId={owner.id} users={seed.users} messages={seed.messages} route="dashboard" onRoute={() => {}}>
    {modal ? <ModalPortal><div className="modal-backdrop"><section role="dialog" aria-label="Edit information">{children}</section></div></ModalPortal>
      : <section className="editing-section">{children}</section>}
    <button onClick={onOutside}>Blocked outside edit</button>
  </AppShell>
}

const renderFields = (children, props) => render(<ActionConfirmationProvider><EditGuardProvider><EditingShell {...props}>{children}</EditingShell></EditGuardProvider></ActionConfirmationProvider>)

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks() })

it('opens the app option menu, cancels the native picker, chooses with pointer/keyboard and closes outside', async () => {
  function Form({ initial = 'one' }) {
    const [value, setValue] = useState(initial)
    return <><SelectField aria-label="Filter" value={value} onChange={event => setValue(event.target.value)}>
      <option hidden value="retired">Retired</option><option value="one">One</option><option value="two">Two</option><option value="disabled" disabled>Unavailable</option>
    </SelectField><button>Outside</button></>
  }
  const outside = vi.fn()
  renderFields(<Form />, { onOutside: outside })
  const user = userEvent.setup()
  const control = screen.getByRole('combobox', { name: 'Filter' })
  expect(fireEvent.pointerDown(control)).toBe(false)
  expect(screen.queryByRole('listbox')).toBeNull()
  await user.click(control)
  const menu = screen.getByRole('listbox', { name: 'Filter' })
  expect(within(menu).queryByRole('option', { name: 'Retired' })).toBeNull()
  await user.click(within(menu).getByRole('option', { name: 'Two' }))
  expect(control).toHaveValue('two')
  expect(screen.queryByRole('listbox')).toBeNull()
  fireEvent.keyDown(control, { key: 'ArrowUp' })
  fireEvent.keyDown(control, { key: 'Home' })
  fireEvent.keyDown(control, { key: 'Enter' })
  expect(control).toHaveValue('one')
  await user.click(control)
  fireEvent.pointerDown(screen.getByText('Outside'))
  expect(screen.queryByRole('listbox')).toBeNull()
  await user.click(control)
  fireEvent.keyDown(document, { key: 'Escape' })
  expect(screen.queryByRole('listbox')).toBeNull()
  expect(control).toHaveFocus()
  await user.click(screen.getByText('Blocked outside edit'))
  expect(outside).not.toHaveBeenCalled()
  cleanup()
  renderFields(<Form initial="retired" />)
  const period = screen.getByRole('combobox', { name: 'Filter' })
  await user.click(period)
  await user.keyboard('{Enter}')
  expect(period).toHaveValue('one')
  expect(screen.queryByRole('listbox')).toBeNull()
  cleanup()
  function RequiredForm() {
    const [name, setName] = useState('')
    const [phone, setPhone] = useState('')
    const [kind, setKind] = useState('')
    return <><Field label="Required name" required><input value={name} onChange={event => setName(event.target.value)} /></Field>
      <Field label="Phone" required group><div>
        <SelectField aria-label="Country code" required value="+65" onChange={() => {}}><option>+65</option></SelectField>
        <input aria-label="Phone number" required value={phone} onChange={event => setPhone(event.target.value)} />
      </div></Field>
      <Field label="Required kind" required><SelectField value={kind} onChange={event => setKind(event.target.value)}><option value="">Choose</option><option>Coach</option></SelectField></Field>
      <Field label="Zero rate" required><input value={0} onChange={() => {}} /></Field>
      <Field label="Invalid email" required error="Invalid email"><input value="invalid" onChange={() => {}} /></Field></>
  }
  render(<RequiredForm />)
  for (const label of ['Required name', 'Phone number', 'Required kind']) {
    const input = screen.getByLabelText(new RegExp(`^${label}`))
    expect(input).toHaveAttribute('data-required-empty', 'true')
    fireEvent.change(input, { target: { value: label === 'Required kind' ? 'Coach' : 'Entered' } })
    expect(input).not.toHaveAttribute('data-required-empty')
    expect(input).toBeRequired()
    fireEvent.change(input, { target: { value: '' } })
    expect(input).toHaveAttribute('data-required-empty', 'true')
  }
  fireEvent.change(screen.getByLabelText(/^Required name/), { target: { value: '   ' } })
  expect(screen.getByLabelText(/^Required name/)).toHaveAttribute('data-required-empty', 'true')
  expect(screen.getByLabelText('Country code')).not.toHaveAttribute('data-required-empty')
  expect(screen.getByLabelText(/^Zero rate/)).not.toHaveAttribute('data-required-empty')
  expect(screen.getByLabelText(/^Invalid email/)).toHaveAttribute('aria-invalid', 'true')
})

it('uses a compact calendar with ISO values, date limits, clearing and no native date input', async () => {
  function Form() {
    const [value, setValue] = useState('2026-09-11')
    return <Field label="Start date" required><DateField aria-label="Start date" value={value} min="2026-09-10" max="2026-10-15" onChange={event => setValue(event.target.value)} /></Field>
  }
  renderFields(<Form />)
  const user = userEvent.setup()
  const control = screen.getByLabelText('Start date')
  expect(control).toHaveAttribute('type', 'text')
  expect(fireEvent.pointerDown(control)).toBe(false)
  expect(screen.queryByRole('dialog')).toBeNull()
  await user.click(control)
  const calendar = screen.getByRole('dialog', { name: 'Start date calendar' })
  expect(within(calendar).getByRole('button', { name: '09 Sept 2026' })).toBeDisabled()
  await user.click(within(calendar).getByRole('button', { name: '12 Sept 2026' }))
  expect(control).toHaveValue('2026-09-12')
  expect(screen.queryByRole('dialog')).toBeNull()
  fireEvent.keyDown(control, { key: 'ArrowDown' })
  fireEvent.click(screen.getByRole('button', { name: 'Next month' }))
  expect(screen.getByRole('button', { name: '16 Oct 2026' })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'Clear' }))
  expect(control).toHaveValue('')
  expect(control).toHaveAttribute('data-required-empty', 'true')
  fireEvent.change(control, { target: { value: '2026-10-14' } })
  expect(control).toHaveValue('2026-10-14')
  expect(control).not.toHaveAttribute('data-required-empty')
  await user.click(control)
  await user.click(screen.getByLabelText('Calendar picker month'))
  const months = screen.getByRole('listbox', { name: 'Calendar picker month' })
  await user.click(within(months).getByRole('option', { name: 'September' }))
  expect(screen.queryByRole('listbox')).toBeNull()
  await user.click(screen.getByLabelText('Calendar picker year'))
  await user.click(within(screen.getByRole('listbox', { name: 'Calendar picker year' })).getByRole('option', { name: '2026' }))
  await user.click(screen.getByRole('button', { name: '11 Sept 2026' }))
  expect(control).toHaveValue('2026-09-11')
  expect(screen.queryByRole('dialog')).toBeNull()
  cleanup()
  function ModalForm() {
    const [value, setValue] = useState('')
    return <><label>Trainer type<SuggestionField aria-label="Trainer type" value={value} options={['Coach', 'Senior coach']} onChange={event => setValue(event.target.value)} /></label><Form /></>
  }
  renderFields(<ModalForm />, { modal: true })
  const modal = screen.getByRole('dialog', { name: 'Edit information' })
  await user.click(within(modal).getByLabelText('Trainer type'))
  await user.click(screen.getByRole('option', { name: 'Senior coach' }))
  expect(within(modal).getByLabelText('Trainer type')).toHaveValue('Senior coach')
  expect(screen.queryByRole('listbox')).toBeNull()
  await user.click(within(modal).getByLabelText('Start date'))
  await user.click(screen.getByRole('button', { name: '12 Sept 2026' }))
  expect(within(modal).getByLabelText('Start date')).toHaveValue('2026-09-12')
  expect(screen.getAllByRole('dialog')).toHaveLength(1)
})

it.each(['select', 'date', 'suggestion'])('opens a popup %s after a completed tap, leaving a scroll gesture alone', async kind => {
  const changed = vi.fn()
  const controls = {
    select: <SelectField aria-label="Choice" value="one" onChange={changed}><option value="one">One</option><option value="two">Two</option></SelectField>,
    date: <DateField aria-label="Choice" value="2026-10-02" onChange={changed} />,
    suggestion: <SuggestionField aria-label="Choice" value="" options={['One', 'Two']} onChange={changed} />,
  }
  renderFields(controls[kind], { modal: true })
  const user = userEvent.setup()
  const control = screen.getByLabelText('Choice')
  const expanded = () => expect(control).toHaveAttribute('aria-expanded', 'false')
  fireEvent.pointerDown(control, { pointerId: 1, pointerType: 'touch', clientX: 100, clientY: 240 })
  // Editable suggestions can receive focus while a finger is still down.
  if (kind === 'suggestion') fireEvent.focus(control)
  expanded()
  expect(fireEvent.pointerMove(control, { pointerId: 1, pointerType: 'touch', clientX: 100, clientY: 100 })).toBe(true)
  fireEvent.pointerCancel(control, { pointerId: 1, pointerType: 'touch' })
  fireEvent.scroll(control.closest('[role="dialog"]'))
  expanded()
  expect(changed).not.toHaveBeenCalled()
  await user.pointer({ keys: '[TouchA>]', target: control })
  expanded()
  await user.pointer({ keys: '[/TouchA]', target: control })
  expect(control).toHaveAttribute('aria-expanded', 'true')
  expect(document.body.style.position).toBe('fixed')
  fireEvent.keyDown(document, { key: 'Escape' })
  expanded()
  expect(screen.getByRole('dialog', { name: 'Edit information' })).toBeInTheDocument()
})

it.each(['client', 'trainer'])('reopens %s search suggestions on click or typing, without opening on press focus', async kind => {
  const owner = seed.users.find(user => user.role === 'owner')
  render(kind === 'client' ? <ClientsPage user={owner} clients={seed.clients} trainers={seed.trainers} />
    : <TrainersPage trainers={seed.trainers} />)
  const user = userEvent.setup()
  const search = screen.getByLabelText(`Search ${kind}`)
  await user.type(search, kind === 'client' ? 'Amanda' : 'Marcus')
  const menu = screen.getByRole('listbox')
  await user.click(within(menu).getAllByRole('option')[0])
  expect(screen.queryByRole('listbox')).toBeNull()
  fireEvent.pointerDown(search, { pointerType: 'touch' })
  fireEvent.focus(search)
  expect(screen.queryByRole('listbox')).toBeNull()
  fireEvent.pointerCancel(search, { pointerType: 'touch' })
  await user.click(search)
  expect(screen.getByRole('listbox')).toBeVisible()
})

it('requests the installed portrait lock and preserves mounted draft input through unsupported rotation', async () => {
  const orientation = Object.assign(new EventTarget(), { type: 'portrait-primary', lock: vi.fn().mockRejectedValue(new Error('Unsupported')) })
  vi.stubGlobal('screen', { orientation, width: 390, height: 844 })
  vi.stubGlobal('matchMedia', query => ({ matches: ['(pointer: coarse)', '(display-mode: standalone)'].includes(query) }))
  window.scrollTo = vi.fn()
  render(<><PortraitOrientation /><input aria-label="Draft" defaultValue="Keep my draft" /></>)
  await act(async () => {})
  expect(orientation.lock).toHaveBeenCalledWith('portrait')
  const draft = screen.getByLabelText('Draft')
  fireEvent.focus(draft)
  act(() => { orientation.type = 'landscape-primary'; orientation.dispatchEvent(new Event('change')) })
  expect(screen.getByRole('dialog', { name: 'Please rotate your device' })).toBeVisible()
  expect(draft).toHaveValue('Keep my draft')
  expect(draft.closest('[inert]')).not.toBeNull()
  act(() => { orientation.type = 'portrait-primary'; orientation.dispatchEvent(new Event('change')) })
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(draft).toHaveValue('Keep my draft')
  expect(draft.closest('[inert]')).toBeNull()
  await act(async () => {})
  cleanup()
  // A mobile UA alone must not trap a desktop keyboard context behind the portrait dialog.
  orientation.type = 'landscape-primary'
  vi.stubGlobal('matchMedia', () => ({ matches: false }))
  vi.stubGlobal('navigator', { userAgent: 'iPhone', platform: 'iPhone', maxTouchPoints: 0 })
  render(<PortraitOrientation />)
  expect(screen.queryByRole('dialog')).toBeNull()
  cleanup()
  // iPad with a precision pointer still has a touch screen and retains portrait protection.
  vi.stubGlobal('navigator', { userAgent: 'Macintosh', platform: 'MacIntel', maxTouchPoints: 5 })
  render(<PortraitOrientation />)
  expect(screen.getByRole('dialog', { name: 'Please rotate your device' })).toBeVisible()
  await act(async () => {})
})
