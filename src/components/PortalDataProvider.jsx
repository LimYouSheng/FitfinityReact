import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { portalServices } from '../services/defaultPortalServices.js'
import { businessClock } from '../app/clock.js'
import { PortalData, PORTAL_SESSION_ENDED } from '../hooks/usePortalData.js'
import { createAdminCreationState } from '../app/adminOnboarding.js'
import { createCreationState } from '../app/creationState.js'

const identityScope = (user, sessionGeneration) => user ? `${user.id}/${user.role}/${sessionGeneration ?? 'demo'}` : null
const authorityLost = error => ['SESSION_EXPIRED', 'SESSION_RECHECK', 'SESSION_CHANGED', 'forbidden'].includes(error.code) || [401, 403].includes(error.status)

export function PortalDataProvider({ services = portalServices, children }) {
  const [state, setState] = useState({ snapshot: null, error: '', loading: true })
  const [clock, setClock] = useState(() => new Date())
  const generation = useRef(0)
  const mounted = useRef(false)
  const adminRecovery = useRef(null)
  const clientRecovery = useRef(null)
  const trainerRecovery = useRef(null)
  const sessionScope = useRef(null)
  const retireAdminCreation = useCallback(() => {
    adminRecovery.current?.retire()
    adminRecovery.current = null
  }, [])
  const retireClientCreation = useCallback(() => {
    clientRecovery.current?.retire()
    clientRecovery.current = null
  }, [])
  const retireTrainerCreation = useCallback(() => {
    trainerRecovery.current?.retire()
    trainerRecovery.current = null
  }, [])
  const retireWorkflows = useCallback(() => { retireAdminCreation(); retireClientCreation(); retireTrainerCreation() }, [retireAdminCreation, retireClientCreation, retireTrainerCreation])
  const invalidateRequests = useCallback(() => { ++generation.current }, [])
  const refresh = useCallback(async () => {
    const request = ++generation.current
    try {
      const snapshot = await services.load()
      if (mounted.current && request === generation.current) {
        const nextScope = identityScope(snapshot.user, snapshot.sessionGeneration)
        if (nextScope !== sessionScope.current) retireWorkflows()
        sessionScope.current = nextScope
        const ownerId = snapshot.user?.role === 'owner' ? snapshot.user.id : null
        if (adminRecovery.current?.ownerId !== ownerId) retireAdminCreation()
        if (ownerId && !adminRecovery.current) adminRecovery.current = createAdminCreationState(ownerId)
        const clientOwner = ['owner', 'admin'].includes(snapshot.user?.role) && snapshot.capabilities?.clientCreation ? snapshot.user.id : null
        if (clientRecovery.current?.ownerId !== clientOwner) retireClientCreation()
        if (clientOwner && !clientRecovery.current) clientRecovery.current = createCreationState(clientOwner)
        const trainerOwner = ['owner', 'admin'].includes(snapshot.user?.role) && snapshot.capabilities?.trainerCreation ? snapshot.user.id : null
        if (trainerRecovery.current?.ownerId !== trainerOwner) retireTrainerCreation()
        if (trainerOwner && !trainerRecovery.current) trainerRecovery.current = createCreationState(trainerOwner)
        if (!snapshot.user) window.dispatchEvent(new Event(PORTAL_SESSION_ENDED))
        setState({ snapshot, adminCreation: adminRecovery.current, clientCreation: clientRecovery.current, trainerCreation: trainerRecovery.current, error: '', loading: false })
      }
      return snapshot
    } catch (error) {
      if (mounted.current && request === generation.current) {
        const nextScope = error.verifiedIdentity ? identityScope(error.verifiedIdentity, error.verifiedIdentity.sessionGeneration) : sessionScope.current
        const changedIdentity = nextScope !== sessionScope.current
        sessionScope.current = nextScope
        if (authorityLost(error) || changedIdentity) retireWorkflows()
        if (error.code === 'SESSION_EXPIRED') window.dispatchEvent(new Event(PORTAL_SESSION_ENDED))
        setState(current => ({ ...current, adminCreation: adminRecovery.current, clientCreation: clientRecovery.current, trainerCreation: trainerRecovery.current, snapshot: error.code === 'SESSION_EXPIRED' && current.snapshot ? { ...current.snapshot, user: null, data: null } : current.snapshot?.capabilities?.realAuthentication ? null : current.snapshot, error: error.message || 'Unable to load the portal.', loading: false }))
      }
      throw error
    }
  }, [services, retireAdminCreation, retireClientCreation, retireTrainerCreation, retireWorkflows])
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
      retireWorkflows()
      // Let the active navigation owner retire its route before private UI unmounts.
      window.dispatchEvent(new Event(PORTAL_SESSION_ENDED))
      setState(current => ({ ...current, adminCreation: null, clientCreation: null, trainerCreation: null, snapshot: current.snapshot ? { ...current.snapshot, user: null, data: null } : null, error: '', loading: false }))
    }
    const wrap = (operation, clearSession = false, creationType = null) => async (...args) => {
      const recovery = () => creationType === 'client' ? clientRecovery.current : creationType === 'trainer' ? trainerRecovery.current : adminRecovery.current
      const recoveryAtStart = recovery()
      const scopeAtStart = renderedScope
      const isCurrent = () => mounted.current && scopeAtStart === sessionScope.current
      try { const result = await operation(...args); if ((clearSession || result?.signedOut === true) && isCurrent()) signOutSnapshot(); return result }
      catch (error) {
        if (error.code === 'SESSION_CHANGED' && isCurrent()) {
          retireWorkflows()
          invalidateRequests()
          setState(current => ({ ...current, adminCreation: null, clientCreation: null, trainerCreation: null, snapshot: null, error: error.message, loading: false }))
          void refresh().catch(() => {})
        } else if (error.code === 'SESSION_EXPIRED' && isCurrent()) {
          signOutSnapshot()
        } else if (creationType && recoveryAtStart === recovery() && authorityLost(error) && isCurrent()) {
          retireWorkflows()
          invalidateRequests()
          setState(current => ({ ...current, adminCreation: null, clientCreation: null, trainerCreation: null, snapshot: null, error: error.message, loading: false }))
        }
        throw error
      }
    }
    return Object.fromEntries(Object.entries(scopedServices).filter(([key]) => key !== 'forSession').map(([key, value]) => [key, key === 'reportService' ? value : typeof value === 'function' ? wrap(value) : Object.fromEntries(Object.entries(value).map(([method, operation]) => [method, wrap(operation, key === 'auth' && method === 'signOut', key === 'staffService' && method === 'createAdmin' ? 'admin' : key === 'clientService' && method === 'create' ? 'client' : key === 'trainerService' && method === 'create' ? 'trainer' : null)]))]))
  }, [services, renderedScope, renderedGeneration, refresh, invalidateRequests, retireWorkflows])
  const today = state.snapshot?.businessDate ?? businessClock(clock, state.snapshot?.policy.timeZone).date
  return <PortalData.Provider value={{ ...state, services: guardedServices, refresh, today }}>{children}</PortalData.Provider>
}
