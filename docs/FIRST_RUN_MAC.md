# Run and verify Fitfinity on your Mac

## Existing M3 checkout

Use `~/Desktop/FitfinityReact`. Do not rerun historical installers, reset the tree,
or replace the current lockfile. A delivery script verifies the exact recognised
source before writing and preserves unknown changes by stopping.

```bash
cd ~/Desktop/FitfinityReact
node --version
npm --version
git --no-pager status --short --branch
```

Use a Node version supported by the installed Vite release; the current lockfile
requires Node 20.19+ or 22.12+ (a supported newer release also works).

## Fresh checkout only

Dependencies are already locked. Install with `npm ci`, not an unreviewed lockfile update.
Browser engines are a one-time setup for this Playwright version:

```bash
npm ci
npx playwright install chromium webkit
```

Routine mutation scripts do not install dependencies or start a development server.

## Full gate

Keep port 4173 free. The delivered script is the authoritative gate: it also checks
exact totals, protected files, source fingerprints, imports, CSS and new-file whitespace.
The equivalent test commands are:

```bash
unset NO_COLOR NODE_DISABLE_COLORS
export FORCE_COLOR=1 CLICOLOR=1 CLICOLOR_FORCE=1
export GIT_PAGER=cat PAGER=cat
npm test
npm run build
CI=1 PLAYWRIGHT_FORCE_TTY=0 npm run test:e2e -- --reporter=list
git --no-pager diff --check
```

Current inventory: 264 unit tests in 54 files; 432 browser cases, 144 per configured
project. The initial browser inventory only lists cases; it does not execute
Playwright. With `set -euo pipefail`, a failing unit test stops the script before
build or browser execution, even though output is piped through `tee`. Running
`npm run test:e2e` manually is separate and does not run unit tests first.
Test inventory alone is not passing evidence. `test:e2e` intentionally builds
both the root and a repository-path release and validates their PWA files before the production-preview suite. Any failed/skipped/flaky test is NOT GREEN.

## Manual development inspection

```bash
cd ~/Desktop/FitfinityReact
npm run dev -- --host
```

Open the printed Local URL on the Mac or Network URL on a device on the same Wi-Fi.
This checks responsive UI. It does not prove the production PWA works.

## Production and installed-PWA acceptance

Stop other Vite servers first, then:

```bash
cd ~/Desktop/FitfinityReact
npm run build
npm run preview -- --host
```

`localhost` on the Mac supports service workers. A phone's ordinary HTTP LAN URL
is not a secure context and cannot establish installed-PWA/service-worker acceptance.
Use a trusted HTTPS test deployment for physical phone/iPad checks.

Local builds default to the origin root; `FITFINITY_BASE_PATH` selects a deployment directory. The Pages workflow reads the actual directory from Pages metadata. Publish the generated `dist/` together,
including the generated `dist/sw.js`; never publish the unexpanded `public/sw.js`
in its place. Keep the staff portal on its own origin when adding the public website.

After an update is downloaded, finish/save or cancel edits, close **all** Fitfinity
browser tabs and standalone windows, then reopen. Reloading one tab while another
remains open does not activate the waiting update. See [M4_ACCEPTANCE.md](M4_ACCEPTANCE.md).

Demo identities, localStorage and IndexedDB are local mock behaviour. Do not use
this frontend as an authenticated production staff system or enter real client data.

## M4.3 Pages readiness installer

Download the revision-specific `.sh` outside the repository and run it against the
verified M4.2E working candidate before committing or pushing. It verifies main,
M3 HEAD/tag, clean index and every baseline byte; applies the complete update;
runs 264 unit tests, builds, runs all 432 browser cases and checks integrity.
It accepts an exact M4.3 rerun after a failed gate. It does not reset/stash/stage,
install dependencies, start a development server, commit, push or publish.

```bash
bash "$HOME/Downloads/Fitfinity_M4_3_Pages_Readiness_2026-09-08.sh" "$HOME/Desktop/FitfinityReact"
```

After every gate passes, follow [GITHUB_PAGES.md](GITHUB_PAGES.md) to enable Pages,
push the demo checkpoint and record physical-device acceptance. Create the final
M4 freeze only after those checks. Once committed, this M3-based installer must
not be rerun on the new HEAD; use the normal verification commands for later checks.

The demo sign-in page lists available accounts. Initial demo password:
`FitfinityDemo1!`. Password changes persist locally; use only demo passwords.
Local account controls are frontend integration scaffolding; M5 provides real sessions.
