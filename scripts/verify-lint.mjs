import { ESLint } from 'eslint'
import path from 'node:path'
import { pathToFileURL } from 'node:url'

export async function verifyLint(cwd = process.cwd()) {
  const engine = new ESLint({ cwd })
  const results = await engine.lintFiles(['src', 'scripts', 'tests', '*.js', 'public/**/*.js'])
  const formatter = await engine.loadFormatter('stylish')
  const diagnostics = formatter.format(results)
  if (diagnostics) console.log(diagnostics)
  if (results.some(result => result.errorCount || result.warningCount)) throw new Error('Semantic/Hooks lint failed; no warnings are accepted.')
  console.log(`\u001b[32mPASS — Semantic and React Hooks lint: ${results.length} files; no errors or warnings.\u001b[0m`)
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  try { await verifyLint() }
  catch (error) { console.error(`\u001b[31m${error.message}\u001b[0m`); process.exitCode = 1 }
}
