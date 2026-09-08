# M4 frontend service and configuration contract

`App` accepts a `services` prop. Its default composition is
`defaultPortalServices → createPortalServices(mockPortalAdapter)`.
The factory has no imports from mock implementations or seed data. Screens receive
records, policy and asynchronous callbacks; persistent reads/writes belong to adapters.
The only UI composition import is in `PortalDataProvider`. Its module exports
only the provider component for React Fast Refresh. The single `PortalData`
context and `usePortalData` hook live in `src/hooks/usePortalData.js`; the provider
and App consume that module. Refresh, snapshot and service behavior are unchanged.

## Adapter surface

- `load()` resolves `{user, policy, capabilities, data}`. `user: null` means signed
  out. The mock adapter additionally supplies `accounts` and `demoPassword` for demo
  sign-in. An API adapter omits those values and uses the account text field.
- `session(method, args)` implements `signIn`, `signOut`, `changePassword`; the demo
  adapter additionally implements `switchDemoIdentity`. Successful sign-out clears
  the displayed private snapshot immediately. `capabilities.demoControls` alone
  exposes demo identity switching and reset controls.
- `invoke(domain, method, args)` implements the exported `PORTAL_OPERATIONS` map:
  clients, trainers, sessions/media, exercise catalogue/reference media, packages,
  content, Messages, requests and remuneration. Return the saved canonical record
  or existing documented domain result; reject failed mutations with an `Error`.
- `reset()` is a demo capability, not a production workflow.
- Errors have a human-readable `message`; `code: 'SESSION_EXPIRED'` clears private
  UI and returns to sign-in. A failed initial load offers Retry; failed refreshes
  retain a retry banner. Refresh failure after a committed mutation must not be
  reported as a failed save or invite duplicate creation.
- All factory methods return Promises, including mock reads. Focus, storage changes
  and a 30-second clock tick refresh the snapshot. Generation checks reject stale
  overlapping load responses. Replace polling with events later without changing
  feature screens.

The API must authorize every read and write using its authenticated principal;
legacy actor arguments are compatibility context only. Never trust a browser role.
The mock adapter rejects scoped/owner-only mutations and expired sessions, but all
mock assets and browser storage remain accessible to someone controlling the browser.
This is not Glofox authentication or a production authorization system.

## Loaded records and policy

`data` provides `users`, `clients`, `trainers`, `sessions`, `messages`, `packages`,
`exerciseLibrary`, `contentEntries`, and `remunerationViews` for visible accounts.
The API returns only authorized records. Each remuneration view has `key`, `cycle`
(start/end/payout), and canonical `trainers` breakdowns/totals/revisions. Calculations
live behind the mock adapter; production amounts must come from the server.

Policy fields supplied by the adapter:

| Field | Consumers |
|---|---|
| `timeZone`, `locale`, `currency` | Business clock and remuneration presentation |
| `packageValidity`, `weeklyFrequencies`, `freeGymMinimumFrequency` | Package setup and onboarding; purchased terms remain snapshots |
| `availability`, `defaultCountryCode`, `defaultRelationship` | New form drafts |
| `trainerRates`, `trainerTypes`, `approvalDefaults` | Trainer onboarding |
| `exerciseCategories`, `exerciseDefaults` | Catalogue and session planning |
| `password.minimumLength/maximumLength`, `sessionHours` | Mock account validation/session expiry |
| `remuneration` | Mock cycle/peak-window rules; server uses authoritative rules later |

Demo business records and defaults live under `src/data`. UI labels, routing keys,
calendar arithmetic, supported media formats and validation bounds remain code;
these are not invented client data. No implicit owner, demo exercise catalogue or
purchased package is selected when service records are missing.

## New record contracts

- Client signature: `acknowledgement.signature` is normalized SVG strokes containing
  finite `{x,y}` points on a 600×200 surface (bounded strokes/points). Names alone do
  not satisfy new signature completion. `late_no_show` has no client signature.
  Preserve historical records that predate drawn evidence; never fabricate ink.
- Session results: `exerciseResults` contains stable plan-row `id`, `name`, measured
  `loadKg`, integer `reps` and `sets`. Signed completion snapshots numeric plan
  loads only when no result list was separately saved; explicitly blank or
  non-numeric loads do not become measurements. Completed, attended sessions
  update points keyed by session/result. Corrections replace derived points;
  legacy points without session links are retained as a baseline.
- Content: `{id,key,title,body,status,version,createdAt,updatedAt}`. Status is
  `draft`, `ready` or `archived`. Keys are unique; edits require `expectedVersion`.
  Text preview is escaped, not executed as HTML. These generic entries do not
  define or publish the future public website's page templates.
- Session video: `loadVideo`, `saveVideo`, `removeVideo` are service calls. Mock
  storage uses immutable IndexedDB byte records; metadata is committed afterward.
  Failed metadata writes delete only the new blob. Old blobs are cleaned after
  commit; cleanup failure may leave an unreferenced blob, never a broken replacement.
  API integration should return media IDs and fetch Blobs from protected endpoints.
  Metadata alone is not the video payload. Unsupported capture/storage is an error;
  unsupported local processing can retain the original marked deferred.
- WhatsApp: `whatsappOpenedAt`/`whatsappOpenCount` record a launched handoff only.
  A blocked window exposes an explicit link and records no delivery. Text export
  does not attach video files or claim WhatsApp sent/read confirmation.

## Backend work still required

Implement authenticated sessions, durable database storage, authorization, atomic
credit/progress writes, version conflict handling, idempotent creation/completion,
protected media upload/download and migration of any data retained from the demo.
The API adapter should translate transport errors and response DTOs to this contract.
Run the same scenarios against that adapter. These interfaces reduce UI rewrites;
they do not make a production backend connection automatic or complete.

Public pages, Glofox member access, cloud video processing/delivery and physical PWA
acceptance remain separate work. Owner-profile editing fields, automatic renewal eligibility/purchasing rules
and a Copy Previous Plan UI remain undecided.

## Message categories and dashboard renewals (M4.2D)

`MessageInbox` in the canonical Messages module owns both entry points: list,
popup, recipient visibility, related records, read/unread mutations and overlay
history. The dashboard requests the `renewals` category and previews three rows;
View All Renewals opens `#/messages/renewals`. Its count and rows come from the
same loaded records and ordering, including read items. It does not invent
renewal thresholds, generate notifications or change recipients. The prominent
Total follow-ups badge uses the complete visible renewal-message count before
the three-row preview is sliced. Reading a notification does not settle a renewal;
the existing contract has no renewal completion lifecycle or distinct-client total.

Adapters may supply a stable `message.category` key: `renewals`, `approvals`,
`sessions`, `people`, `remuneration` or `updates`. The canonical classifier in
`messageFilters.js` otherwise maps existing typed `kind`, request and record
metadata. It never parses message titles. Unknown kinds appear under Updates
and All; the UI display labels are presentation constants. Renewal event creation
and server recipient authorization remain backend responsibilities.

Category controls reuse the canonical `ProfileNavigation` component and CSS used
by client/trainer profiles, including its 700px inline/menu boundary. The former
Messages-only pill markup and styling are removed. Filtering composes with existing
text/date filtering and pagination.
Selecting a category never marks records read. Dashboard and full inbox saves
use the same injected async service callbacks; a failed read mutation keeps the
list usable and exposes retry feedback. Production authorization and complete
server pagination/query semantics must be enforced by the API adapter.

## Calendar date access (M4.2D)

Weekly/monthly calendars remain the dashboard views. Date controls open
`#/dashboard/day/YYYY-MM-DD` using the existing app navigation owner; the shared
ModalPortal displays that day's already-scoped session records and owns focus
and scroll locking. Closing uses app history; opening a session replaces the
popup route so session Back returns to the preserved calendar view/date. This
restores access to compact monthly cells without a permanent daily agenda or
new backend operations. Native Back/Forward and Escape/Close are covered.

Owner Weekly/Monthly and trainer Monthly display seven-column date grids with
one session-count button per day, including zero days. Count buttons open the
complete scoped day. Owner popups group that day's records by trainer; each
group retains chronological order. Trainer Weekly shows seven daily sections
with one compact time/client row for every session. There is no preview cap,
+more button, viewport subscription or booking-capacity rule. The same behaviour
applies on desktop, tablet and phone. Session names and counts come from the
existing scoped records, not UI fixtures or a separate data source.

The visual reference is Fitfinity's behavioural Oracle prototype:
`LimYouSheng/fitfinityPWA`, `assets/css/core.css`, blob
`e6e956f75d8357256fe1ff2bc4aace1c44551ee8`. Its neutral grid (`#0f1116`), session
surface (`#181b25`), blue accent (`#4f67f6`) and owner count treatment
(`rgba(79,103,246,.10)` background, `#dfe4ff` text) live in canonical `styles.css`.
The superseded preview cards, overflow controls and compact-time CSS are removed.

## Password requirement notifications (M4.2D)

The Change Password form reads the adapter's `password.minimumLength/maximumLength`
for the displayed requirement and validation. Focusing New password or selecting
Password requirements uses the shared notification provider; invalid length,
missing current password, mismatched confirmation and unchanged password also
notify before confirmation or service calls. No character-class rules are invented.
The service still verifies the current password and validates every mutation;
failed saves preserve the draft. Concise labels replace static instructional copy.

## Physical acceptance repairs (2026-09-08)

- `useAppNavigation` owns a per-history-entry, account-scoped view state context.
  Tabs, searches, filters, pagination and selected progress exercise survive Back,
  Forward and reload. Calendar popups and message categories carry the current
  view into their related route. Editable drafts remain local and use the edit
  guard. Scroll restoration is shared with native Back, app Back and swipe Back.
- Navigation sections use the same collapsible controls on mobile, tablet and
  desktop, start collapsed on sign-in/account changes, and retain their open
  choices across responsive layout changes. Trainer client lists omit the trainer
  filter while the service still scopes visible clients to that trainer.
- `sessionActionError(session, today)` blocks signature/no-show completion and
  WhatsApp before the training date. UI uses the provider clock; the service
  independently checks the current clock in `policy.timeZone` before mutation.
  The rule unlocks on the calendar date, not at the session start time. A future
  API must enforce this with its authoritative clock before opening a share flow.
- Signed completion snapshots valid numeric saved-plan loads when no separate
  outcome result list exists. Explicit outcome results take precedence; an
  explicitly saved empty list stays empty. Non-numeric loads are not guessed.
  No-shows do not contribute strength points. Corrections rebuild points by
  session/result ID without another credit debit. Older signed sessions are
  projected through the same progress calculation when loading the mock snapshot.
- Package count is free text with a numeric keyboard. `packageSessionCount`
  supplies inclusive limits (mock policy: 1–365); form and service reject blank,
  decimal, signed, exponential or out-of-range input. The service stores an
  integer. `packageValidity` preserves explicit rules and `packageValidityRule`
  supplies proportional days for other counts (mock: 90 days / 12 sessions,
  rounded up to whole days). Confirmation displays the computed term. Existing
  purchased package snapshots and schedules are unchanged by template edits.
- WebKit media fallback remains deferred: originals can retain audio and unknown
  duration. The future backend must validate/transcode/caption them before final
  delivery; this demo has no cloud processing worker.


## Progress report action history

Client Progress offers **View Export/WhatsApp History** only to the owner. Report
export/share actions remain available to the owner and assigned trainer. General
Information has no renewal status, renewal date or renewal history workflow.

- `clientService.recordProgressReportAction(clientId, {id, kind})` appends one event
  and a saved-action message, returning `{id, clientId, kind, at, by:{id,name}}`.
  `kind` is `csv_export` or `whatsapp_opened`. The UI generates a unique action ID
  and the adapter derives the authenticated actor and authoritative timestamp.
- A retry with the same ID, client, kind and actor returns the original event,
  without another timestamp or message. Reusing an ID for a different action is
  rejected. Failed validation, authorization or storage commits nothing.
- `clientService.progressReportHistory(clientId)` returns only that client's
  events, newest timestamp first. The service requires an active owner identity;
  a caller-supplied owner argument cannot grant access. History is omitted from
  ordinary snapshots and never supplied to trainer UI. The mock database's
  `progressReportEvents` list is an adapter detail, not a component dependency.
- Timestamps are ISO UTC instants formatted in `policy.timeZone`. The production
  API must use its server clock and principal rather than accepting those fields
  from the browser. Future filtering/pagination can be implemented in this service.
- CSV events record a download initiated by the app, not proof of a saved file.
  WhatsApp events record a successfully opened handoff window, not a sent/read
  receipt. Blocked or failed window launches add no event. The browser launch
  runs synchronously in the user action, before the asynchronous history write.
- If saving history fails after launch, the UI offers **Retry History Save** with
  the same action ID and does not launch/download the report again. History loads
  have their own retry state; entries are displayed ten per page.
- Opening the history view is read-only. It preserves the Progress tab and
  selected exercise. Empty progress charts still permit the owner to view history.
- The retired manual renewal workflow is not used. Previously stored renewal
  metadata is preserved without inventing CSV or WhatsApp actions from it.

These mock records are browser-local. The backend must provide durable storage,
access control and idempotent writes; a WhatsApp integration would be required
for actual delivery receipts.
