import { mockPolicy } from '../../data/mockPolicy.js'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import ExerciseNamePicker from './ExerciseNamePicker.jsx'
import ExercisePlanEditor from './ExercisePlanEditor.jsx'
import { ActionConfirmationProvider } from '../../components/ActionConfirmationProvider.jsx'
afterEach(cleanup)
const catalog = [{ id: 'a', name: 'New movement', status: 'active', category: 'Core' }, { id: 'b', name: 'Historical movement', status: 'inactive', category: 'Core' }]
it('offers the managed active exercises while retaining Custom Exercise first', () => {
  const choose = vi.fn()
  render(<ExerciseNamePicker catalog={catalog} index={1} name="" choice="" onChoose={choose} onCustomName={vi.fn()} />)
  fireEvent.click(screen.getByRole('combobox'))
  expect(screen.getAllByRole('button').map(button => button.textContent)).toEqual(['Custom Exercise', 'New movement'])
  fireEvent.click(screen.getByRole('button', { name: 'New movement' })); expect(choose).toHaveBeenCalledWith('New movement')
})
it('keeps a saved inactive exercise name when editing another plan field', async () => {
  const onSave = vi.fn().mockResolvedValue(undefined)
  render(<ActionConfirmationProvider><ExercisePlanEditor defaults={mockPolicy.exerciseDefaults} catalog={catalog} items={[{ id: 'old', name: 'Historical movement', weight: '10 kg', reps: '8', rounds: '2', rest: '60 sec' }]} editing canEdit onSave={onSave} onEndEdit={vi.fn()} /></ActionConfirmationProvider>)
  expect(screen.getByRole('combobox')).toHaveTextContent('Historical movement')
  fireEvent.change(screen.getByLabelText('Exercise 1 weight'), { target: { value: '12 kg' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save', exact: true }))
  fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Save Plan' }))
  await waitFor(() => expect(onSave).toHaveBeenCalledWith([expect.objectContaining({ id: 'old', name: 'Historical movement', weight: '12 kg' })]))
})
