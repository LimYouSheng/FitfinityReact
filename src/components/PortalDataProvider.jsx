import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { portalServices } from '../services/defaultPortalServices.js'
import { businessClock } from '../app/clock.js'
import { PortalData, PORTAL_SESSION_ENDED } from '../hooks/usePortalData.js'
import { createAdminCreationState } from '../app/adminOnboarding.js'

const identityScope = (user, sessionGeneration) => user ? `${user.id}/${user.role}/${sessionGeneration ?? 'demo'}` : null
const authorityLost = error => ['SESSION_EXPIRED', 'SESSION_RECHECK', 'forbidden'].includes(error.code) || [401, 403].includes(error.status)

export function PortalDataProvider({ services = portalServices, children }) {
  const [state, setState] = useState({ snapshot: null, error: '', loading: true })
  const [clock, setClock] = useState(() => new Date())
  const generation = useRef(0)
  const mounted = useRef(false)
  const adminRecovery = useRef(null)
  const sessionScope = useRef(null)
  const retireAdminCreation = useCallback(() => {
    adminRecovery.current?.retire()
    adminRecovery.current = null
  }, [])
  const invalidateRequests = useCallback(() => { ++generation.current }, [])
  const refresh = useCallback(async () => {
    const request = ++generation.current
    try {
      const snapshot = await services.load()
      if (mounted.current && request === generation.current) {
        const nextScope = identityScope(snapshot.user, snapshot.sessionGeneration)
        if (nextScope !== sessionScope.current) retireAdminCreation()
        sessionScope.current = nextScope
        const ownerId = snapshot.user?.role === 'owner' ? snapshot.user.id : null
        if (adminRecovery.current?.ownerId !== ownerId) retireAdminCreation()
        if (ownerId && !adminRecovery.current) adminRecovery.current = createAdminCreationState(ownerId)
        if (!snapshot.user) window.dispatchEvent(new Event(PORTAL_SESSION_ENDED))
        setState({ snapshot, adminCreation: adminRecovery.current, error: '', loading: false })
      }
      return snapshot
    } catch (error) {
      if (mounted.current && request === generation.current) {
        const nextScope = error.verifiedIdentity ? identityScope(error.verifiedIdentity, error.verifiedIdentity.sessionGeneration) : sessionScope.current
        const changedIdentity = nextScope !== sessionScope.current
        sessionScope.current = nextScope
        if (authorityLost(error) || changedIdentity) retireAdminCreation()
        if (error.code === 'SESSION_EXPIRED') window.dispatchEvent(new Event(PORTAL_SESSION_ENDED))
        setState(current => ({ ...current, adminCreation: adminRecovery.current, snapshot: error.code === 'SESSION_EXPIRED' && current.snapshot ? { ...current.snapshot, user: null, data: null } : current.snapshot?.capabilities?.realAuthentication ? null : current.snapshot, error: error.message || 'Unable to load the portal.', loading: false }))
      }
      throw error
    }
  }, [services, retireAdminCreation])
  useEffect(() => {
    mounted.current = true
    void refresh().catch(() => {})
    const synchronize = () => { setClock(new Date()); void refresh().catch(() => {}) }
    const timer = setInterval(() => { setClock(new Date()) }, 30000)
    window.addEventListener('storage', synchronize)
    window.addEventListener('focus', synchronize)
    return () => { mounted.current = false; invalidateRequests(); clearInterval(timer); window.removeEventListener('storage', synchronize); window.removeEventListener('focus', synchronize) }
  }, [refresh, invalidateRequests])
  const userId = state.snapshot?.user?.id
  useEffect(() => {
    if (userId) void refresh().catch(() => {})
  }, [clock, userId, refresh])
  const renderedScope = identityScope(state.snapshot?.user, state.snapshot?.sessionGeneration)
  const renderedGeneration = state.snapshot?.sessionGeneration
  const guardedServices = useMemo(() => {
    const scopedServices = renderedGeneration === undefined ? services : services.forSession?.(renderedGeneration) ?? services
    const signOutSnapshot = () => {
      invalidateRequests()
      sessionScope.current = null
      retireAdminCreation()
      // Let the active navigation owner retire its route before private UI unmounts.
      window.dispatchEvent(new Event(PORTAL_SESSION_ENDED))
      setState(current => ({ ...current, adminCreation: null, snapshot: current.snapshot ? { ...current.snapshot, user: null, data: null } : null, error: '', loading: false }))
    }
    const wrap = (operation, clearSession = false, creatingAdmin = false) => async (...args) => {
      const recoveryAtStart = adminRecovery.current
      const scopeAtStart = renderedScope
      const isCurrent = () => mounted.current && scopeAtStart === sessionScope.current
      try { const result = await operation(...args); if ((clearSession || result?.signedOut === true) && isCurrent()) signOutSnapshot(); return result }
      catch (error) {
        if (error.code === 'SESSION_CHANGED' && isCurrent()) {
          retireAdminCreation()
          invalidateRequests()
          setState(current => ({ ...current, adminCreation: null, snapshot: null, error: error.message, loading: false }))
          void refresh().catch(() => {})
        } else if (error.code === 'SESSION_EXPIRED' && isCurrent()) {
          signOutSnapshot()
        } else if (creatingAdmin && recoveryAtStart === adminRecovery.current && authorityLost(error) && isCurrent()) {
          retireAdminCreation()
          invalidateRequests()
          setState(current => ({ ...current, adminCreation: null, snapshot: null, error: error.message, loading: false }))
        }
        throw error
      }
    }
    return Object.fromEntries(Object.entries(scopedServices).filter(([key]) => key !== 'forSession').map(([key, value]) => [key, key === 'reportService' ? value : typeof value === 'function' ? wrap(value) : Object.fromEntries(Object.entries(value).map(([method, operation]) => [method, wrap(operation, key === 'auth' && method === 'signOut', key === 'staffService' && method === 'createAdmin')]))]))
  }, [services, renderedScope, renderedGeneration, refresh, invalidateRequests, retireAdminCreation])
  const today = state.snapshot?.businessDate ?? businessClock(clock, state.snapshot?.policy.timeZone).date
  return <PortalData.Provider value={{ ...state, services: guardedServices, refresh, today }}>{children}</PortalData.Provider>
}
