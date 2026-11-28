const THEME_KEY = 'fitfinity-theme'

export function readTheme() {
  try { return localStorage.getItem(THEME_KEY) === 'light' ? 'light' : 'dark' } catch { return 'dark' }
}

export function applyTheme(theme) {
  document.documentElement.dataset.theme = theme
}

export function saveTheme(theme) {
  applyTheme(theme)
  try { localStorage.setItem(THEME_KEY, theme) } catch { /* The current tab can still change theme when storage is unavailable. */ }
}
