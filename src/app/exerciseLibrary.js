export const CUSTOM_EXERCISE = '__custom__'

export function exerciseChoiceFor(name, catalog = []) {
  return catalog.some(item => item.status === 'active' && item.name === name) ? name : CUSTOM_EXERCISE
}
