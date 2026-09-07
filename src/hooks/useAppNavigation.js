import { useCallback, useEffect, useRef, useState } from 'react'
import { useEditGuard } from '../components/EditGuardProvider.jsx'

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
export default function useAppNavigation() {
  const { activeEdit, guardNavigation } = useEditGuard()
  const [path, setPath] = useState(locationPath)
  const current = useRef(null)
  const pending = useRef(null)
  const lastEvent = useRef('')
  const allowedTraversal = useRef(false)
  const live = useRef({ activeEdit, guardNavigation })
  live.current = { activeEdit, guardNavigation }

  const write = useCallback((next, replace = false) => {
    const nextPath = cleanPath(next)
    const depth = (history.state?.fitfinityDepth ?? current.current?.depth ?? 0) + (replace ? 0 : 1)
    const state = { fitfinity: true, fitfinityDepth: depth, fitfinityPath: nextPath }
    history[replace ? 'replaceState' : 'pushState'](state, '', `#/${nextPath}`)
    current.current = { path: nextPath, depth, state }
    lastEvent.current = token(current.current)
    setPath(nextPath)
  }, [])

  useEffect(() => {
    let mounted = true
    const initial = readEntry()
    initial.state ??= { fitfinity: true, fitfinityDepth: initial.depth, fitfinityPath: initial.path }
    history.replaceState(initial.state, '', location.href)
    current.current = initial
    // The hash may change between the first render and this effect (notably during startup).
    setPath(initial.path)

    const accept = entry => {
      current.current = entry
      setPath(entry.path)
    }
    const restore = (origin, entry) => {
      const delta = origin.depth - entry.depth
      if (delta) history.go(delta)
    }
    const ask = async transaction => {
      transaction.phase = 'prompting'
      const accepted = await live.current.guardNavigation(() => {})
      if (!mounted || pending.current !== transaction) return
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
        entry.state = { fitfinity: true, fitfinityDepth: entry.depth, fitfinityPath: entry.path }
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
    return () => {
      mounted = false
      pending.current = null
      window.removeEventListener('popstate', sync)
      window.removeEventListener('hashchange', sync)
    }
  }, [])

  // A message popup can add a same-page history entry without changing App's path.
  useEffect(() => {
    if (activeEdit && !pending.current) {
      current.current = readEntry()
      lastEvent.current = token(current.current)
    }
  }, [activeEdit])

  const navigate = useCallback((next, options = {}) => {
    if (pending.current) return Promise.resolve(false)
    return guardNavigation(() => write(next, options.replace))
  }, [guardNavigation, write])

  const goBack = useCallback(fallback => {
    if (pending.current) return Promise.resolve(false)
    return guardNavigation(() => {
      if ((history.state?.fitfinityDepth ?? 0) > 0) {
        allowedTraversal.current = true
        history.back()
      } else write(fallback, true)
    })
  }, [guardNavigation, write])

  const replacePath = useCallback(next => write(next, true), [write])
  return { path, navigate, goBack, replacePath }
}
