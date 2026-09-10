import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useEditGuard } from '../components/EditGuardProvider.jsx'
import { PORTAL_SESSION_ENDED } from './usePortalData.js'

const cleanPath = value => String(value || 'dashboard').replace(/^\/+|\/+$/g, '') || 'dashboard'
const locationPath = () => cleanPath(location.hash.replace(/^#\/?/, ''))
const token = entry => `${entry.depth}|${entry.path}|${entry.state?.fitfinityOverlayId ?? ''}`

function readEntry(fallbackDepth = 0) {
  const path = locationPath()
  const state = history.state
  const known = state?.fitfinity && state.fitfinityPath === path && Number.isFinite(state.fitfinityDepth)
  return { path, depth: known ? state.fitfinityDepth : fallbackDepth, state: known ? state : null }
}

/** One owner for page history, including native Back/Forward during an edit. */
export default function useAppNavigation(userId = '') {
  const { activeEdit, guardNavigation } = useEditGuard()
  const [entry, setEntry] = useState(() => {
    const initial = readEntry()
    return initial.state?.fitfinityUserId != null && initial.state.fitfinityUserId !== userId
      ? { ...initial, path: 'dashboard' } : initial
  })
  const path = entry.path
  const current = useRef(null)
  const mounted = useRef(false)
  const pending = useRef(null)
  const lastEvent = useRef('')
  const allowedTraversal = useRef(false)
  const restoringScroll = useRef(false)
  const scrollPositions = useRef(new Map())
  const persistScroll = useRef(() => {})
  const live = useRef({ activeEdit, guardNavigation })
  live.current = { activeEdit, guardNavigation }

  const write = useCallback((next, replace = false, preserveView = false) => {
    if (!mounted.current) return
    persistScroll.current()
    const nextPath = cleanPath(next)
    const depth = (history.state?.fitfinityDepth ?? current.current?.depth ?? 0) + (replace ? 0 : 1)
    const state = { fitfinity: true, fitfinityDepth: depth, fitfinityPath: nextPath, fitfinityUserId: userId }
    if (preserveView && history.state?.fitfinityUserId === userId) {
      state.fitfinityPageState = history.state.fitfinityPageState
      state.fitfinityScroll = history.state.fitfinityScroll
    }
    history[replace ? 'replaceState' : 'pushState'](state, '', `#/${nextPath}`)
    current.current = { path: nextPath, depth, state }
    scrollPositions.current.delete(token(current.current))
    restoringScroll.current = true
    lastEvent.current = token(current.current)
    setEntry(current.current)
  }, [userId])

  const setValue = useCallback((key, next, initialValue) => {
    if (!mounted.current || pending.current) return
    const actual = readEntry()
    if (actual.path !== current.current?.path || actual.path !== path) return
    const values = actual.state?.fitfinityUserId === userId ? actual.state.fitfinityPageState ?? {} : {}
    const previous = Object.hasOwn(values, key) ? values[key] : initialValue
    const value = typeof next === 'function' ? next(previous) : next
    if (Object.hasOwn(values, key) && Object.is(previous, value)) return
    const state = { ...actual.state, fitfinityUserId: userId, fitfinityPageState: { ...values, [key]: value } }
    history.replaceState(state, '', location.href)
    current.current = { ...actual, state }
    setEntry(current.current)
  }, [userId, path])

  useLayoutEffect(() => {
    mounted.current = true
    const initial = readEntry()
    if (initial.state?.fitfinityUserId != null && initial.state.fitfinityUserId !== userId) {
      initial.path = 'dashboard'
      history.replaceState(null, '', '#/dashboard')
      initial.depth = 0
      initial.state = null
    }
    initial.state ??= { fitfinity: true, fitfinityDepth: initial.depth, fitfinityPath: initial.path }
    initial.state.fitfinityUserId = userId
    history.replaceState(initial.state, '', location.href)
    current.current = initial
    // The hash may change between the first render and this effect (notably during startup).
    setEntry(initial)

    const accept = entry => {
      restoringScroll.current = true
      current.current = entry
      setEntry(entry)
    }
    const restore = (origin, entry) => {
      const delta = origin.depth - entry.depth
      if (delta) history.go(delta)
    }
    const ask = async transaction => {
      transaction.phase = 'prompting'
      const accepted = await live.current.guardNavigation(() => {})
      if (!mounted.current || pending.current !== transaction) return
      transaction.phase = accepted ? 'leaving' : 'cancelling'
      const destination = accepted ? transaction.target : transaction.origin
      const actual = readEntry()
      if (token(actual) === token(destination)) {
        pending.current = null
        accept(destination)
      } else {
        history.go(destination.depth - actual.depth)
      }
    }
    const sync = () => {
      const entry = readEntry((current.current?.depth ?? 0) + 1)
      if (!entry.state) {
        entry.state = { fitfinity: true, fitfinityDepth: entry.depth, fitfinityPath: entry.path, fitfinityUserId: userId }
        history.replaceState(entry.state, '', location.href)
      }
      const key = token(entry)
      if (key === lastEvent.current) return // A hash traversal emits both popstate and hashchange.
      lastEvent.current = key
      const transaction = pending.current
      if (transaction) {
        const destination = transaction.phase === 'leaving' ? transaction.target : transaction.origin
        if (key !== token(destination)) {
          restore(destination, entry)
          return
        }
        if (transaction.phase === 'restoring') void ask(transaction)
        else if (['leaving', 'cancelling'].includes(transaction.phase)) {
          pending.current = null
          accept(destination)
        }
        return
      }
      if (allowedTraversal.current || !live.current.activeEdit || key === token(current.current)) {
        allowedTraversal.current = false
        accept(entry)
        return
      }
      const transactionNext = { origin: current.current, target: entry, phase: 'restoring' }
      pending.current = transactionNext
      // Restore the real history entry before prompting, preserving the draft and Forward stack.
      restore(transactionNext.origin, entry)
    }
    window.addEventListener('popstate', sync)
    window.addEventListener('hashchange', sync)
    const endSession = () => {
      pending.current = null
      allowedTraversal.current = false
      scrollPositions.current.clear()
      write('dashboard', true)
    }
    window.addEventListener(PORTAL_SESSION_ENDED, endSession)
    return () => {
      mounted.current = false
      pending.current = null
      window.removeEventListener('popstate', sync)
      window.removeEventListener('hashchange', sync)
      window.removeEventListener(PORTAL_SESSION_ENDED, endSession)
    }
  }, [])

  useEffect(() => {
    const previous = history.scrollRestoration
    history.scrollRestoration = 'manual'
    let timer
    const capture = () => {
      if (restoringScroll.current || pending.current || document.body.style.position === 'fixed') return
      const actual = readEntry()
      if (actual.path !== current.current?.path) return
      const position = { x: window.scrollX, y: window.scrollY }
      scrollPositions.current.set(token(actual), position)
      return { actual, position }
    }
    persistScroll.current = () => {
      clearTimeout(timer)
      const captured = capture()
      if (!captured) return
      const { actual, position } = captured
      if (actual.state?.fitfinityScroll?.x === position.x && actual.state?.fitfinityScroll?.y === position.y) return
      const state = { ...actual.state, fitfinityUserId: userId, fitfinityScroll: position }
      history.replaceState(state, '', location.href)
      current.current = { ...actual, state }
    }
    const rememberScroll = () => {
      capture()
      clearTimeout(timer)
      timer = setTimeout(() => persistScroll.current(), 500)
    }
    window.addEventListener('scroll', rememberScroll, { passive: true })
    window.addEventListener('pagehide', persistScroll.current)
    return () => {
      clearTimeout(timer); history.scrollRestoration = previous
      window.removeEventListener('scroll', rememberScroll)
      window.removeEventListener('pagehide', persistScroll.current)
      persistScroll.current = () => {}
    }
  }, [userId])

  const entryToken = token(entry)
  useLayoutEffect(() => {
    restoringScroll.current = true
    let secondFrame
    const firstFrame = requestAnimationFrame(() => {
      const position = scrollPositions.current.get(entryToken) ?? (entry.state?.fitfinityUserId === userId ? entry.state.fitfinityScroll : null)
      if (document.body.style.position !== 'fixed') window.scrollTo(position?.x ?? 0, position?.y ?? 0)
      secondFrame = requestAnimationFrame(() => { restoringScroll.current = false })
    })
    return () => { cancelAnimationFrame(firstFrame); cancelAnimationFrame(secondFrame) }
  }, [entryToken, userId])

  // A message popup can add a same-page history entry without changing App's path.
  useEffect(() => {
    if (activeEdit && !pending.current) {
      current.current = readEntry()
      lastEvent.current = token(current.current)
    }
  }, [activeEdit])

  const navigate = useCallback((next, options = {}) => {
    if (!mounted.current || pending.current || allowedTraversal.current) return Promise.resolve(false)
    if (cleanPath(next) === current.current?.path && !history.state?.fitfinityOverlay) return Promise.resolve(false)
    return guardNavigation(() => write(next, options.replace, options.preserveView))
  }, [guardNavigation, write])

  const goBack = useCallback(fallback => {
    if (!mounted.current || pending.current || allowedTraversal.current) return Promise.resolve(false)
    return guardNavigation(() => {
      if (!mounted.current) return
      persistScroll.current()
      if ((history.state?.fitfinityDepth ?? 0) > 0) {
        allowedTraversal.current = true
        history.back()
      } else write(fallback, true)
    })
  }, [guardNavigation, write])

  const replacePath = useCallback(next => write(next, true), [write])
  const values = entry.state?.fitfinityUserId === userId ? entry.state.fitfinityPageState ?? {} : {}
  return { path, navigate, goBack, replacePath, canGoBack: entry.depth > 0 || path !== 'dashboard', pageState: { values, setValue } }
}
