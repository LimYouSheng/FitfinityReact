import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import OnboardingReview from './OnboardingReview.jsx'

afterEach(cleanup)
const sections = [
  { key: 'general', title: 'General Information', groups: [{ title: 'Client 1', rows: [{ label: 'Name', value: 'Alpha' }] }, { title: 'Client 2', rows: [{ label: 'Name', value: 'Beta' }] }] },
  { key: 'rates', title: 'Training & Rates', groups: [{ rows: [{ label: 'Peak rate', value: 'S$80.00' }] }] },
]

describe('shared form summary', () => {
  it('shows each section and each person without rendering editable inputs', () => {
    const { container } = render(<OnboardingReview sections={sections} onEdit={() => {}} />)
    expect(screen.getByRole('region', { name: 'General Information' })).toBeVisible()
    expect(screen.getByRole('heading', { name: 'Client 1' })).toBeVisible()
    expect(screen.getByRole('heading', { name: 'Client 2' })).toBeVisible()
    expect(screen.getByText('Alpha')).toBeVisible()
    expect(screen.getByText('Beta')).toBeVisible()
    expect(container.querySelectorAll('input,select,textarea')).toHaveLength(0)
  })
  it('routes each named Edit action to its own section without submitting the parent form', () => {
    const onEdit = vi.fn(); const onOpen = vi.fn(); const onSubmit = vi.fn(event => event.preventDefault())
    const assessment = { key: 'assessments', title: 'Health & Assessments', layout: 'assessments', groups: ['Alpha', 'Beta'].map((title, personIndex) => ({ title,
      rows: [{ label: 'Static Balance', value: 'Filled', detail: '18 Sep 2026 · Owner', open: { personIndex, formId: 'balance' } }, { label: 'Hurdle Step', value: 'Not filled' }] })) }
    render(<form onSubmit={onSubmit}><OnboardingReview sections={[...sections, assessment]} onEdit={onEdit} onOpen={onOpen} /></form>)
    fireEvent.click(screen.getByRole('button', { name: 'Edit General Information' }))
    fireEvent.click(screen.getByRole('button', { name: 'Edit Training & Rates' }))
    expect(onEdit.mock.calls).toEqual([['general'], ['rates']])
    for (const person of ['Alpha', 'Beta']) {
      const list = screen.getByRole('list', { name: `Assessment summary for ${person}` })
      expect(within(list).getAllByRole('listitem')).toHaveLength(2)
      expect(within(list).getByText('Filled')).toHaveClass('is-filled')
      expect(within(list).getByText('Not filled')).not.toHaveClass('is-filled')
      expect(within(list).getByText('18 Sep 2026 · Owner')).toBeVisible()
      const button = screen.getByRole('button', { name: `View Static Balance for ${person}` })
      fireEvent.click(button)
      expect(button).toHaveFocus()
    }
    expect(onOpen.mock.calls).toEqual([[{ personIndex: 0, formId: 'balance' }], [{ personIndex: 1, formId: 'balance' }]])
    expect(screen.queryByRole('button', { name: /View Hurdle/ })).not.toBeInTheDocument()
    expect(onSubmit).not.toHaveBeenCalled()
  })
  it('renders entered text safely as text rather than HTML', () => {
    const value = '<img src=x onerror=alert(1)>\nSecond line'
    const { container } = render(<OnboardingReview sections={[{ key: 'notes', title: 'Notes', groups: [{ rows: [{ label: 'Notes', value }] }] }]} onEdit={() => {}} />)
    expect(container.querySelector('dd').textContent).toBe(value)
    expect(container.querySelector('img')).toBeNull()
  })
  it('keeps every Edit action disabled by the owning form while creation is pending', () => {
    render(<fieldset disabled><OnboardingReview sections={sections} onEdit={() => {}} /></fieldset>)
    for (const section of sections) {
      expect(within(screen.getByRole('region', { name: section.title })).getByRole('button')).toBeDisabled()
    }
  })
})
