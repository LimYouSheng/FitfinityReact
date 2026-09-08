export function contentErrors(draft) {
  const errors = {}
  if (!draft.title?.trim() || draft.title.length > 180) errors.title = 'Enter a title of up to 180 characters.'
  if (!/^[a-z0-9]+(?:[-/][a-z0-9]+)*$/.test(draft.key ?? '') || draft.key.length > 120) errors.key = 'Use a content key with lowercase letters, numbers, hyphens or slashes.'
  if (!draft.body?.trim() || draft.body.length > 20000) errors.body = 'Enter content of up to 20,000 characters.'
  if (!['draft', 'ready', 'archived'].includes(draft.status)) errors.status = 'Choose a content status.'
  return errors
}
