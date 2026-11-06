# Bread Bot command checkpoints

Status: checkpoint 1 authorized and underway; later checkpoints remain proposals. Work continues in Bread_bot. Existing migrated commands are the baseline; do not rebuild working features from scratch or blindly apply bread_bot_fixes.patch. See CHECKPOINT_1.md for the command matrix, 54-test offline verification, evidence button, and pending live acceptance.

## Starting point

- 23 original slash commands and 10 prefix command roots are registered in the new structure.
- Supabase migration, runtime connection, command registration and controlled Discord startup have been verified. The latest local suite contains 35 tests.
- /serverinfo has been restyled from the user's reference image.
- Prefix bread kick and bread warn now open a requester-owned evidence form before action, as requested during checkpoint 1. Shared slash callbacks recheck permissions on submission.
- NASA APOD has a real implementation; it still needs a live API/user acceptance check.
- The sent invitation for user 1401097287639502912 was deliberately deleted from the active Supabase scheduled_invites table at the user's request. Historical migration snapshots remain historical; do not re-import them and restore that deleted record.
- Hosting is not deployed. The user requires free hosting or a trial of at least two weeks and has approved GitHub Student benefits. Heroku student-funded Basic is the current recommendation, pending account benefit redemption and host selection.

## Approach and ordering

Recommended: finish and verify original command behavior, improve consistency, then add bounded feature groups. An appearance-first approach would polish commands whose edge cases remain untested; adding many new commands first would expand the verification backlog. Each checkpoint has a demonstrable result and its own completion criteria.

The roadmap is split by user-visible outcomes. Detailed designs and task-level implementation plans are written when a checkpoint is selected, so speculative features do not become accidental commitments.

## Checkpoint 1 — Verify the original command set

Deliver a command matrix recording slash/prefix support, inputs, required permissions, public/private replies, Supabase writes, audit behavior, and live test status.

| Group | Existing commands to verify |
| --- | --- |
| Utilities | ping, test, hello, coin_toss, botinfo, serverinfo, userinfo, help, apod |
| Moderation | kick, ban, unban, unkick, mute, purge, warn, warnings, blacklist, broadcast |
| Administration | setlog, setwelcome, get_channels / bread getchannels, filter and its prefix subcommands |

- Verify successful use, bad input, missing permissions, hierarchy failures, DMs, missing channels, API errors, and database outages where applicable.
- Test moderation only with designated test accounts in a dedicated test server. No real-member kicks, bans, purges, broadcasts, or DMs for smoke testing.
- Decide whether prefix kick/warn should remain redirects or become fully functional wrappers using the same services as slash commands. Proposed default: functional parity where the arguments can be represented clearly; slash-only forms remain appropriate for complex interactions.
- Document intended public/private visibility per command rather than assuming all responses should be public. Keep rejection details and sensitive moderation responses private.

**Done when:** every existing command has an explicit supported behavior, regression coverage for consequential failures, and a recorded live check or clearly stated external blocker. No command is marked complete just because it registers.

## Checkpoint 2 — Consistent command presentation and help

- Extract a small shared embed style from the new /serverinfo design: restrained colors, icons/thumbnails, readable sections and consistent timestamps.
- Improve /userinfo with avatar, account/join dates, role information and relevant permission summaries; improve /botinfo with useful uptime/latency information.
- Make /help category-based and generated from actual commands, with accurate parameters, prefix examples, permission notes and pagination where needed.
- Use consistent success/error wording and result visibility. Handle missing icons, uncached owners, long role lists and Discord field limits.

**Done when:** utility responses share one style, help accurately reflects installed commands, and layouts have been checked in desktop and mobile Discord. Existing functionality and permission checks remain intact.

## Checkpoint 3 — Complete warnings and moderation history

Recover the intent of the saved patch, not its old code verbatim.

- Add warning removal by stable warning ID and a clear-member-warnings operation with confirmation.
- Prefer marking warnings removed with moderator/reason/time rather than silently erasing the audit trail. Removed warnings do not count toward future escalation; historical numbers remain stable and are not reused.
- Add case/history lookup, with filtering and pagination, covering kick, ban, unban, timeout, warnings and partial failures.
- Make warning escalation configurable per server, with its current behavior explicitly shown before any setting changes. Define how removed warnings and repeated thresholds affect escalation before implementation.
- Verify every moderation action records the outcome/evidence and reports post-action audit failures truthfully without repeating the action.

**Done when:** a moderator can warn, inspect, remove and clear warnings in the test server; all changes are attributable; concurrency tests pass; old history remains readable; escalation decisions are deterministic.

## Checkpoint 4 — Administration and AutoMod management

- Add a clear setup/status command showing log/welcome channels, required permissions, filter state and AutoMod synchronization state.
- Improve filter word listing, validation and pagination; add explicit AutoMod resynchronization and controlled exemptions for channels/roles.
- Add welcome-message customization and a preview action with persistence and clear fallback behavior.
- Add role-management commands if wanted: grant/remove an ordinary role with actor/bot hierarchy checks and safeguards against privileged-role escalation.

**Done when:** settings survive restart, configuration errors are actionable, permission and role boundaries are tested, and local filtering/Discord AutoMod behavior matches the displayed state.

## Checkpoint 5 — Safe messaging and additional moderation tools

- Recover /sendmessage from the patch as a modal-based message/embed composer with a preview, destination selection, permission checks and explicit send confirmation.
- Improve broadcast with preview, channel selection, deliberate mention controls and a useful partial-delivery summary.
- Candidate additions: /unmute, /slowmode, /lock and /unlock. Implement reversible channel changes without overwriting unrelated permission overrides; remember the prior state for unlock.
- Add narrowly scoped cooldowns for expensive or disruptive commands, without concealing legitimate permission failures.

**Done when:** previews send nothing; only the authorized user can confirm; mentions behave as configured; channel tools restore prior state; failed sends do not cause duplicate delivery.

## Checkpoint 6 — Useful community commands

Candidate scope, to prioritize before implementation:

- /poll with clear closing/results behavior.
- /remindme with timezone-aware scheduling and cancel/list controls.
- /avatar and improved member/server information.
- Additional NASA features only after /apod passes its live checks.

Prefer one complete feature at a time. Polls and reminders need explicit persistence/expiry/restart behavior; they are not just a command that sends a message.

**Done when:** selected features handle restart, expiry, cancellation, unavailable external services, usage limits and server separation correctly.

## Checkpoint 7 — Scheduling and operational controls

- Review whether scheduled rejoin invitations are still wanted. Keep completed/deleted jobs from being replayed.
- Add an authorized status/list/cancel workflow for retained scheduling features, plus explicit pause/resume controls.
- Make failed jobs inspectable with error IDs and bounded retry policies. An uncertain external delivery must not be silently treated as a guaranteed failure.
- Verify worker startup, reconnect, graceful shutdown, retention behavior and error logs under real deployment-like conditions.

**Done when:** restart does not duplicate workers or completed jobs; cancelled/deleted jobs stay inactive; failures are inspectable without exposing credentials.

## Checkpoint 8 — Deploy and release

- Redeem/verify the chosen free or student-funded hosting offer before provisioning.
- Deploy one worker replica with secrets stored in host configuration. Keep old Render hosting stopped.
- Apply only new versioned migrations; do not replay the old Mongo import after production Supabase writes.
- Test harmless commands first, then permissions and designated test-account moderation. Verify logs, restart behavior and rollback instructions.
- Produce a release checklist and a short command guide for server administrators.

**Done when:** the bot survives a controlled restart, required commands work in the test server, no secret values appear in logs, host costs/credit conditions are understood, and only one production instance is running.

## Rules for every checkpoint

- Small feature files; shared services; Supabase calls only through repositories.
- Tests cover user-visible behavior and relevant failures, not merely implementation details.
- New database changes require versioned SQL, deliberate grants/RLS and migration checks.
- Preserve server separation, permissions, role hierarchy, and moderation history.
- Give a checkpoint update with delivered behavior, test evidence, remaining limitations and the next checkpoint. Pause only for required credentials, unresolved product decisions, or actions outside existing authorization.
- No new paid services, message sends, destructive live tests, or deployment without applicable authorization.

## Recommended next step

Start with Checkpoint 1, then Checkpoint 2. The highest-value additions after that are warning removal/history and /sendmessage, because they complete identifiable unfinished work in the saved patch. Checkpoints 4-7 can be reprioritized after the first two based on the server's actual needs.
