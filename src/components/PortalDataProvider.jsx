import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { portalServices } from '../services/defaultPortalServices.js'
import { businessClock } from '../app/clock.js'
import { PortalData, PORTAL_SESSION_ENDED } from '../hooks/usePortalData.js'

export function PortalDataProvider({ services = portalServices, children }) {
  const [state, setState] = useState({ snapshot: null, error: '', loading: true })
  const [clock, setClock] = useState(() => new Date())
  const generation = useRef(0)
  const mounted = useRef(false)
  const refresh = useCallback(async () => {
    const request = ++generation.current
    try {
      const snapshot = await services.load()
      if (mounted.current && request === generation.current) {
        if (!snapshot.user) window.dispatchEvent(new Event(PORTAL_SESSION_ENDED))
        setState({ snapshot, error: '', loading: false })
      }
      return snapshot
    } catch (error) {
      if (mounted.current && request === generation.current) {
        if (error.code === 'SESSION_EXPIRED') window.dispatchEvent(new Event(PORTAL_SESSION_ENDED))
        setState(current => ({ ...current, snapshot: error.code === 'SESSION_EXPIRED' && current.snapshot ? { ...current.snapshot, user: null, data: null } : current.snapshot, error: error.message || 'Unable to load the portal.', loading: false }))
      }
      throw error
    }
  }, [services])
  useEffect(() => {
    mounted.current = true
    void refresh().catch(() => {})
    const synchronize = () => { setClock(new Date()); void refresh().catch(() => {}) }
    const timer = setInterval(() => { setClock(new Date()) }, 30000)
    window.addEventListener('storage', synchronize)
    window.addEventListener('focus', synchronize)
    return () => { mounted.current = false; ++generation.current; clearInterval(timer); window.removeEventListener('storage', synchronize); window.removeEventListener('focus', synchronize) }
  }, [refresh])
  const user = state.snapshot?.user
  useEffect(() => {
    if (user) void refresh().catch(() => {})
  }, [clock, user?.id, refresh])
  const guardedServices = useMemo(() => {
    const signOutSnapshot = () => {
      ++generation.current
      // Let the active navigation owner retire its route before private UI unmounts.
      window.dispatchEvent(new Event(PORTAL_SESSION_ENDED))
      setState(current => ({ ...current, snapshot: current.snapshot ? { ...current.snapshot, user: null, data: null } : null, error: '', loading: false }))
    }
    const wrap = (operation, clearSession = false) => async (...args) => {
      try { const result = await operation(...args); if (clearSession && mounted.current) signOutSnapshot(); return result }
      catch (error) {
        if (error.code === 'SESSION_EXPIRED' && mounted.current) {
          signOutSnapshot()
        }
        throw error
      }
    }
    return Object.fromEntries(Object.entries(services).map(([key, value]) => [key, typeof value === 'function' ? wrap(value) : Object.fromEntries(Object.entries(value).map(([method, operation]) => [method, wrap(operation, key === 'auth' && method === 'signOut')]))]))
  }, [services])
  const today = businessClock(clock, state.snapshot?.policy.timeZone).date
  return <PortalData.Provider value={{ ...state, services: guardedServices, refresh, today }}>{children}</PortalData.Provider>
}
