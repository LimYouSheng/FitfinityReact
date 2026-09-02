import { seed } from '../data/seed.js'

const KEY = 'fitfinity-m1-2-mock-db'
const clone = value => JSON.parse(JSON.stringify(value))

function load() {
  try {
    const stored = localStorage.getItem(KEY)
    return stored ? JSON.parse(stored) : clone(seed)
  } catch {
    return clone(seed)
  }
}

let state = load()

function persist() {
  try { localStorage.setItem(KEY, JSON.stringify(state)) } catch { /* private/test fallback */ }
}

export const mockDb = {
  read() { return clone(state) },
  write(next) { state = clone(next); persist(); return clone(state) },
  mutate(mutator) {
    const next = clone(state)
    mutator(next)
    state = next
    persist()
    return clone(state)
  },
  reset() { state = clone(seed); persist(); return clone(state) },
}

export const delay = (ms = 120) => new Promise(resolve => setTimeout(resolve, ms))
