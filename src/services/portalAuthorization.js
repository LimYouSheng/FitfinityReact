import { managesOperations, canEditTrainerRates } from '../app/permissions.js'
import { messageVisibleTo } from '../app/messageInbox.js'
import { clientAssignedToTrainer } from '../app/clientPackages.js'
import { PortalContractError } from './portalContracts.js'

const deny = message => { throw new PortalContractError('FORBIDDEN', message) }
const operations = actor => { if (!managesOperations(actor)) deny('This action is available to the owner or Admin.') }
const assignedTrainer = (input, actor) => {
  if (!managesOperations(actor) && input.id !== actor.trainerId) deny('This trainer is unavailable for your account.')
}
const assignedClient = (input, actor, db) => {
  if (!managesOperations(actor) && !db.clients.some(item => item.id === input.id && item.trainerId === actor.trainerId)) deny('This client is unavailable for your account.')
}
const session = (input, actor, db) => {
  const current = db.sessions.find(item => item.id === input.sessionId)
  if (!current || (!managesOperations(actor) && current.trainerId !== actor.trainerId)) deny('This session is unavailable for your account.')
}
const rates = (draft, actor) => {
  if (!canEditTrainerRates(actor) && Object.hasOwn(draft, 'rates')) deny('Trainer pay rates are restricted.')
}

const policies = {
  authenticated() {},
  operations(input, actor) { operations(actor) },
  owner(input, actor) { if (actor.role !== 'owner') deny('Only the owner can create an Admin.') },
  assignedTrainer,
  assignedClient,
  session,
  operationsSession(input, actor, db) { operations(actor); session(input, actor, db) },
  trainerCreate(input, actor) { operations(actor); rates(input.draft, actor) },
  trainerEdit(input, actor) {
    if (Object.hasOwn(input.patch, 'name')) operations(actor)
    assignedTrainer(input, actor)
    rates(input.patch, actor)
  },
  clientEdit(input, actor, db) {
    assignedClient(input, actor, db)
    if (!managesOperations(actor) && Object.keys(input.patch).some(key => !['healthNotes', 'remarks', 'notes'].includes(key))) deny('Client information can only be edited by the owner or Admin.')
  },
  reportClient(input, actor, db) {
    const client = db.clients.find(item => item.id === input.id)
    if (!managesOperations(actor) && (!client || !clientAssignedToTrainer(client, actor.trainerId, db.sessions))) deny('This client is unavailable for your account.')
  },
  remuneration(input, actor) { if (actor.role === 'admin') deny('Remuneration access is restricted.') },
  approveRemuneration(input, actor) { if (actor.role !== 'owner') deny('Remuneration access is restricted.') },
  message(input, actor, db) {
    if (!messageVisibleTo(actor, db.messages.find(item => item.id === input.id))) deny('This message is unavailable.')
  },
}

export function authorizePortalRequest({ input, definition }, actor, db) {
  if (!Object.hasOwn(policies, definition.access)) deny('This action has no access policy.')
  policies[definition.access](input, actor, db)
}
