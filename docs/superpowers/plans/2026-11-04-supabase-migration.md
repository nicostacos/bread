# Supabase Migration and Bot Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Preserve the existing MongoDB records in Supabase and deliver a modular Discord bot with corrected authorization, persistence, lifecycle, and error handling.

**Architecture:** Feature command modules call services backed by injected Supabase repositories. SQL functions own atomic warning allocation, filter mutation, and leased invite processing. Migration tools preserve exact source snapshots and compare normalized destination data before runtime cutover.

**Tech Stack:** Python, discord.py, async supabase-py, PostgreSQL 17, pymongo/BSON for migration only, unittest with IsolatedAsyncioTestCase for offline regression tests.

**Spec:** ../specs/2026-11-04-supabase-migration-design.md

## Global Constraints

- Continue in Bread_bot and preserve all pre-existing local modifications and recovery files.
- Preserve existing command names and the bread prefix; no silent deletion of historical data.
- Keep secrets and raw snapshots Git-ignored and out of command output.
- Never mutate or delete MongoDB source records.
- Imported historical warnings must not trigger Discord moderation actions.
- One runtime replica, one managed invite worker, explicit async resource shutdown.
- The user confirmed the bot is offline and usually hosted on Render; leave it offline through final import validation.
- No hosting deployment is authorized by the request to research alternatives; prepare deployable source and report separately.
- Hosting must be free or offer a trial of at least two weeks. The user is approved for GitHub Student Developer Pack; see docs/hosting-options.md. Heroku Basic under redeemed student credits is the recommended candidate, pending host selection.
- Existing project stzbjhimxmzpvmrbnlxg is the selected Supabase destination. Public schema was empty at inspection; recheck before applying schema.

## Review Focus

- Legacy AutoMod IDs live in server_configs as well as a dedicated collection; preserve either source and reject conflicts (Task 1).
- Imported timestamps and Discord IDs must round-trip without timezone or numeric precision loss (Tasks 1-2).
- Database failures must not authorize blocked users or produce false success messages (Tasks 3-5).
- Reconnects and process cancellation must not duplicate jobs or leak clients (Task 6).
- A post-action logging failure must not repeat a kick/ban or misreport the Discord action as undone (Task 5).

## Files and interfaces

- `core/settings.py`, `core/logging.py`, `core/errors.py`, `core/checks.py`: validated configuration, logging, responses, and checks.
- `repositories/{client,configs,filters,warnings,cases,blacklists,invites}.py`: typed persistence, supplied through `Repositories` on the bot.
- `services/{filters,automod,moderation,invites}.py`: feature behavior independent of slash/prefix presentation.
- `commands/admin/{channels,filters,automod}.py`, `commands/moderation/{kick,ban,timeout,purge,warnings,blacklist,invites,broadcast}.py`, `commands/utility/{help,ping,info,fun,nasa}.py`: command extensions.
- `events/{messages,members,guilds}.py`, `tasks/scheduled_invites.py`, `bot.py`, `main.py`: event routing and runtime ownership.
- `scripts/{mongo_snapshot,migrate_supabase,validate_migration}.py`, `supabase/migrations/202611050001_initial.sql`: preservation, schema, normalization, validation.
- `tests/`: unittest test modules named per task below; `tests/integration/`: explicit isolated database checks.
- Restore `.env.example`; update `requirements.txt`, `.gitignore`, `README.md`, and deployment runbook. Remove old runtime cogs/helpers only after command parity checks pass.

### Task 1: Lossless source export and deterministic normalization

**Files:** Create `scripts/mongo_snapshot.py`, `scripts/migrate_supabase.py`, `tests/test_migration.py`.

**Interfaces:** `snapshot_database(db, output: Path) -> dict`; `normalize_snapshot(folder: Path) -> dict[str, list[dict]]`. IDs crossing JSON APIs are decimal strings. Source document identities are stored separately from generated UUIDs.

- [ ] Write failing tests: `test_preserves_unknown_bson_fields`, `test_preserves_large_snowflake_and_utc_date`, `test_reads_legacy_automod_id`, `test_conflicting_automod_ids_blocks_import`, `test_duplicate_or_malformed_settings_blocks_import`. Assert raw-document round-trip equality, stable source identifiers, correct AutoMod fallback, and explicit validation errors rather than dropped records.
- [ ] Run `.venv/Scripts/python.exe -m unittest tests.test_migration -v`; confirm the missing normalization implementation fails.
- [ ] Implement the exporter with collection counts, per-file SHA256 manifests, a new private destination directory per snapshot, and canonical Extended JSON. Implement schema normalization with explicit field mapping, retained source values, and deterministic import IDs. Normalize blacklist arrays to membership rows and maintain document-to-row validation mappings.
- [ ] Run the same command and require all tests to pass. Validate fixtures for all seven collections, including empty collections and pending/sent invite states.
- [ ] Save a task checkpoint recording changed files and evidence. Commit only task-owned files if Git metadata is writable; otherwise retain changes and record the limitation without staging unrelated user edits.

### Task 2: Restricted SQL schema and transactional behavior

**Files:** Create `supabase/migrations/202611050001_initial.sql`, `tests/integration/test_schema.py`.

**Interfaces:** Tables `guild_settings`, `guild_filter_settings`, `filter_words`, `warnings`, `moderation_cases`, `scheduled_invites`, `guild_blacklist_entries`, private raw import documents and migration runs. RPCs `add_warning`, `mutate_filter`, `claim_invites`, `finish_invite`, `deactivate_guild`; their typed wrappers belong to Task 3.

- [ ] Write failing isolated integration checks for no anonymous/authenticated table or RPC access, unique guild/user membership, parallel warning increments with one escalation decision at each threshold, concurrent filter additions with no lost update, and two workers claiming disjoint jobs.
- [ ] Run integration checks against an isolated database/schema and confirm missing schema failures. Never use destructive resets against the linked production project.
- [ ] Implement versioned SQL with constraints and explicit privilege revocation/grants. Raw source archives remain in a private schema. Warning numbering and escalation decisions use member-scoped transaction locks. Job leases use atomic claiming, bounded retries, and disabled-guild checks. Guild departure marks inactive and suspends jobs while retaining history.
- [ ] Apply and exercise SQL only in an isolated transaction/database first. Require concurrency and privilege checks to pass before applying the migration to the selected destination. Check existing objects and fail safely on unexpected conflicts.
- [ ] Record SQL validation evidence and checkpoint task-owned changes.

### Task 3: Async Supabase repositories and validated runtime configuration

**Files:** Create `core/settings.py`, `repositories/client.py`, the six feature repository modules, `tests/test_repositories.py`; update `requirements.txt`, `.env.example`, `.gitignore`.

**Interfaces:** `Settings.from_env() -> Settings`; `create_repositories(settings) -> Repositories`; `Repositories.close()`. Configs `get(guild_id)`, `update(guild_id, changes)`, `deactivate(guild_id)`; filters `get(guild_id)`, `mutate(guild_id, action, word=None)`; blacklist `contains/add/remove/list`; warnings `add(...)`, `list(guild_id,user_id)`; cases `record(...)`; invites `enqueue/claim/record_invite/complete/fail`. Repository rows use typed models, with UTC-aware dates and stable IDs.

- [ ] Write failing async tests with a fake Supabase transport asserting awaitable query execution, correct text ID handling, pagination beyond a default API page, absence of placeholder dummy objects, explicit missing-setting errors, propagated persistence failures, and client closure.
- [ ] Run `.venv/Scripts/python.exe -m unittest tests.test_repositories -v`; require expected missing-interface failures.
- [ ] Implement narrowly scoped repository methods over the official async client. Use RPCs for atomic operations; no Mongo operators or compatibility collections in runtime code. Keep Mongo packages only in migration dependencies. Read credentials without logging values and validate optional NASA/health settings.
- [ ] Run tests and inspect dependency resolution on the installed Python version; document any required supported Python version before deployment. Do not assume package installation alone proves runtime compatibility.
- [ ] Record evidence and checkpoint changes.

### Task 4: Central logs, safe responses, and authorization

**Files:** Create `core/logging.py`, `core/errors.py`, `core/checks.py`, `tests/test_errors.py`, `tests/test_checks.py`.

**Interfaces:** `configure_logging(settings)`, `respond(interaction, *, content=None, embed=None, ephemeral=True)`, `report_error(error, context) -> str`; `authorize(guild_id, user_id, repos) -> None` raises typed errors; `validate_target(guild, actor, target, permission) -> None` enforces runtime hierarchy and owner rules.

- [ ] Write failing tests asserting blocked prefix commands never invoke callbacks; missing guild is rejected; repository failure denies invocation; initial responses and deferred/already-responded followups are selected correctly; secret values and connection strings are absent even from formatted exception tracebacks; tracebacks retain useful error IDs.
- [ ] Run the two unittest modules and confirm expected failures.
- [ ] Implement shared checks and one response/error boundary for each entry point. Configure console/rotating handlers once, module loggers, contextual error IDs, and secret redaction. Avoid recursive database logging and duplicate traces.
- [ ] Run tests and require all authorization failure paths and logging-redaction assertions to pass.
- [ ] Record evidence and checkpoint changes.

### Task 5: Feature services and split commands

**Files:** Create the `services/` and `commands/` modules listed above, `tests/test_commands.py`, `tests/test_services.py`, `tests/test_nasa.py`; replace old cog loading after parity is proved.

**Interfaces:** `FilterService.settings/mutate`, `AutoModService.sync`, `ModerationService.execute`, `InviteService.send_once`; each command extension exports `async setup(bot)`. Bot injects `repos` and `services`; prefix and slash variants call the same service. Preserve the exact old slash/prefix command inventory in a test fixture before extraction.

- [ ] Write failing tests covering word-boundary alternatives, filter cache/persistence failures, AutoMod action type 2 and session ownership, welcome persistence failure, positive timeout/purge bounds, actual purge count, deferred broadcast, warning pagination limits, evidence persistence, partial audit failure after a successful action, and NASA image/video/error responses. Assert new command inventory equals the old fixture with no duplicates or unintended renames.
- [ ] Run `.venv/Scripts/python.exe -m unittest tests.test_commands tests.test_services tests.test_nasa -v` and confirm missing modules/incorrect old behavior fails.
- [ ] Extract each feature without copying old persistence calls. Apply shared runtime checks, defer slow work, use followups, and report partial results truthfully. Use supported Discord AutoMod APIs. Page warnings within embed count/length limits. Record moderation outcomes without retrying destructive actions after ambiguous failures. Perform bounded async APOD calls using the owned session and optional NASA key; default DEMO_KEY is explicitly documented.
- [ ] Run tests and offline extension loading with a fake repository; verify every command registers once without connecting to Discord. Remove superseded runtime imports only after parity passes.
- [ ] Record evidence and checkpoint changes.

### Task 6: Events, worker lifecycle, health, and deployment preparation

**Files:** Create `bot.py`, feature event modules, `tasks/scheduled_invites.py`, `tests/test_lifecycle.py`, `tests/test_invites.py`; simplify `main.py`; update `README.md` and `docs/deployment.md`.

**Interfaces:** `BreadBot(settings, repos_factory=...)`; `setup_hook`, `close`, event methods; `InviteWorker.run()` and `run_once()`; health reports `ready/degraded/not_ready` from bot/database state. Setup never waits for Gateway readiness before login completes.

- [ ] Write failing tests for exactly one task/session across repeated ready events, correct handler signatures, worker cancellation and client closure, database-unavailable health, guild leave retaining history/suspending jobs, job retry exhaustion, cached-user fallback fetching, and saved invite reuse after recoverable delivery failure.
- [ ] Run both unittest modules and confirm expected failures.
- [ ] Implement owned resources and task scheduling, authoritative message filtering plus command dispatch, welcome routing, retained guild records, and background error boundaries. Required extension/configuration failures abort startup. Remove obsolete keep-alive self-pinging behavior; health hosting is optional and platform-configurable.
- [ ] Run lifecycle/worker tests and full offline suite. Document the start command, one replica, secrets, logging, shutdown, and the recommended host once the independent alternatives research is complete. Do not deploy automatically.
- [ ] Record evidence and checkpoint changes.

### Task 7: Final snapshot, import, and content validation

**Files:** Complete `scripts/migrate_supabase.py`, create `scripts/validate_migration.py`, `tests/test_migration_validation.py`, `docs/migration-runbook.md`.

**Interfaces:** CLI export, `--dry-run`, import, validate. `validate_migration(snapshot, destination) -> ValidationReport` checks both source-document preservation and normalized content. Exit nonzero for mismatches. Re-import uses source IDs and cannot duplicate imported rows.

- [ ] Write failing tests for changed snapshot hashes, missing/wrong destination values, repeated import idempotency, empty source collections, source unknown-field retention, and a previously imported pending invite not executing during validation.
- [ ] Run tests, then implement import and validation with private input/output files and bounded request batches. Never interpolate raw data into executable SQL; parameterize database writes or use JSON payload APIs.
- [ ] Recheck project reference/schema and runtime secrets privately. Confirm the user-reported offline bot remains offline and take a fresh snapshot. Rehearse import, validate all normalized fields and per-guild counts, then repeat import to prove idempotency. Preserve the earlier 9-document backup as an additional checkpoint; current counts may differ and must be reported.
- [ ] Apply final data import and validate hashes/fields/counts, including the legacy AutoMod ID in server_configs. Save an audit report containing counts and hashes, not secret data. Do not change MongoDB or run Discord actions.
- [ ] Record exact completed verification commands and imported counts. If access is missing, finish independent code work and document the precise external blocker; never call cutover complete.

### Task 8: Whole-project review and runtime handoff

**Files:** All changed code, tests, migration/runbook, plan progress ledger.

- [ ] Run `.venv/Scripts/python.exe -m unittest discover -s tests -v`, compile source modules, run isolated SQL integration tests, verify command parity, check Git diff/ignored secrets, and rerun migration validation after the last import change.
- [ ] Invoke verification-before-completion and request a fresh whole-project review; address critical/important findings with regression tests. Do not publish secrets or raw snapshots in the review package.
- [ ] Set runtime configuration to Supabase only after validated import. Verify startup dependencies without connecting to Discord; live smoke tests must not kick, ban, purge, broadcast, or send pending invites merely for verification.
- [ ] Leave deployment stopped until the user chooses the new hosting platform. Explain rollback before/after new Supabase writes, summarize residual limitations, and provide the verified start/deploy instructions. No claim of deployed success without observed deployment evidence.

## Plan review and execution

Self-review: all approved design areas map to Tasks 1-8; listed interface names and consumers agree. The five review-focus conditions are exercised explicitly. Cross-task changes must update the ledger rather than silently weaken data preservation or checks.

Recommended execution: native implementation in this session, with one independent whole-project review at the end. The tasks share repository interfaces, making coordinated inline changes efficient. The hosting alternatives subagent is independent research requested by the user and does not change this implementation method.

Status: user approved design and requested continuation; native implementation and independent final review completed. See migration-progress.md for test evidence, decisions, completed data import, and the remaining private runtime credential requirement. No hosting deployment has occurred.
