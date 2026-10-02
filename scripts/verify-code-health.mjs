import fs from 'node:fs'
import path from 'node:path'
import { execFileSync } from 'node:child_process'
import { createRequire } from 'node:module'
import { pathToFileURL } from 'node:url'

const fail = message => { throw new Error(message) }
const equal = (a, b) => JSON.stringify(a) === JSON.stringify(b)

// A Linux checkout must also be safe on a case-insensitive Mac filesystem.
// Check directory prefixes too: src/Foo/a.js and src/foo/b.js also collide.
export function assertPortableSourcePaths(files) {
  const spellings = new Map()
  for (const file of files) {
    const parts = file.split('/')
    for (let length = 1; length <= parts.length; length++) {
      const spelling = parts.slice(0, length).join('/')
      const folded = spelling.normalize('NFC').toLowerCase()
      const previous = spellings.get(folded)
      if (previous !== undefined && previous !== spelling) fail(`Case-insensitive source path collision: ${previous} / ${spelling}`)
      spellings.set(folded, spelling)
    }
  }
}

// Revision hashes and backups belong to the installer. This checker follows source ownership.
export async function verifyCodeHealth(repo = process.cwd()) {
  repo = fs.realpathSync(repo)
  const files = execFileSync('git', ['ls-files', '--cached', '--others', '--exclude-standard', '-z'], { cwd: repo, encoding: 'utf8' }).split('\0').filter(Boolean).sort()
  assertPortableSourcePaths(files)
  const fileSet = new Set(files)
  const filePath = relative => {
    let current = repo
    for (const part of relative.split('/')) {
      if (!part || part === '.' || part === '..') fail(`Unsafe source path: ${relative}`)
      current = path.join(current, part)
      if (fs.lstatSync(current).isSymbolicLink()) fail(`Redirected source path: ${relative}`)
    }
    if (!fs.statSync(current).isFile()) fail(`Non-file source: ${relative}`)
    return current
  }
  for (const file of files) filePath(file)
  const req = createRequire(path.join(repo, 'package.json'))
  const utils = await import(pathToFileURL(req.resolve('rolldown/utils')))
  const graph = new Map()
  const cssImports = []
  const walk = (node, callback) => {
    if (!node || typeof node !== 'object') return
    if (Array.isArray(node)) { for (const value of node) walk(value, callback); return }
    if (node.type) callback(node)
    for (const [key, value] of Object.entries(node)) if (!['parent', 'loc', 'start', 'end'].includes(key)) walk(value, callback)
  }
  let syntaxCount = 0
  for (const file of files) {
    if (!/\.(js|jsx|mjs|css|json|md|html|webmanifest|yml|yaml|py|toml|txt|lock)$/.test(file) && file !== '.gitignore') continue
    const text = fs.readFileSync(filePath(file), 'utf8')
    if (/^(?:<{7}|>{7})(?:\s|$)/m.test(text) || /^(?:={7})$/m.test(text)) fail(`Conflict marker: ${file}`)
    if (/[\t ]+$/m.test(text)) fail(`Trailing whitespace: ${file}`)
    if (!/\.(js|jsx|mjs)$/.test(file)) continue
    const parsed = utils.parseSync(file, text, { lang: file.endsWith('.jsx') ? 'jsx' : 'js' })
    if (parsed.errors.length) fail(`JS/JSX/MJS parse error in ${file}: ${JSON.stringify(parsed.errors)}`)
    syntaxCount++
    const imports = []
    for (const declaration of parsed.program.body) {
      if (!['ImportDeclaration', 'ExportNamedDeclaration', 'ExportAllDeclaration'].includes(declaration.type) || !declaration.source) continue
      const source = declaration.source.value
      if (source.startsWith('.')) {
        const target = path.posix.normalize(path.posix.join(path.posix.dirname(file), source))
        if (!fileSet.has(target)) fail(`Missing relative import: ${file} -> ${source}`)
        if (declaration.type === 'ImportDeclaration' && target === 'src/styles.css') cssImports.push(file)
        imports.push(target)
        if (/^src\/(app|services)\//.test(file) && !file.includes('.test.') && /^src\/(features|components)\//.test(target)) fail(`UI imported by domain/service: ${file}`)
      }
      if (declaration.type === 'ImportDeclaration') {
        for (const specifier of declaration.specifiers) {
          let used = false
          for (const statement of parsed.program.body) if (statement.type !== 'ImportDeclaration') walk(statement, node => {
            if (['Identifier', 'JSXIdentifier'].includes(node.type) && node.name === specifier.local.name) used = true
          })
          if (!used) fail(`Unused imported name ${specifier.local.name} in ${file}`)
        }
      }
    }
    walk(parsed.program, node => {
      if (node.type === 'ImportExpression' && typeof node.source?.value === 'string' && node.source.value.startsWith('.')) {
        const target = path.posix.normalize(path.posix.join(path.posix.dirname(file), node.source.value))
        if (!fileSet.has(target)) fail(`Missing dynamic import: ${file} -> ${node.source.value}`)
        imports.push(target)
      }
      if (node.type !== 'CallExpression') return
      let callee = node.callee
      const members = []
      while (callee?.type === 'MemberExpression') { members.push(callee.property.name ?? callee.property.value); callee = callee.object }
      if (['test', 'it', 'describe'].includes(callee?.name) && members.some(name => ['skip', 'only', 'fixme', 'todo'].includes(name))) fail(`Disabled/exclusive test control: ${file}`)
    })
    graph.set(file, imports.filter(target => /\.(js|jsx|mjs)$/.test(target)))
  }
  const visited = new Set()
  const visiting = new Set()
  const visit = file => {
    if (visiting.has(file)) fail(`Static import cycle at ${file}`)
    if (visited.has(file)) return
    visiting.add(file)
    for (const target of graph.get(file) ?? []) visit(target)
    visiting.delete(file); visited.add(file)
  }
  for (const file of graph.keys()) visit(file)
  const reachable = new Set()
  const reach = file => { if (reachable.has(file)) return; reachable.add(file); for (const target of graph.get(file) ?? []) reach(target) }
  reach('src/main.jsx')
  const runtime = [...graph.keys()].filter(file => file.startsWith('src/') && !file.includes('.test.') && !file.startsWith('src/test/'))
  const unreachable = runtime.filter(file => !reachable.has(file))
  if (unreachable.length) fail(`Unreachable runtime modules: ${unreachable.join(', ')}`)
  const cssTree = await import(pathToFileURL(req.resolve('css-tree')))
  const css = fs.readFileSync(path.join(repo, 'src/styles.css'), 'utf8')
  const ast = cssTree.parse(css)
  let rules = 0, declarations = 0
  const declaredVars = new Set(), usedVars = new Set()
  cssTree.walk(ast, {
    enter(node) {
      if (node.type === 'Rule') rules++
      if (node.type === 'Declaration') {
        declarations++
        if (node.property.startsWith('--')) declaredVars.add(node.property)
        const value = cssTree.generate(node.value)
        for (const match of value.matchAll(/var\((--[\w-]+)/g)) usedVars.add(match[1])
        if (!node.property.startsWith('-') && !value.includes('var(')) {
          const match = cssTree.lexer.matchProperty(node.property, node.value)
          if (match.error && !/Unknown property/.test(match.error.message)) fail(`Invalid CSS ${node.property}: ${value}`)
        }
      }
      if (node.type === 'Block') {
        const seen = new Set()
        node.children.forEach(child => {
          if (child.type !== 'Declaration') return
          if (seen.has(child.property)) fail(`Duplicate CSS declaration: ${child.property}`)
          seen.add(child.property)
        })
      }
    },
  })
  for (const name of usedVars) if (!declaredVars.has(name)) fail(`Undefined CSS variable ${name}`)
  if (!equal(cssImports, ['src/main.jsx'])) fail('Canonical CSS import changed.')
  for (const provider of ['NotificationProvider', 'ActionConfirmationProvider', 'EditGuardProvider']) {
    const entries = runtime.filter(file => new RegExp(`<${provider}(?:>|\\s)`).test(fs.readFileSync(filePath(file), 'utf8')))
    if (!equal(entries, ['src/main.jsx'])) fail(`Canonical ${provider} ownership changed.`)
  }
  const stylesheets = files.filter(file => /^src\/.*\.css$/.test(file))
  if (!equal(stylesheets, ['src/styles.css'])) fail('Exactly one canonical source stylesheet is required.')
  const result = { sourceFiles: files.length, syntaxFiles: syntaxCount, runtimeModules: runtime.length, cssRules: rules, cssDeclarations: declarations }
  console.log(`\u001b[32mPASS — Code health: ${syntaxCount} JS/JSX/MJS files; imports, layering, cycles and ${runtime.length} reachable runtime modules.\u001b[0m`)
  console.log(`\u001b[32mPASS — CSS: ${rules} rules / ${declarations} declarations; properties, variables and shared ownership.\u001b[0m`)
  console.log('No disabled/exclusive tests, conflict markers, source whitespace or redirected source paths. Static checks are not visual/device certification.')
  return result
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  try { await verifyCodeHealth() }
  catch (error) { console.error(`\u001b[31m${error.stack ?? error}\u001b[0m`); process.exitCode = 1 }
}
