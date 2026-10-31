# Admin — Developer AWS acceptance worksheet

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
| UAT-006 | Look for Create Admin and try its test link supplied by the organiser. Do not use an Owner account. | Create Admin is unavailable or denied. No Admin account is created. | | |
| UAT-007 | Request a new login email for the test Trainer. Ask the Trainer to check the old address, then verify the new address themselves. Use the actual verification email in the Trainer’s designated inbox. | Old address remains in use until verification finishes. New address then works; earlier sign-ins end. A manager cannot verify for the Trainer. | | |
| UAT-008 | Review and replace a pending Trainer email request. Ask the Trainer to try the older request/code. Ask the organiser to prepare an unresolved send/verification. Use only the prepared test inboxes; do not repeatedly send codes to force a fault. | Old requests cannot complete. Unresolved work blocks replacement. Changing the requested address does not itself send email or bypass resend limits. | | |
| UAT-009 | Open permitted staff profiles and try editing allowed personal fields. Try restricted financial fields. | Permitted edits save; financial fields stay inaccessible. Owner-only actions are not available. | | |

## Clients, Trainers and package setup

| Case | What to do | What should happen | Result | Remarks |
| --- | --- | --- | --- | --- |
| UAT-010 | Add an individual client. Try blank required fields and invalid details. Use Back/Edit, then confirm valid details. | Required fields are checked. Back/Edit keeps entered details. Only final confirmation creates the client, purchase and reviewed sessions, once. | | |
| UAT-011 | Add a couple with different details for each person. Later edit only one person. | Each person keeps their own name, birthday and contacts. The couple’s display name does not replace either person’s name. | | |
| UAT-012 | Browse/search clients and Trainers. Filter active records. Open a profile and refresh. | Lists and profiles agree. Missing information is not made up. Inactive Trainers are not offered as eligible replacements. | | |
| UAT-014 | Edit client contact details and remarks. Cancel once, then repeat and save. | Cancel leaves saved values unchanged. Save changes only the intended details; the people remain the same. | | |
| UAT-015 | Create a Trainer using a designated test inbox. Try missing required fields and an existing email before valid details. Open the actual invitation and complete the new Trainer sign-in. | Invalid entries leave no usable partial account. One valid Trainer account/invitation is created. Required password/authenticator setup works; qualifications remain optional. | | |
| UAT-016 | Try viewing Trainer rates and remuneration through the menus and supplied test links. | Rates and remuneration are not shown. You cannot change rates or approve pay. | | |
| UAT-018 | Change whether Trainer A needs approval. Sign in as A and make a schedule change. | The saved setting controls whether approval is required. Trainer cannot give themselves permission to bypass approval. | | |
| UAT-019 | Create/edit a package template. Try 0, 366 and a decimal session count. Check 12/24/36 sessions. Deactivate/reactivate the template. | Invalid counts are rejected. Standard validity is 90/180/270 days, counting the start date. Inactive templates cannot be bought; existing purchases keep their terms. | | |
| UAT-020 | Add a package to an existing client. Review the prefilled details; cancel, then save. Try overlapping an older purchase, even if it has no sessions left. | Cancel creates nothing. Valid purchase keeps its own terms. An invalid overlap is rejected. | | |
| UAT-021 | Use developer-environment purchases prepared just before and on their Singapore activation dates. Refresh twice. Repeat with an inactive client or purchase. | An eligible purchase starts once on the correct Singapore date. Inactive records do not start. Previous credits, signatures and history stay unchanged. | | |

## Health notes and assessments

| Case | What to do | What should happen | Result | Remarks |
| --- | --- | --- | --- | --- |
| UAT-022 | Open the initial assessment forms for both people in the test couple. Save different answers. | Each person has their own 11 forms and separate answers. | | |
| UAT-024 | Save an empty assessment draft. Add answers, save, leave and return. Complete the form and open its history. | Saved drafts can be resumed. History records explicit saves, not every keystroke. Completed answers, person and assessor remain correct. | | |
| UAT-025 | Try zero, checked/unchecked choices, invalid answers and overlong text. Try completing an empty form and the prepared all-unchecked hurdle checklist. | Zero is retained. Unchecked answers stay unchecked. Invalid answers are rejected. Empty completion is rejected except the specifically saved hurdle checklist. | | |
| UAT-026 | Correct a completed assessment with a reason. Start a new assessment occasion. Void a test record with a reason. | Original answers remain in history. A new assessment is separate. A voided record cannot be changed again. | | |
| UAT-027 | Try editing an inactive client’s forms/notes. Inspect the organiser’s older assessment record. | Inactive records are read-only. Older answers are retained without invented questions or automatic replacement. | | |

## Sessions, schedules and approvals

| Case | What to do | What should happen | Result | Remarks |
| --- | --- | --- | --- | --- |
| UAT-028 | Open Upcoming, All, weekly and monthly sessions. Open a session and press Back. | Upcoming starts near the next session. All is newest first. Weekly starts today and moves seven days; months start Monday. Empty dates have no false session count. Back restores your view. | | |
| UAT-030 | Schedule an Open session. Compare its session record, package and used credits before and after. | The same session gains an allowed date/time and position. Its package and used credits do not change; no duplicate session appears. | | |
| UAT-031 | Edit a future session. Try unavailable time/Trainer, overlap, invalid duration and a date outside package validity, then a valid choice. | Invalid choices leave the booking unchanged. A valid save changes only the intended booking and preserves package terms. | | |
| UAT-032 | Preview and confirm postponement. Try the same action on a started or completed session. | An eligible session becomes Open without a date/time or session number. Other bookings stay in place. Started/completed sessions cannot be postponed. | | |
| UAT-033 | Work with the designated test Trainer. Request a future time change that requires approval. Check the booking before approval. Approve as a manager. | Pending request leaves the original booking unchanged. Approval applies the reviewed change once, only if it is still allowed. | | |
| UAT-034 | Work with the designated test Trainer. Request a different Trainer and reject it. Make another request, arrange a conflicting booking, then try approval. | Rejection changes nothing. A conflicting or outdated request cannot be approved. Decision history remains available. | | |
| UAT-036 | Work with the designated test Trainer. Cancel A’s pending request as A. Try as B and after a decision. In two browsers, cancel and decide at nearly the same time. | Only the requesting Trainer can cancel a pending request. Only one competing action succeeds; the change and notices are not duplicated. | | |
| UAT-037 | Reassign Client A permanently to C. Try an unavailable replacement first. Compare current/additional purchases and past sessions. | Invalid replacement changes nothing. Valid reassignment updates eligible future assignments, keeps times and terms, and preserves completed/started/cancelled history. | | |
| UAT-038 | Work with the designated test Trainer. Change a client’s fixed weekly times. Check approval behavior for both Trainers. Inspect a separately scheduled additional purchase. | Only eligible bookings change time; dates and Trainers stay the same. Separate purchase schedules remain unchanged. A supervised change waits for approval. | | |
| UAT-039 | With assistance: Use the prepared older schedules: one with a clear weekly match and one with an unclear match. Inspect the booking’s start/end times. | Clear matches work. Unclear matches or conflicts reject the entire change. Duration follows the displayed start/end times. | | |
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
| UAT-052 | Deactivate a test client with active and separately inactive purchases. Sign in as the assigned Trainer. | Client and affected purchases become inactive. Editing is blocked. Sessions, credits and history are retained. | | |
| UAT-053 | Reactivate that client after reviewing the schedule. Inspect separately inactive purchases and prepared older purchases with unclear history. | Only purchases disabled by that client action reactivate. Others remain inactive. Expiry/used credits stay the same; deleted sessions do not return. | | |
| UAT-054 | Deactivate one purchase, then review and reactivate it. Check other purchases and completed sessions. | Only that purchase changes. Expiry, used credits and history stay the same. Conflicts prevent reactivation; deactivation has no general Undo. | | |
| UAT-055 | On an inactive purchase, preview and confirm Delete Upcoming Sessions. Include Open, future, completed, cancelled and acknowledged sessions. | Only eligible unfinished Open/future sessions are deleted. Protected sessions and credits remain. Related pending requests are rejected; history remains. | | |
| UAT-056 | Use prepared developer records: Undo deletion within 24 hours with unchanged information and available recordings. Then try expired, changed and missing-recording examples. | Eligible Undo restores the original sessions but leaves the purchase inactive. Expired/conflicting cases are rejected without restoring only part of the records. | | |
| UAT-057 | Deactivate a Trainer with future and Open sessions. Try missing replacements, unavailable replacements, then valid replacements for the complete list. | Incomplete/conflicting choices change nothing. Valid confirmation moves all eligible sessions and disables the Trainer’s access. It does not silently change permanent client assignment. | | |
| UAT-058 | Ask the Trainer to try existing and new sign-in after deactivation. Reactivate the test Trainer, then ask them to sign in afresh and inspect assignments. | Old sign-ins stay ended. Fresh sign-in is required. Reassigned sessions are not reclaimed. A separately disabled login is not silently re-enabled. | | |

## Messages, Undo, content and remuneration

| Case | What to do | What should happen | Result | Remarks |
| --- | --- | --- | --- | --- |
| UAT-059 | Filter Messages; mark a message read, then unread. View it as another recipient. Check Dashboard reminders. | Filters do not mark messages read. Each recipient keeps their own read state. Dashboard shows up to three reminders while the total counts all visible reminders. | | |
| UAT-060 | Dismiss a renewal reminder. Refresh; check another recipient and another client. | Only the permitted reminder changes. Reading alone does not dismiss it. Unrelated reminders remain unchanged. | | |
| UAT-061 | Review and Undo an eligible recent action. Inspect the restored values and original decision history. | Allowed values are restored and the reversal is recorded. The original action/approval remains visible in history. | | |
| UAT-062 | Try Undo after 24 hours, after a later dependent change or after losing access. Try completed/credited or approved-pay changes, acknowledgement, and package Add/Deactivate. | Restricted Undo is blocked without partial changes. Later changes may need reversing first. Used credits and ended sign-ins are not restored by Undo. | | |
| UAT-063 | Create/edit content on the developer website. Cancel once, then save. In another browser, try saving an older edit. Ask a Trainer to check the restricted page. | Valid content saves and remains after refresh. Cancel changes nothing; older or unauthorized edits cannot overwrite it. This does not publish a new public website. | | |
| UAT-064 | Try remuneration cycles, Trainer pay details and approval through supplied developer-site test links. | All financial data and approval actions are unavailable or denied. No rates or amounts are disclosed. | | |

## Reports, Exercise Library and recordings

| Case | What to do | What should happen | Result | Remarks |
| --- | --- | --- | --- | --- |
| UAT-067 | View progress for two purchases. Change exercise, filter and page; go Back. Expand a second chart. | Purchases do not mix. View choices are retained; only one chart is expanded. Unclear older results are not assigned to a purchase by guesswork. | | |
| UAT-068 | Prepare/download a report. Refresh without changes, then choose another purchase or change its content. | All recorded exercises are included. The PDF stays matched to the current purchase/content; an older preparation cannot replace it. | | |
| UAT-069 | On the developer website, prepare and share the PDF to your own designated test destination. Cancel another share. With assistance, test unsupported file sharing and PDF preparation failure. | Cancelled sharing records no share. Unsupported sharing offers Download/Open; preparation failure offers Retry PDF. The app does not claim a message was delivered. | | |
| UAT-070 | Open report history for different clients/purchases and pages. With assistance, recover a save whose confirmation was lost. | History is correctly ordered and grouped, with ten rows per page. Trainer cannot read it. Recovery does not share/download again or duplicate the entry. | | |
| UAT-071 | Browse Exercise Library. As manager add/edit an exercise; try duplicate/reserved name, name over 180 characters and description over 2,000. | Invalid entries are rejected. Trainers see active exercises but cannot edit the catalogue. Existing session plans retain their saved names. | | |
| UAT-072 | Attach an allowed image/video. Try empty, unsupported and over-50-MiB files. Save, refresh and open the attachment. Reopen from a fresh sign-in or second permitted device on the developer website. | Allowed JPEG/PNG/WebP/MP4/WebM/MOV within the limit works. Invalid files are rejected, not shown as successfully saved. | | |
| UAT-073 | With assistance: Replace/remove a library attachment. Try opening the old attachment and try as someone without access. Interrupt an upload. Check from a second browser using the developer website; do not manually remove stored files. | Removed or private attachments cannot be newly opened. Interrupted saving can be checked without creating duplicate attachments. | | |
| UAT-074 | On your phone/tablet, record or select a test video through the developer website. Save, then play it from a fresh sign-in or second permitted device. Use separate records for replacement/removal. Try a clip with sound with Include original audio unchecked, then checked; listen to the preview and saved clip. | The deployed app saves and retrieves the correct permitted recording across devices. Converted unchecked clips are silent; checked clips retain original sound if present. An unavailable conversion warns that the original audio is unchanged. Exercise/credit records stay unchanged. Picture, sound and playback are usable; record any delay or failure. | | |
| UAT-075 | Use prepared developer-site recordings that are recent, expired or intentionally unavailable. Try edits after completion/inactivity; with a manager, remove access while a recording loads. Do not change device time or storage settings yourself. | Expired/missing or newly restricted recordings do not play as if available. Restricted edits are blocked. Editing or Undo does not extend original expiry. | | |

## Two users editing and interrupted actions

| Case | What to do | What should happen | Result | Remarks |
| --- | --- | --- | --- | --- |
| UAT-076 | Work with the other manager in a separate browser. Both edit the same record; Owner saves first, then Admin saves the older edit. Repeat for client details, plan and schedule. | First save stays. Second user sees a clear message that changes have been made and must review them; no silent overwrite occurs. | | |
| UAT-077 | Keep an unsaved edit open while the other person saves a change. Wait for refresh, then Cancel and reopen. | Your draft is not silently replaced. Trying to save an outdated edit requires review. Cancel/reopen shows the latest saved information. | | |
| UAT-078 | Ask the assigned Trainer to join you. While Trainer edits, manager reassigns or deactivates the record. Trainer tries Save and Back. | The old edit cannot save after access is lost. Private information does not return through Back or a late response. | | |
| UAT-079 | With assistance: Open confirmation, then leave or sign out while loading is delayed. Open a different confirmation afterwards. | The old dialog does not reopen or confirm the new action. No action saves without its required confirmation. | | |
| UAT-080 | With the organiser, arrange a lost confirmation after a real developer-site save has finished. Repeat for client creation, profile, plan, completion, request approval and recording. Use Check, refresh and sign in afresh. | The original saved result is recovered once. No duplicate record, credit, approval, message or recording appears. If the organiser cannot confirm the save finished, mark Blocked. | | |
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
