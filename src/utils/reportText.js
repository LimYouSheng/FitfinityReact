// Break at words where possible, including long names without spaces. Array.from
// keeps surrogate pairs intact, and React escapes all names before SVG rendering.
export function wrapText(value, limit) {
  const width = text => Array.from(text).reduce((sum, letter) => sum + (/[^\u0000-\u024f]/u.test(letter) ? 2 : /[MW@]/.test(letter) ? 1.5 : 1), 0)
  const lines = []
  let line = ''
  for (const word of String(value).split(/\s+/)) {
    if (line && width(`${line} ${word}`) > limit) { lines.push(line); line = '' }
    if (line) line += ' '
    for (const letter of Array.from(word)) {
      if (line && width(line + letter) > limit) { lines.push(line); line = '' }
      line += letter
    }
  }
  if (line) lines.push(line)
  return lines.length ? lines : ['']
}
