# Trainer — Developer AWS acceptance worksheet

| Test session | Fill in |
| --- | --- |
| Tester / date | |
| Developer AWS website URL | |
| Deployed version supplied by organiser | |
| Test account / receiving email address | |
| Device / browser | |
| Browser tab or installed app | |
| Partner for two-person checks | |
| Test client / purchase / session names | |

Use the deployed **developer AWS website**, with real sign-in, email and saved records. Use only designated test accounts, inboxes, clients and files—not real customer records. Confirm with the organiser that sign-in uses the developer Cognito service, changes save to the developer database and recordings use developer storage.

Write **Pass / Fail / Blocked / Not tested** in Result. Leave it blank until checked. Record what happened, screenshots and delays in Remarks. After saving, refresh and check from a fresh sign-in or second permitted device. Cancel/rejected actions must leave saved information unchanged. Mark a disabled feature or unavailable prepared record **Blocked**; do not switch to demo mode.

Trainer A requires approval for schedule changes; Trainer B has the permitted approval-free settings; each has a different assigned client. Trainer C is the replacement account. The organiser supplies separate lifecycle/deletion records, older/expired examples and a closed pay cycle. Do not change device time. Assisted interruption checks must be arranged for the developer environment without disrupting other users.

## Sign-in and account access

| Case | What to do | What should happen | Result | Remarks |
| --- | --- | --- | --- | --- |
| UAT-001 | Sign in. Refresh the page. Sign out, then press Back. | You see only your permitted information. Private pages do not return after sign-out. | | |
| UAT-002 | Try a wrong password, wrong code and expired code. Then sign in correctly. | Clear errors appear. Correct details let you sign in; another person’s information never appears. | | |
| UAT-003 | Use your designated developer AWS account. Complete password and authenticator setup using your authenticator app. Try fewer than 15 characters, a space, then a valid 15–128-character password. | Invalid passwords are rejected. A valid password works. Authenticator setup cannot be skipped. | | |
| UAT-004 | Change your password: try the wrong current password, mismatched confirmation, then correct details. Sign in again. | Only the valid change succeeds. Your new password works at the next sign-in. | | |
| UAT-005 | Use Forgot Password for your designated developer account. Read the actual email in your test inbox. Try an invalid/expired code, then the valid code and a new password. | Only valid recovery changes the password. Recovering a password does not remove the authenticator requirement. | | |
| UAT-006 | Look for Create Admin and try the supplied test link. | The action is unavailable or denied. No Admin account is created. | | |
| UAT-007 | Ask a manager to request a new login email for your test account. Try the old address before verification, then send/verify the new code yourself. Use the actual verification email in the Trainer’s designated inbox. | Old address remains in use until verification finishes. New address then works; earlier sign-ins end. A manager cannot verify for the Trainer. | | |
| UAT-008 | Ask a manager to replace your pending email request. Try the old request/code, then the current request. Ask the organiser to prepare an unresolved verification. Use only the prepared test inboxes; do not repeatedly send codes to force a fault. | Old requests cannot complete. Unresolved work blocks replacement. Changing the requested address does not itself send email or bypass resend limits. | | |
| UAT-009 | Open your profile. Edit permitted personal fields; try changing your name and rates. | Permitted personal changes save. Protected name and rates cannot be changed through your self-profile. | | |

## Clients, Trainers and package setup

| Case | What to do | What should happen | Result | Remarks |
| --- | --- | --- | --- | --- |
| UAT-012 | Browse the client and Trainer lists available to you; open a permitted profile and refresh. | Only permitted information appears. Inactive Trainers are not offered as eligible replacements; missing details are not invented. | | |
| UAT-013 | Open assigned Client A. Try Client B’s profile using the organiser’s test link. Try a missing-record link. | Client A is available as permitted. Client B’s private profile and missing records reveal no private information. | | |
| UAT-016 | View your own rates. Try changing them and try another Trainer’s financial information. | You can view permitted own rates but cannot change them or read another Trainer’s private financial information. | | |
| UAT-017 | Edit your availability. Try overlapping/invalid times, then valid times. Try changing another Trainer’s availability. | Valid changes to your own availability save. Invalid times and changes to another Trainer are rejected. | | |
| UAT-018 | Ask a manager to change whether your schedule changes need approval. Make a schedule change, then try changing the approval setting yourself. | The saved setting controls approval. You cannot grant yourself permission to bypass it. | | |
| UAT-T01 | Try Add Client, Add Trainer, package setup, permanent client reassignment and client/Trainer/package deactivation through supplied developer-site links. | Manager-only actions are unavailable or denied; no account, package or assignment changes. | | |

## Health notes and assessments

| Case | What to do | What should happen | Result | Remarks |
| --- | --- | --- | --- | --- |
| UAT-023 | Read/edit Client A’s general health notes. Try the initial assessment forms and Client B’s notes. | Assigned-client notes can be saved. The initial 11 forms and another Trainer’s client notes remain private. | | |
| UAT-027 | Open general notes for an inactive assigned client and try editing. Also try initial assessment forms. | Inactive notes are read-only; initial 11 forms remain inaccessible. No private form answers are disclosed. | | |

## Sessions, schedules and approvals

| Case | What to do | What should happen | Result | Remarks |
| --- | --- | --- | --- | --- |
| UAT-028 | Open Upcoming, All, weekly and monthly sessions. Open a session and press Back. | Upcoming starts near the next session. All is newest first. Weekly starts today and moves seven days; months start Monday. Empty dates have no false session count. Back restores your view. | | |
| UAT-029 | Open a busy weekly day and records from current and earlier assignments. | All permitted weekly sessions appear. Historical viewing does not allow restricted editing or full access to another Trainer’s client. | | |
| UAT-032 | Preview and confirm postponement. Try the same action on a started or completed session. | An eligible session becomes Open without a date/time or session number. Other bookings stay in place. Started/completed sessions cannot be postponed. | | |
| UAT-033 | Work with the designated test manager. Request a future time change that requires approval. Check the booking before approval. Approve as a manager. | Pending request leaves the original booking unchanged. Approval applies the reviewed change once, only if it is still allowed. | | |
| UAT-034 | Work with the designated test manager. Request a different Trainer and reject it. Make another request, arrange a conflicting booking, then try approval. | Rejection changes nothing. A conflicting or outdated request cannot be approved. Decision history remains available. | | |
| UAT-035 | Make time and Trainer changes that do not require approval. Also try a past/current start and an unavailable replacement. | Valid changes save directly. Permission to act without approval does not allow past times, conflicts or another Trainer’s records. | | |
| UAT-036 | Work with the designated test manager. Cancel A’s pending request as A. Try as B and after a decision. In two browsers, cancel and decide at nearly the same time. | Only the requesting Trainer can cancel a pending request. Only one competing action succeeds; the change and notices are not duplicated. | | |
| UAT-038 | Work with the designated test manager. Change a client’s fixed weekly times. Check approval behavior for both Trainers. Inspect a separately scheduled additional purchase. | Only eligible bookings change time; dates and Trainers stay the same. Separate purchase schedules remain unchanged. A supervised change waits for approval. | | |
| UAT-040 | After reassignment, compare the original Trainer, current Trainer and Trainer who completed the session. Repeat after permitted Undo. | Changing assignment does not rewrite who originally owned or performed the session. Unknown historical attribution stays unknown; the manager recording completion is not made the performer. | | |

## Exercise plans, outcomes and completion

| Case | What to do | What should happen | Result | Remarks |
| --- | --- | --- | --- | --- |
| UAT-041 | Create a plan with several exercises. Reorder, edit and remove an item, then save. | Saved order/details are correct. Prior results and recording history are retained. Editing a plan does not complete the session. | | |
| UAT-042 | Open Copy Previous Plan. Inspect preview; cancel, then repeat and confirm. Compare source and target recordings. | Cancel changes nothing. Confirm copies the latest eligible nonempty earlier-date plan. Open/same-day sessions are excluded; recordings are not copied to the new session. | | |
| UAT-043 | Try Copy Previous Plan with no earlier eligible plan, then with only a same-day plan. | No unsuitable plan is offered and the current plan is not replaced. | | |
| UAT-044 | Save actual exercise results and comments. Correct or remove a result and inspect history. | Results and prior versions remain traceable. Duration follows the booking. Signatures, used credits, completion and approved pay do not change. | | |
| UAT-045 | Save an explicitly empty outcome. Refresh and inspect progress. Compare a signed attended session with a no-show. | Empty results stay empty. Progress uses signed attended results from the selected purchase; no-shows and plan targets are not shown as actual results. | | |
| UAT-046 | Save a client summary. Try blank/overlong text, then replace with valid text. | Valid summary saves separately and previous text remains in history. Results, credits and delivery status do not change. | | |
| UAT-047 | Complete an eligible session with signer name and real signature strokes. Try missing name/ink and future/Open/cancelled sessions. | Only valid completion succeeds. Saved signature is read-only and one credit is used. Invalid attempts use no credit. | | |
| UAT-048 | Mark a session no-show, then correct it to a signature. Try changing the signature back to no-show. | One credit is used overall. Both records remain in history. The reverse correction is not allowed. | | |
| UAT-049 | Complete a session that leaves two credits. Refresh and check again. Repeat with a client who already has a later active purchase. | One applicable reminder appears, without duplicates. A later active purchase suppresses the renewal reminder as required. | | |
| UAT-050 | Open a completed/cancelled cover session and inactive client/package. Try changing results, summary, completion, schedule and recording. | Permitted history is visible, but restricted changes are blocked. Cover-session access does not expose the whole client profile or progress. | | |
| UAT-051 | Export a session PDF with captions and the optional summary. Unselect every available item and try to continue. | PDF includes only selected content. With no content selected, Continue is disabled. Captions do not include video files or claim a WhatsApp message was sent. | | |

## Client, Trainer and purchase lifecycle

| Case | What to do | What should happen | Result | Remarks |
| --- | --- | --- | --- | --- |
| UAT-058 | While signed in, ask the manager to deactivate your test Trainer account. Try existing/new sign-in. After reactivation, sign in again and check assignments. | Old sign-ins stay ended. Fresh sign-in is required. Reassigned sessions are not reclaimed. A separately disabled login is not silently re-enabled. | | |

## Messages, Undo, content and remuneration

| Case | What to do | What should happen | Result | Remarks |
| --- | --- | --- | --- | --- |
| UAT-059 | Filter Messages; mark a message read, then unread. View it as another recipient. Check Dashboard reminders. | Filters do not mark messages read. Each recipient keeps their own read state. Dashboard shows up to three reminders while the total counts all visible reminders. | | |
| UAT-060 | Dismiss a renewal reminder. Refresh; check another recipient and another client. | Only the permitted reminder changes. Reading alone does not dismiss it. Unrelated reminders remain unchanged. | | |
| UAT-061 | Review and Undo an eligible recent action. Inspect the restored values and original decision history. | Allowed values are restored and the reversal is recorded. The original action/approval remains visible in history. | | |
| UAT-062 | Try Undo after 24 hours, after a later dependent change or after losing access. Try completed/credited or approved-pay changes, acknowledgement, and package Add/Deactivate. | Restricted Undo is blocked without partial changes. Later changes may need reversing first. Used credits and ended sign-ins are not restored by Undo. | | |
| UAT-063 | Try content management and its supplied developer-site test link. | Content editing is unavailable or denied. No content can be changed. | | |
| UAT-064 | Open your own remuneration cycles and detail. Try another Trainer’s detail and the approval action. | Only your permitted own records are visible. Other Trainers’ finances and pay approval are unavailable or denied. | | |

## Reports, Exercise Library and recordings

| Case | What to do | What should happen | Result | Remarks |
| --- | --- | --- | --- | --- |
| UAT-067 | View progress for two purchases. Change exercise, filter and page; go Back. Expand a second chart. | Purchases do not mix. View choices are retained; only one chart is expanded. Unclear older results are not assigned to a purchase by guesswork. | | |
| UAT-068 | Prepare/download a report. Refresh without changes, then choose another purchase or change its content. | All recorded exercises are included. The PDF stays matched to the current purchase/content; an older preparation cannot replace it. | | |
| UAT-069 | On the developer website, prepare and share the PDF to your own designated test destination. Cancel another share. With assistance, test unsupported file sharing and PDF preparation failure. | Cancelled sharing records no share. Unsupported sharing offers Download/Open; preparation failure offers Retry PDF. The app does not claim a message was delivered. | | |
| UAT-070 | Try report history for your assigned client and another client using supplied developer-site test links. | Report history is unavailable to Trainers; no history entries are disclosed. Permitted report viewing/sharing remains separate. | | |
| UAT-071 | Browse Exercise Library. Try adding/editing an exercise and opening an inactive catalogue entry. | Active permitted exercises are visible. Catalogue editing is unavailable or denied; inactive entries are not offered. | | |
| UAT-073 | With assistance: Ask a manager to replace/remove a library attachment. Try the old attachment and a supplied restricted link. Check from a second browser using the developer website; do not manually remove stored files. | Removed/restricted media cannot be newly opened. You cannot replace or remove library attachments. | | |
| UAT-074 | On your phone/tablet, record or select a test video through the developer website. Save, then play it from a fresh sign-in or second permitted device. Use separate records for replacement/removal. Try a clip with sound with Include original audio unchecked, then checked; listen to the preview and saved clip. | The deployed app saves and retrieves the correct permitted recording across devices. Converted unchecked clips are silent; checked clips retain original sound if present. An unavailable conversion warns that the original audio is unchanged. Exercise/credit records stay unchanged. Picture, sound and playback are usable; record any delay or failure. | | |
| UAT-075 | Use prepared developer-site recordings that are recent, expired or intentionally unavailable. Try edits after completion/inactivity; with a manager, remove access while a recording loads. Do not change device time or storage settings yourself. | Expired/missing or newly restricted recordings do not play as if available. Restricted edits are blocked. Editing or Undo does not extend original expiry. | | |

## Two users editing and interrupted actions

| Case | What to do | What should happen | Result | Remarks |
| --- | --- | --- | --- | --- |
| UAT-077 | Keep an unsaved edit open while the other person saves a change. Wait for refresh, then Cancel and reopen. | Your draft is not silently replaced. Trying to save an outdated edit requires review. Cancel/reopen shows the latest saved information. | | |
| UAT-078 | Keep a client/session edit open while the manager reassigns or deactivates the record. Try Save and Back. | The old edit cannot save after access is lost. Private information does not return through Back or a late response. | | |
| UAT-079 | With assistance: Open confirmation, then leave or sign out while loading is delayed. Open a different confirmation afterwards. | The old dialog does not reopen or confirm the new action. No action saves without its required confirmation. | | |
| UAT-080 | With the organiser, arrange a lost confirmation after a real developer-site save has finished. Repeat for notes, plan, completion and recording. Use Check, refresh and sign in afresh. | The original saved result is recovered once. No duplicate record, credit, approval, message or recording appears. If the organiser cannot confirm the save finished, mark Blocked. | | |
| UAT-081 | With the organiser, arrange a developer-site save failure known to occur before saving. Check, retry if offered and try a quick double-click once. | No partial information remains. A permitted retry produces at most one result without duplicate credits/notices. If the failure point cannot be confirmed, mark Blocked. | | |
| UAT-082 | With assistance: Start saving, then close the editor while its result is unclear. Visit another page and return. Try changing the pending action’s values. | The original action can still be checked. Closing the editor does not cancel a save already sent. New values do not silently replace the unresolved action. | | |
| UAT-083 | With the organiser, let a developer-site save succeed but prevent the updated page from loading. Restore connection and refresh. | The app keeps the successful save status. Refresh shows the saved change without asking you to save it again. | | |
| UAT-084 | Disconnect while editing notes. Reconnect as the same signed-in user. Repeat after signing out or changing accounts. | Only the same sign-in can recover the unsaved draft. Private notes stay hidden while identity is unconfirmed. Another account does not inherit the draft. | | |
| UAT-085 | With assistance: Leave a slow page loading. Sign out and sign in as another user before the old page finishes. | The old user’s information, errors and dialogs do not appear for the new user. | | |
| UAT-086 | During a separately agreed developer AWS interruption/recovery check, revisit a finished save and a save interrupted before completion. Ask the organiser to confirm which occurred; do not stop shared services yourself. | Finished changes survive recovery. Interrupted work leaves no partial change or duplicate when checked/retried. Mark Blocked if the controlled check has not been arranged. | | |

## Devices, navigation and response time

| Case | What to do | What should happen | Result | Remarks |
| --- | --- | --- | --- | --- |
| UAT-087 | Use only the keyboard for menus, fields, date/select/suggestion controls and dialogs. Try required and disabled controls. | Labels, focus and errors are clear. Menus stay on screen. Disabled controls do nothing; closing a dialog leaves focus in a sensible place. | | |
| UAT-088 | Edit a client, weekly schedule and plan. Sign, record video and share PDF. Scroll long pages and use date/file pickers. | No trapped scrolling, missed taps or hidden Save/Cancel. Drafts are retained. Signature, recording and sharing are usable; note any lag. | | |
| UAT-089 | Rotate while editing. Open/close keyboard. Switch apps and return; use Back/Forward. | Portrait handling keeps your draft. Opening the keyboard does not wrongly rotate the interface. Another account’s private screen never flashes. | | |
| UAT-090 | Use lists with many records. Change filters/pages, open a profile/session, go Back and refresh. | Counts, sorting and selected views remain correct. Navigation starts collapsed and only one category expands. Missing records do not become invented sessions. | | |
| UAT-091 | On the developer website, time first/repeated page opening, reviews, saving, PDF preparation and recording playback. Try Cancel/Back during a delay. Record device, connection and approximate seconds. | Progress and outcome are clear. No frozen controls or duplicate actions. In Remarks, record any noticeable/disruptive delay even if the action succeeds. | | |
| UAT-092 | Sign out, disconnect and revisit previously opened private pages and recordings. | Private information is not accessible offline after sign-out. Seeing the app’s empty screen does not mean you can access an account. | | |

## Account delivery and assisted recovery

Use the designated developer accounts and receiving inboxes. Lost-authenticator recovery is performed by authorised support, not ordinary staff.

| Case | What to do | What should happen | Result | Remarks |
| --- | --- | --- | --- | --- |
| LIVE-01 | Check actual sign-in, authenticator setup, password-recovery email and email-change verification on the developer website. Check a fresh sign-in after each change. | Emails reach the intended test inbox, valid codes work, invalid/expired codes fail and the correct new credentials are required. | | |
| LIVE-03 | With authorised support, perform the arranged lost-authenticator recovery for your developer test account, then enrol a replacement authenticator and sign in. | Support verifies the correct person; old access ends and a replacement authenticator is required. Other staff gain no reset power. Mark Blocked if not arranged. | | |
