import { clientPackages, packageForRecord } from '../app/clientPackages.js'
import { updateClientProgress } from '../app/progress.js'
import { normalizePackageLifecycle } from '../app/packageLifecycle.js'
import { createDemoSeed, seed } from '../data/seed.js'
import { businessClock } from '../app/clock.js'
import { migrateRenewalMessages } from '../app/renewals.js'

const KEY = 'fitfinity-m2-demo-db-v4'
const clone = value => JSON.parse(JSON.stringify(value))

function normalizeSession(session) {
  const normalized = { ...session }
  // Migrate only absent fields. An explicit null means no handoff occurred;
  // it must not disappear or revive an obsolete legacy timestamp on reload.
  for (const [current, legacy] of [['whatsappOpenedAt', 'whatsappSentAt'], ['whatsappOpenCount', 'whatsappSendCount']]) {
    if (!Object.hasOwn(normalized, current) && Object.hasOwn(session, legacy)) normalized[current] = session[legacy]
  }
  return normalized
}

function normalizeClientRecords(db, client) {
  normalizePackageLifecycle(db, client)
  // Old demo sessions were constructed from this exact purchase, even when their
  // example dates preceded it. Stable seed identity can recover that original link.
  for (const session of db.sessions.filter(item => item.clientId === client.id && item.packageId == null)) {
    const original = seed.sessions.find(item => item.id === session.id && item.clientId === client.id &&
      item.date === session.date && item.sessionNumber === session.sessionNumber && item.packageTotal === session.packageTotal)
    if (original && clientPackages(client).some(item => item.id === original.packageId)) session.packageId = original.packageId
  }
  updateClientProgress(db, client.id)
  for (const credit of db.packageCreditTransactions ?? []) {
    if (credit.clientId !== client.id || credit.packageId != null) continue
    const session = db.sessions.find(item => item.id === credit.sessionId && item.clientId === client.id)
    const purchased = session && packageForRecord(client, session)
    if (purchased) credit.packageId = purchased.id
  }
}

function load() {
  let loaded, stored
  try {
    stored = localStorage.getItem(KEY)
    loaded = stored ? JSON.parse(stored) : createDemoSeed(businessClock(new Date(), seed.settings.timeZone).date)
  } catch {
    return createDemoSeed(businessClock(new Date(), seed.settings.timeZone).date)
  }
  const normalized = { ...loaded, settings: { ...clone(seed.settings), ...loaded.settings }, exerciseLibrary: loaded.exerciseLibrary ?? clone(seed.exerciseLibrary), contentEntries: loaded.contentEntries ?? [], packages: loaded.packages ?? clone(seed.packages), sessions: (loaded.sessions ?? []).map(normalizeSession) }
  // A legacy-data migration must persist successfully before it is published to the UI.
  const before = JSON.stringify(loaded)
  for (const client of normalized.clients) normalizeClientRecords(normalized, client)
  const renewalChanged = migrateRenewalMessages(normalized)
  if (!stored || renewalChanged || JSON.stringify(normalized) !== before) localStorage.setItem(KEY, JSON.stringify(normalized))
  return normalized
}

// Keep the canonical JSON snapshot so reads only parse an independent copy.
// Re-serializing every plan, signature and progress point on each read is costly.
let snapshotJson
const current = () => snapshotJson ??= JSON.stringify(load())

function commit(next) {
  for (const client of next.clients) normalizeClientRecords(next, client)
  // Publish to memory only after storage succeeds, so failures can be retried safely.
  const serialized = JSON.stringify(next)
  localStorage.setItem(KEY, serialized)
  snapshotJson = serialized
  return JSON.parse(serialized)
}

export const mockDb = {
  read() { return JSON.parse(current()) },
  reload() { const serialized = JSON.stringify(load()); snapshotJson = serialized; return JSON.parse(serialized) },
  write(next) { return commit(clone(next)) },
  mutate(mutator) {
    const next = JSON.parse(current())
    mutator(next)
    return commit(next)
  },
  reset(referenceDate) { return commit(referenceDate ? createDemoSeed(referenceDate) : clone(seed)) },
}

export const delay = (ms = 120) => new Promise(resolve => setTimeout(resolve, ms))
