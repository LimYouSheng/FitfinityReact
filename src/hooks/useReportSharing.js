import { useContext, useEffect, useRef, useState } from 'react'
import { PortalData } from './usePortalData.js'

// Authorizing/preparing never launches a device action. Keep the final native
// share on a second explicit click, and discard late results after source changes.
export default function useReportSharing(selection, source, prepare) {
  const services = useContext(PortalData)?.services
  const enabled = Boolean(services?.prepareReportSharing)
  const key = JSON.stringify({ selection, source })
  const current = useRef({ key, services })
  const mounted = useRef(true)
  const acting = useRef(false)
  const [state, setState] = useState(null)
  current.current = { key, services }
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  const result = state?.key === key && state.services === services ? state : null
  const authorize = async (retry = false) => {
    if (!enabled || acting.current) return
    acting.current = true
    setState({ key, services, busy: true })
    try {
      const value = await (retry ? services.retryReportSharing(selection) : services.prepareReportSharing(selection))
      const file = await prepare(value.inputs)
      if (mounted.current && current.current.key === key && current.current.services === services) setState({ key, services, file, message: 'Report ready. Review or download the PDF, then tap Share PDF.' })
    } catch (error) {
      if (mounted.current && current.current.key === key && current.current.services === services) setState({ key, services, pending: error.code === 'APPROVAL_PENDING',
        retry: error.code === 'SAVE_UNCERTAIN', message: error.code === 'APPROVAL_PENDING' ? 'Waiting for Owner approval. Check again after the report is approved.' : error.message })
    } finally { acting.current = false }
  }
  return { enabled, file: result?.file, busy: Boolean(result?.busy), message: result?.message,
    pending: result?.pending, retry: result?.retry, authorize,
    reset: () => setState(null) }
}
