# Supabase migration and reliability design

## Intent and scope

Continue in Bread_bot, preserve existing MongoDB data, replace runtime MongoDB access with Supabase, separate commands into feature modules, and resolve the defects in PROJECT_REVIEW.md. Keep current command names and the bread prefix. Preserve existing local modifications and the recovery snapshot.

## Approach

Recommended: staged refactor followed by validated import and cutover. A full rewrite makes command parity harder to verify. A Mongo-shaped adapter preserves accidental coupling and is not the target architecture. The user has requested the migration and listed fixes; this document makes implementation choices reviewable before work begins.

Use Python/discord.py and the async Supabase Python client for runtime queries, with SQL migrations and transactional PostgreSQL functions where atomic operations are required. Use a PostgreSQL connection only for schema installation and migration tooling. Do not provision a billable project without an account/project selection from the user. No Supabase connector, CLI, or destination configuration was found locally.

## Modules

- main.py: entry point and health server startup.
- bot.py: dependency creation, extension loading, command tree, managed tasks, shutdown.
- core/: validated settings, logging, shared checks, interaction response/error handling.
- commands/admin/: channels, filters, AutoMod.
- commands/moderation/: kick, ban/unban, timeout, purge, warnings, blacklist, invites, broadcast.
- commands/utility/: help, ping, information, fun, NASA.
- services/: shared business behavior for slash and prefix commands.
- repositories/: typed Supabase persistence operations, no Discord dependencies.
- events/: messages, members, guild lifecycle.
- tasks/: managed invite dispatcher.
- scripts/: Mongo snapshot, schema install, resumable import, validation.
- supabase/migrations/: versioned schema and transactional functions.

## Schema and preservation

Use text decimal Discord IDs at API boundaries, timestamptz for UTC dates, UUID identifiers for new warning/case/job records, and source collection/source document identifiers for imports.

| Mongo collection | Destination |
| --- | --- |
| server_configs | guild_settings |
| word_filters | guild_filter_settings and filter_words |
| moderation_warnings | warnings |
| moderation_cases | moderation_cases |
| scheduled_invites | scheduled_invites |
| guild_blacklists | guild_blacklist_entries |
| automod_rule_ids | guild_settings.automod_rule_id |

Store an exact BSON Extended JSON source snapshot separately from normalized records, including unknown fields and source IDs, so normalization does not discard data. Snapshot files are private, Git-ignored, hashed, and never printed. Duplicate settings, malformed IDs/dates, and conflicting documents must appear in a migration validation report and block cutover rather than be silently discarded. Raw snapshots are not exposed through the public Data API.

Use unique keys for guild settings, guild/word filters, and guild/user blacklist entries. Warnings have stable IDs distinct from display numbers. Allocate new warning sequence numbers under a per-member database lock and persist escalation decisions transactionally. Historical imported numbers and timestamps remain available. Do not replay historical kick/ban actions during import.

Invite jobs use bounded batches, atomic leases, retry limits/backoff, cached-user fallback fetching, and explicit failed states. Persist the created invite before DM delivery when possible. A crash between Discord accepting a DM and the database acknowledging it can still duplicate delivery; do not claim exactly-once behavior.

Enable RLS with no anon/authenticated grants to bot tables. Keep service credentials on the server. Limit SQL function execution privileges deliberately. Migration scripts never delete MongoDB documents.

Retention decision (builder proposal): leaving a Discord guild marks it inactive and suspends its pending jobs; it does not delete settings, blacklists, or moderation history. This intentionally replaces the current destructive on_guild_remove cleanup to honor the user's preservation requirement. Rejoining requires explicitly reactivating jobs so stale invites are not sent unexpectedly. No automatic historical purge is part of this change.

## Reliability changes

1. Register each event once with the correct signature; use one authoritative message handler and shared prefix/slash authorization. Reject DMs for guild-only commands, halt blocked invocation, and fail closed when authorization persistence is unavailable.
2. Own one HTTP session, one database client, and one instance of each task. Start jobs after readiness without awaiting readiness inside setup_hook. Reconnects must not create new jobs; shutdown cancels/awaits jobs and closes clients.
3. Correct filter regex boundaries; return coherent enabled/words settings without indexing a missing cache entry. Explicit failures replace the incompatible dummy database. Reset persists its enabled flag. Mutations are atomic where concurrent edits could lose updates.
4. Use Discord's supported AutoMod API, the alert action type 2, and persistent rule IDs. Never close the shared HTTP session inside a request. Surface partial persistence/AutoMod failures accurately.
5. Acknowledge slow interactions before external work and use followups after acknowledgement. Central handling must preserve response visibility and avoid a second initial response. Show concise errors with IDs; keep traces in logs.
6. Validate positive timeout/purge values and platform upper bounds. Report actual deleted message counts. Enforce actor/bot permissions, role hierarchy, guild ownership exceptions, and valid targets consistently.
7. Paginate warnings within Discord limits. Serialize numbering/escalation decisions in SQL. Persist moderation cases and evidence, including partial outcomes when the Discord action succeeded but logging failed. Do not automatically repeat destructive actions after uncertain failures.
8. Configure module logging with rotating files and console output; include error ID and command/event/guild context. Redact configured secrets and sensitive connection strings. Install prefix, application command, event, and background task handlers. Log at responsible boundaries without duplicate traces.
9. Health returns not-ready status until Discord and persistence are ready. Required extension load or configuration failures abort startup. Replace APOD placeholder with a bounded async NASA request, optional API key, response validation, and safe image/video handling.

## Data migration and cutover

1. Read-only source inventory and schema profiling; no bot startup or command synchronization during inspection.
2. Rehearsal snapshot and idempotent import into the selected new Supabase project. Validate raw-document hashes, normalized field values, per-guild counts, blacklist membership, filters/enabled flags, warning/case history, dates, and pending jobs. Global counts alone are insufficient.
3. Identify and stop the deployed bot writer and scheduled workers before the final snapshot. The deployment and its control method have not been identified yet; do not assume stopping a local process stops production.
4. Import the final snapshot, validate again, run database and command smoke checks, then change runtime configuration and resume one bot instance.
5. Retain MongoDB read-only as a rollback checkpoint. After new Supabase writes occur, rollback requires reconciling/exporting those writes; simply restarting the old bot would lose them. Document this boundary in the runbook.

## Validation

Use unit tests with fake repositories/Discord objects for authorization, guild checks, regex filtering, persistence failures, interaction response state, lifecycle/reconnects, bounds, pagination, and APOD parsing. Use real isolated PostgreSQL/Supabase integration checks for RLS, RPC permissions, warning concurrency, job leases, and import replay. Verify every extension and command registers once without logging into Discord. Import production data only after rehearsals pass.

## Access findings and outstanding dependencies

On 2026-11-04, local Python 3.14.2 has discord.py, pymongo, motor, and dotenv installed. Supabase, psycopg, and pytest are absent. The local .env has Mongo settings but no Supabase settings. A read-only source connection failed during DNS/SRV resolution with ConfigurationError/LifetimeTimeout, including outside the network sandbox. No record counts, exports, or database modifications have occurred.

Needed from the user: selected new Supabase project with SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, and SUPABASE_DB_URL configured privately in .env. Before final cutover, confirm the deployed bot location and how its writes/workers will be stopped. Mongo DNS connectivity must be restored or a complete BSON/Extended JSON export provided.

### Verified access update

The CLI is now authenticated and this checkout is linked to the user's selected project stzbjhimxmzpvmrbnlxg (Astro Discord Bot). A read-only database query found no tables in its public schema. MongoDB is now reachable. A private, Git-ignored canonical Extended JSON snapshot was saved to backups/mongo-20261105T023041Z, round-tripped, and SHA256-hashed per collection. Counts: server_configs 1, word_filters 1, moderation_warnings 4, moderation_cases 1, scheduled_invites 1, guild_blacklists 0, automod_rule_ids 0. Total: 9 documents. This is a rehearsal backup, not a write-paused cutover snapshot.

Source profiling found automod_rule_id in server_configs even though automod_rule_ids is empty. Import must read both locations, preserve this existing setting, and reject conflicting values instead of overwriting it with an empty collection's result. CLI database access is available for migration; runtime Supabase credentials are still absent from .env.

## Approval status

Design proposed; implementation and live cutover are not complete. This design preserves data as explicitly requested. Implementation details such as helper names and module sizes are left to the builder; behavior changes beyond the listed corrections require explicit scope decisions.

Builder review completed: the reviewer identified guild-leave retention as the only material design ambiguity; the retention proposal above resolves it for user review. Other remaining dependencies concern external access and the final deployed-writer pause.

References: https://supabase.com/docs/reference/python/realtime-api and https://supabase.com/docs/guides/database/postgres/row-level-security
