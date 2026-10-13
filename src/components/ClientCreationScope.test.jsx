import { act, cleanup, render, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { PortalDataProvider } from './PortalDataProvider.jsx'
import usePortalData from '../hooks/usePortalData.js'

afterEach(cleanup)
const snapshot = () => ({ user: { id: 'verified-owner', role: 'owner' }, sessionGeneration: 0, policy: { timeZone: 'Asia/Singapore' }, businessDate: '2026-10-13', data: {}, capabilities: { realAuthentication: true, clientCreation: true, trainerCreation: true } })

it.each(['client', 'trainer'])('retains a %s draft during directory outages and retires it on verified identity change', async kind => {
  let current, fail = false, identity = false
  const services = { load: vi.fn(async () => {
    if (fail) throw Object.assign(new Error('Directory unavailable'), identity ? { verifiedIdentity: { id: 'replacement', role: 'admin', sessionGeneration: 1 } } : {})
    return snapshot()
  }) }
  function Probe() { current = usePortalData(); return null }
  render(<PortalDataProvider services={services}><Probe /></PortalDataProvider>)
  await waitFor(() => expect(current[`${kind}Creation`]).toBeTruthy())
  const creation = current[`${kind}Creation`], version = creation.version()
  creation.update({ form: { draft: { name: 'Retained private client' }, submitted: { original: true } } })
  fail = true
  await act(async () => { await current.refresh().catch(() => {}) })
  expect(current.snapshot).toBeNull()
  expect(current[`${kind}Creation`]).toBe(creation)
  expect(creation.getSnapshot().form.draft.name).toBe('Retained private client')
  identity = true
  await act(async () => { await current.refresh().catch(() => {}) })
  expect(current[`${kind}Creation`]).toBeNull()
  expect(creation.update({ form: { created: 'late old result' } }, version)).toBe(false)
  expect(creation.getSnapshot()).toEqual({})
})

it.each(['client', 'trainer'])('forbidden %s creation retires the private workflow and removes the directory', async kind => {
  let current
  const services = { load: vi.fn(async () => snapshot()), [`${kind}Service`]: { create: vi.fn(async () => { throw Object.assign(new Error('No current authority'), { code: 'forbidden', status: 403 }) }) } }
  function Probe() { current = usePortalData(); return null }
  render(<PortalDataProvider services={services}><Probe /></PortalDataProvider>)
  await waitFor(() => expect(current[`${kind}Creation`]).toBeTruthy())
  const original = current[`${kind}Creation`]
  original.update({ form: { submitted: { original: true } } })
  await act(async () => { await current.services[`${kind}Service`].create({ draft: {} }).catch(() => {}) })
  expect(current[`${kind}Creation`]).toBeNull()
  expect(current.snapshot).toBeNull()
  expect(original.getSnapshot()).toEqual({})
})

it.each(['client', 'trainer'])('retires private %s drafts when a later snapshot read discovers a changed login', async kind => {
  let current, changed = false
  const services = { load: vi.fn(async () => {
    if (changed) throw Object.assign(new Error('Login changed during Messages read'), { code: 'SESSION_CHANGED', verifiedIdentity: { id: 'verified-owner', role: 'owner', sessionGeneration: 0 } })
    return snapshot()
  }) }
  function Probe() { current = usePortalData(); return null }
  render(<PortalDataProvider services={services}><Probe /></PortalDataProvider>)
  await waitFor(() => expect(current[`${kind}Creation`]).toBeTruthy())
  const original = current[`${kind}Creation`], version = original.version()
  original.update({ form: { draft: { name: 'Private client' } } })
  changed = true
  await act(async () => { await current.refresh().catch(() => {}) })
  expect(current.snapshot).toBeNull()
  expect(current[`${kind}Creation`]).toBeNull()
  expect(original.getSnapshot()).toEqual({})
  expect(original.update({ form: { draft: { name: 'Late result' } } }, version)).toBe(false)
})
