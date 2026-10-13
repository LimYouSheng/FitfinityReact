import { directoryData } from './directory.js'
export function deactivationReview(patch = {}) {
  const client = directoryData().clients[0]
  return { id: client.id, version: client.version, name: client.name, trainerId: client.trainer_id,
    purchases: client.purchases.map(p => ({ id: p.id, version: p.version, status: p.status, name: p.name })), ...patch }
}
