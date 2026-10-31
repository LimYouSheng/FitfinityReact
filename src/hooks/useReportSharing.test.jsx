import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { PortalData } from './usePortalData.js'
import useReportSharing from './useReportSharing.js'

describe('report authorization lifetime', () => {
  const selection = { kind: 'session', targetId: 'booking', purchaseId: 'purchase', includeSummary: true, videoIds: [] }
  function setup(services, prepare = vi.fn().mockResolvedValue(new File(['reviewed'], 'summary.pdf'))) {
    const wrapper = ({ children }) => <PortalData.Provider value={{ services }}>{children}</PortalData.Provider>
    return { ...renderHook(({ source }) => useReportSharing(selection, source, prepare), { wrapper, initialProps: { source: 'original' } }), prepare }
  }
  it('authorizes and prepares without launching a device share or requesting on mount', async () => {
    const services = { prepareReportSharing: vi.fn().mockResolvedValue({ inputs: { summary: 'Frozen reviewed content' } }) }
    const view = setup(services)
    expect(services.prepareReportSharing).not.toHaveBeenCalled()
    await act(() => view.result.current.authorize())
    expect(view.prepare).toHaveBeenCalledExactlyOnceWith({ summary: 'Frozen reviewed content' })
    expect(view.result.current.file.name).toBe('summary.pdf')
    expect(view.result.current.message).toContain('tap Share PDF')
    view.rerender({ source: 'changed' })
    expect(view.result.current.file).toBeUndefined()
  })
  it('keeps pending approval separate from a prepared share', async () => {
    const error = Object.assign(new Error('Pending'), { code: 'APPROVAL_PENDING' })
    const view = setup({ prepareReportSharing: vi.fn().mockRejectedValue(error) })
    await act(() => view.result.current.authorize())
    expect(view.result.current.pending).toBe(true)
    expect(view.result.current.file).toBeUndefined()
    expect(view.prepare).not.toHaveBeenCalled()
  })
  it('discards a late authorized file after a content change', async () => {
    let resolve
    const prepare = vi.fn(() => new Promise(done => { resolve = done }))
    const view = setup({ prepareReportSharing: vi.fn().mockResolvedValue({ inputs: {} }) }, prepare)
    let running
    act(() => { running = view.result.current.authorize() })
    await waitFor(() => expect(prepare).toHaveBeenCalledOnce())
    view.rerender({ source: 'changed' })
    await act(async () => { resolve(new File(['old'], 'old.pdf')); await running })
    expect(view.result.current.file).toBeUndefined()
  })
  it('only retries an uncertain original request after an explicit action', async () => {
    const services = { prepareReportSharing: vi.fn().mockRejectedValue(Object.assign(new Error('Check first'), { code: 'SAVE_UNCERTAIN' })),
      retryReportSharing: vi.fn().mockResolvedValue({ inputs: {} }) }
    const view = setup(services)
    await act(() => view.result.current.authorize())
    expect(view.result.current.retry).toBe(true)
    expect(services.retryReportSharing).not.toHaveBeenCalled()
    await act(() => view.result.current.authorize(true))
    expect(services.retryReportSharing).toHaveBeenCalledExactlyOnceWith(selection)
    expect(view.result.current.file).toBeDefined()
  })
  it('retires a prepared report when the authenticated service scope changes', async () => {
    let services = { prepareReportSharing: vi.fn().mockResolvedValue({ inputs: {} }) }
    const wrapper = ({ children }) => <PortalData.Provider value={{ services }}>{children}</PortalData.Provider>
    const prepare = vi.fn().mockResolvedValue(new File(['old login'], 'old.pdf'))
    const view = renderHook(() => useReportSharing(selection, 'same record', prepare), { wrapper })
    await act(() => view.result.current.authorize())
    expect(view.result.current.file).toBeDefined()
    services = { prepareReportSharing: vi.fn().mockRejectedValue(new Error('Different login')) }
    view.rerender()
    expect(view.result.current.file).toBeUndefined()
  })
})
