import { seed } from '../data/seed.js'
import { migrateRenewalMessages } from '../app/renewals.js'

const KEY = 'fitfinity-m2-demo-db-v4'
const clone = value => JSON.parse(JSON.stringify(value))

function load() {
  let loaded
  try {
    const stored = localStorage.getItem(KEY)
    loaded = stored ? JSON.parse(stored) : clone(seed)
  } catch {
    return clone(seed)
  }
  const normalized = { ...loaded, settings: { ...clone(seed.settings), ...loaded.settings }, exerciseLibrary: loaded.exerciseLibrary ?? clone(seed.exerciseLibrary), contentEntries: loaded.contentEntries ?? [], packages: loaded.packages ?? clone(seed.packages), sessions: (loaded.sessions ?? []).map(session => ({ ...session, whatsappOpenedAt: session.whatsappOpenedAt ?? session.whatsappSentAt, whatsappOpenCount: session.whatsappOpenCount ?? session.whatsappSendCount })) }
  // A legacy-data migration must persist successfully before it is published to the UI.
  if (migrateRenewalMessages(normalized)) localStorage.setItem(KEY, JSON.stringify(normalized))
  return normalized
}

let state
const current = () => state ??= load()

function commit(next) {
  // Publish to memory only after storage succeeds, so failures can be retried safely.
  localStorage.setItem(KEY, JSON.stringify(next))
  state = next
  return clone(state)
}

export const mockDb = {
  read() { return clone(current()) },
  reload() { state = load(); return clone(state) },
  write(next) { return commit(clone(next)) },
  mutate(mutator) {
    const next = clone(current())
    mutator(next)
    return commit(next)
  },
  reset() { return commit(clone(seed)) },
}

export const delay = (ms = 120) => new Promise(resolve => setTimeout(resolve, ms))
