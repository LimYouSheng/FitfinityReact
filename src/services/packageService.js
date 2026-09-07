import { PACKAGE_VALIDITY, packageDefinitions, packageErrors } from '../app/packages.js'
import { requireActiveActor } from '../app/scheduleChanges.js'
import { appendSavedEditMessage } from './editMessage.js'
import { delay, mockDb } from './mockDb.js'

export const packageService = {
  async save({ id, expectedVersion, draft }, actor) {
    await delay(180)
    let savedId
    const state = mockDb.mutate(db => {
      if (requireActiveActor(db, actor).role !== 'owner') throw new Error('Only the owner can set up packages.')
      const errors = packageErrors(draft)
      if (Object.keys(errors).length) throw new Error(Object.values(errors)[0])
      const definitions = structuredClone(packageDefinitions(db))
      const previous = id ? definitions.find(item => item.id === id) : null
      if (id && (!previous || previous.version !== expectedVersion)) throw new Error('Package changed. Refresh before editing again.')
      const name = draft.name.trim()
      if (definitions.some(item => item.id !== id && item.name.toLowerCase() === name.toLowerCase())) throw new Error('A package already uses this name.')
      if (draft.status && !['active', 'inactive'].includes(draft.status)) throw new Error('Choose a valid package status.')
      savedId = id ?? `package-${Math.max(0, ...definitions.map(item => Number(item.id.match(/^package-(\d+)$/)?.[1] ?? 0))) + 1}`
      const record = { id: savedId, name, total: Number(draft.total), validityDays: PACKAGE_VALIDITY[Number(draft.total)],
        status: draft.status ?? previous?.status ?? 'active', version: (previous?.version ?? 0) + 1 }
      if (previous) definitions[definitions.findIndex(item => item.id === id)] = record
      else definitions.push(record)
      db.packages = definitions
      appendSavedEditMessage(db, { packageId: savedId, kind: 'package_setup', title: `Package ${previous ? 'updated' : 'created'}: ${name}`,
        body: `${record.total} sessions · ${record.validityDays} days · ${record.status}. Existing client packages keep their purchased terms.` })
    })
    return state.packages.find(item => item.id === savedId)
  },
}
