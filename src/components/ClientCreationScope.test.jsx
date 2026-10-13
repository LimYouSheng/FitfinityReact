import { act, cleanup, render, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { PortalDataProvider } from './PortalDataProvider.jsx'
import usePortalData from '../hooks/usePortalData.js'

afterEach(cleanup)
const snapshot = () => ({ user: { id: 'verified-owner', role: 'owner' }, sessionGeneration: 0, policy: { timeZone: 'Asia/Singapore' }, businessDate: '2026-10-13', data: {}, capabilities: { realAuthentication: true, clientCreation: true } })

it('retains a client draft during directory outages and retires it on verified identity change', async () => {
  let current, fail = false, identity = false
  const services = { load: vi.fn(async () => {
    if (fail) throw Object.assign(new Error('Directory unavailable'), identity ? { verifiedIdentity: { id: 'replacement', role: 'admin', sessionGeneration: 1 } } : {})
    return snapshot()
  }) }
  function Probe() { current = usePortalData(); return null }
  render(<PortalDataProvider services={services}><Probe /></PortalDataProvider>)
  await waitFor(() => expect(current.clientCreation).toBeTruthy())
  const creation = current.clientCreation, version = creation.version()
  creation.update({ form: { draft: { name: 'Retained private client' }, submitted: { original: true } } })
  fail = true
  await act(async () => { await current.refresh().catch(() => {}) })
  expect(current.snapshot).toBeNull()
  expect(current.clientCreation).toBe(creation)
  expect(creation.getSnapshot().form.draft.name).toBe('Retained private client')
  identity = true
  await act(async () => { await current.refresh().catch(() => {}) })
  expect(current.clientCreation).toBeNull()
  expect(creation.update({ form: { created: 'late old result' } }, version)).toBe(false)
  expect(creation.getSnapshot()).toEqual({})
})

it('forbidden creation retires the private workflow and removes the directory', async () => {
  let current
  const services = { load: vi.fn(async () => snapshot()), clientService: { create: vi.fn(async () => { throw Object.assign(new Error('No current authority'), { code: 'forbidden', status: 403 }) }) } }
  function Probe() { current = usePortalData(); return null }
  render(<PortalDataProvider services={services}><Probe /></PortalDataProvider>)
  await waitFor(() => expect(current.clientCreation).toBeTruthy())
  const original = current.clientCreation
  original.update({ form: { submitted: { original: true } } })
  await act(async () => { await current.services.clientService.create({ draft: {} }).catch(() => {}) })
  expect(current.clientCreation).toBeNull()
  expect(current.snapshot).toBeNull()
  expect(original.getSnapshot()).toEqual({})
})
