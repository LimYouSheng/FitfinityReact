import { seed } from '../data/seed.js'

const KEY = 'fitfinity-m2-demo-db-v4'
const clone = value => JSON.parse(JSON.stringify(value))

function load() {
  try {
    const stored = localStorage.getItem(KEY)
    const loaded = stored ? JSON.parse(stored) : clone(seed)
    return { ...loaded, settings: loaded.settings ?? clone(seed.settings), exerciseLibrary: loaded.exerciseLibrary ?? clone(seed.exerciseLibrary), contentEntries: loaded.contentEntries ?? [], packages: loaded.packages ?? clone(seed.packages), sessions: (loaded.sessions ?? []).map(session => ({ ...session, whatsappOpenedAt: session.whatsappOpenedAt ?? session.whatsappSentAt, whatsappOpenCount: session.whatsappOpenCount ?? session.whatsappSendCount })) }
  } catch {
    return clone(seed)
  }
}

let state = load()

function commit(next) {
  // Publish to memory only after storage succeeds, so failures can be retried safely.
  localStorage.setItem(KEY, JSON.stringify(next))
  state = next
  return clone(state)
}

export const mockDb = {
  read() { return clone(state) },
  reload() { state = load(); return clone(state) },
  write(next) { return commit(clone(next)) },
  mutate(mutator) {
    const next = clone(state)
    mutator(next)
    return commit(next)
  },
  reset() { return commit(clone(seed)) },
}

export const delay = (ms = 120) => new Promise(resolve => setTimeout(resolve, ms))
