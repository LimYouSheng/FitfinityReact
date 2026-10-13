import { expect, it, vi } from 'vitest'
import { createCreationState } from './creationState.js'

it('retains one private form through subscriptions and rejects late retired writes', () => {
  const state = createCreationState('verified-owner'), listener = vi.fn()
  const unsubscribe = state.subscribe(listener), version = state.version()
  const form = { draft: { name: 'Private draft' }, submitted: { request: 'original' } }
  expect(state.update({ form }, version)).toBe(true)
  expect(state.getSnapshot().form).toEqual(form)
  expect(listener).toHaveBeenCalledOnce()
  unsubscribe()
  state.retire()
  expect(state.update({ form }, version)).toBe(false)
  expect(state.getSnapshot()).toEqual({})
})

it('deliberate reset invalidates completion from the abandoned workflow', () => {
  const state = createCreationState('verified-admin'), version = state.version()
  state.reset()
  expect(state.update({ form: { created: { id: 'old' } } }, version)).toBe(false)
  expect(state.update({ form: { draft: {} } })).toBe(true)
})
