# Publish the M4 staff demo

M4.3 prepares a GitHub Pages demo for installed-PWA acceptance. The public website
and Glofox member authentication remain deferred; backend/auth starts at M5.
Use demo accounts and sample records on this publicly reachable frontend.

## 1. Apply and verify on the Mac

Keep the installer in Downloads, outside the repository. Stop an existing preview
on port 4173, then run:

```bash
bash "$HOME/Downloads/Fitfinity_M4_3_Pages_Readiness_2026-09-08.sh" "$HOME/Desktop/FitfinityReact"
```

It requires the exact M4.2E candidate with M3 HEAD/tag and an unstaged index.
It applies M4.3 and runs 264 unit tests / 54 files, production builds, PWA checks,
all 432 browser cases / 15 files, then source integrity and code health. Unit failure
stops build/browser execution. Browser failures, skips, retries or incomplete totals
stop completion. The initial browser inventory is a list, not test execution.

Continue only after `=== COMPLETE — ALL GATES PASSED ===`. Keep the printed
fingerprint and report directory with the acceptance record. The installer does
not install dependencies, commit, push or publish. If it reports an unfamiliar
source or HEAD, preserve the checkout and reconcile the reported difference.

## 2. Select the Pages publishing source

Open [FitfinityReact Pages settings](https://github.com/LimYouSheng/FitfinityReact/settings/pages).
Under **Build and deployment → Source**, select **GitHub Actions**. The committed
workflow handles building and uploading `dist/`; no generated output branch is needed.
This is the publishing-source setup recommended by [Vite's GitHub Pages guide](https://vite.dev/guide/static-deploy#github-pages).

## 3. Push the verified demo checkpoint

Review the intended M4 changes, including the new workflow and verification scripts:

```bash
cd "$HOME/Desktop/FitfinityReact"
git --no-pager status --short --branch
git --no-pager diff --check
git add -- .gitignore .github README.md docs index.html package.json public src tests vite.config.js scripts
git --no-pager diff --cached --check
git --no-pager diff --cached --stat
git commit -m "Prepare M4 staff demo for GitHub Pages"
git push origin main
```

The installer does not alter dependency versions or the lockfile. Generated `dist/`
and `dist-pages/`, local environment files, dependencies and test reports stay out
of the commit. This is a demo deployment checkpoint; the final M4 freeze/tag follows
physical-device acceptance. After committing, do not rerun the installer that requires
the old M3 HEAD. Use the repository's verification commands for subsequent checks.

## 4. Wait for the deployment

Open [repository Actions](https://github.com/LimYouSheng/FitfinityReact/actions) and
select **Verify and publish the staff demo**. Its order is:

1. Install the locked dependencies and pass the unit gate.
2. Install Chromium/WebKit, build and validate root/repository-path releases, then pass the full browser gate.
3. Read the configured Pages location, build for that directory and verify its PWA files.
4. Upload the complete `dist/` and publish through the dependent deployment job.

A failed test or build prevents publication. Workflow actions are pinned to commits;
the workflow uses Node 24. GitHub's [custom Pages workflow documentation](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
describes the artifact and deployment-job arrangement.

Use the URL shown by the successful deployment. With the current repository name
and no custom domain, the expected address is
[Fitfinity staff demo](https://limyousheng.github.io/FitfinityReact/).
This document does not certify that the first deployment has run.

If Pages was not enabled before the push, set its source, then rerun the failed
workflow from Actions. Read the failing step before changing source or clearing
browser data. A green build with an old installed UI can mean a worker is waiting;
finish edits and close all app windows before reopening.

## 5. Install and accept on real devices

Open the successful HTTPS deployment on the phone, iPad and desktop. Use the
browser's installation/Add to Home Screen action where available. Record the exact
device, OS/browser, commit, candidate fingerprint and URL in [M4_ACCEPTANCE.md](M4_ACCEPTANCE.md).

Check owner/trainer navigation, calendars and renewals, password/sign-out flows,
client signatures and media; then check standalone launch, offline reopening,
Back/swipe and an update from a later verified deployment. Save/cancel edits, close
all browser tabs and standalone windows, then reopen to activate a waiting update.
An installed app still uses the current mock services and browser-local records.

The new M4.3 full Mac browser run, first Actions deployment and physical-device
checks remain pending until their actual receipts are recorded. After acceptance,
freeze M4 and start M5 backend/auth using the existing service contract.

## Hosting configuration

The runtime uses Vite's resolved base directory for the logo, worker registration
and scope. The manifest uses relative IDs, icons and launch URLs. The generated
worker includes that directory in its revision and cache namespace; cleanup leaves
other app directories and legacy unscoped caches alone. Hash routing keeps detail
URLs under the same app document without a server rewrite.

Local builds default to `/`. The workflow derives `FITFINITY_BASE_PATH` from Pages
metadata, so a repository rename or custom-domain location does not require editing
components. The `/FitfinityReact/` path in `build:pages-test` and browser fixtures
is the representative subpath test case. For a local repository-path preview:

```bash
cd "$HOME/Desktop/FitfinityReact"
FITFINITY_BASE_PATH=/FitfinityReact/ npm run build
npm run verify:pwa -- dist /FitfinityReact/
FITFINITY_BASE_PATH=/FitfinityReact/ npm run preview -- --host
```

Open the printed URL under `/FitfinityReact/`. A phone's HTTP LAN address is only
a responsive preview; use the hosted HTTPS site for installed-PWA acceptance.
`npm run test:e2e` rebuilds and validates both paths before testing, and does not
run unit tests itself. The installer and workflow enforce unit-first sequencing.

Publish generated `dist/sw.js`, never the placeholder template from `public/`.
Production AWS hosting still requires controlled worker cache headers, previous
hashed-bundle retention, real authentication and backend authorization. This Pages
demo workflow does not configure those production hosting capabilities. Keep the
later staff origin separate from public/member services as described in
[PRODUCTION_ARCHITECTURE.md](PRODUCTION_ARCHITECTURE.md).
