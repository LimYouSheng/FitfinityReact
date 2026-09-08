import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { createHash } from 'node:crypto'
import { readFileSync, readdirSync, writeFileSync } from 'node:fs'
import { join, resolve } from 'node:path'

// Build one complete shell revision, including Vite's hashed bundles and public assets.
function staffPortalPwa() {
  let base
  return {
    name: 'fitfinity-staff-pwa',
    apply: 'build',
    configResolved(config) {
      base = config.base
      if (!/^\/(?:[A-Za-z0-9_.-]+\/)*$/.test(base) || base.split('/').some(part => part === '.' || part === '..')) {
        throw new Error('Use an absolute directory path such as / or /FitfinityReact/ for the app base.')
      }
    },
    writeBundle(options) {
      const directory = resolve(options.dir)
      const filesIn = (folder, prefix = '') => readdirSync(folder, { withFileTypes: true })
        .flatMap(entry => entry.isDirectory()
          ? filesIn(join(folder, entry.name), `${prefix}${entry.name}/`)
          : [`${prefix}${entry.name}`])
      const files = filesIn(directory).filter(file => file !== 'sw.js' && !file.endsWith('.map')).sort()
      const workerPath = join(directory, 'sw.js')
      const template = readFileSync(workerPath, 'utf8')
      const hash = createHash('sha256').update(base).update('\0').update(template)
      for (const file of files) hash.update(file).update('\0').update(readFileSync(join(directory, file)))
      const revision = hash.digest('hex').slice(0, 20)
      const resources = files.map(file => file === 'index.html' ? base : `${base}${file}`)
      if (!resources.includes(base) || !template.includes('__BASE_PATH__') || !template.includes('__BUILD_REVISION__') || !template.includes('/* __PRECACHE__ */ []')) {
        throw new Error('The complete Fitfinity PWA shell could not be generated.')
      }
      writeFileSync(workerPath, template
        .replace("'__BASE_PATH__'", JSON.stringify(base))
        .replace('__BUILD_REVISION__', revision)
        .replace('/* __PRECACHE__ */ []', JSON.stringify(resources)))
    },
  }
}

export default defineConfig({
  base: process.env.FITFINITY_BASE_PATH || '/',
  plugins: [react(), staffPortalPwa()],
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.js',
    include: ['src/**/*.test.{js,jsx}'],
    exclude: ['tests/**', 'e2e/**', 'node_modules/**', 'dist/**'],
  },
})
