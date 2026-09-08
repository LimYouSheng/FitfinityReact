import { DAYS } from './constants.js'

export { DAYS } from './constants.js'
const TIME = /^(?:[01]\d|2[0-3]):[0-5]\d$/

/** Availability windows share one validation boundary in both onboarding flows. */
export function availabilityBlockError(block, existing = [], rejectOverlaps = false) {
  if (!Array.isArray(block?.days) || !block.days.length || block.days.some(day => !DAYS.includes(day))) {
    return 'Select at least one possible day.'
  }
  if (!TIME.test(block.from) || !TIME.test(block.to) || block.from >= block.to) {
    return 'Choose a From time earlier than To.'
  }
  const days = DAYS.filter(day => block.days.includes(day))
  if (existing.some(item => item.from === block.from && item.to === block.to &&
    DAYS.filter(day => item.days.includes(day)).join('|') === days.join('|'))) {
    return 'This availability block is already added.'
  }
  if (rejectOverlaps && existing.some(item => item.days.some(day => days.includes(day)) &&
    item.from < block.to && block.from < item.to)) {
    return 'This time overlaps another block on a selected day.'
  }
  return ''
}

/** Normalize trainer availability to the existing day -> [from, to][] contract. */
export function availabilityByDay(blocks) {
  return Object.fromEntries(DAYS.map(day => [day, blocks
    .filter(block => block.days.includes(day))
    .map(block => [block.from, block.to])
    .sort((a, b) => a[0].localeCompare(b[0]))]))
}
