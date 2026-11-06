# Project restart review

Continue in Bread_bot. It retains Git history and bread_bot_fixes.patch.
Unique files from Project Revamped were preserved under recovery/project-revamped-2026-11-04 before cleanup. The manifest records SHA256 hashes and whether each source file is preserved in the canonical tree or recovery snapshot. The recovery .env is private and must remain ignored by Git.

## Confirmed source findings

- main.py registers event helpers whose signatures require an additional bot argument. Its welcome wrapper also omits that argument.
- Background tasks start in setup_hook and on_ready, allowing duplicates at startup and reconnects. HTTP sessions are overwritten without explicit cleanup.
- The prefix blacklist function reports rejection but does not stop execution. Database blacklist failures default to allowing commands.
- Revamped puts slash blacklist registration and index creation inside the member-join handler rather than startup.
- Both message filters mix raw regex boundaries with ordinary backspace escapes. Failed database reads can leave the filter cache missing an entry that callers index directly.
- The dummy database lacks required find_one, cursor sort, and acknowledged result behavior. Its async find conflicts with Motor-style callers.
- AutoMod alert payloads use type 4 instead of type 2. The update fallback enters the shared ClientSession as a context manager and closes it afterward.
- Welcome configuration can report success after persistence fails. Filter commands ignore failed save results.
- Broadcast and other commands do slow work before acknowledging interactions. Some error paths attempt another initial response after responding already.
- Guild-only checks are inconsistent. Several callbacks assume a guild exists while the slash blacklist check allows DMs.
- Timeout and purge have upper bounds but no positive lower bounds. Purge reports the requested count instead of actual deletions.
- Warning numbering and escalation use read-then-insert logic and can race. Warning displays lack pagination.
- log_moderation_case is not called by moderation commands, leaving moderation history incomplete.
- Error handling relies on prints and swallowed exceptions. The constructed file handler is not connected to application logging. Health always claims online status.
- NASA APOD is a placeholder. The unapplied modernization patch expects another baseline and needs selective review.

These findings are from source inspection; runtime reproduction and regression tests remain necessary.

## Recommended migration and structure

Keep Python and discord.py. Migrate to Supabase in stages, with repositories separating database operations from command code. Prefer small files grouped by feature over one file per trivial function.

```text
main.py                    # process entry point
bot.py                     # startup, dependency injection, shutdown
core/                      # settings, logging, checks, error responses
commands/admin/            # channels, filters, AutoMod
commands/moderation/       # kick, ban, timeout, purge, warnings, blacklist, invites, broadcast
commands/utility/          # help, ping, info, fun, NASA
services/                  # shared behavior used by prefix and slash commands
repositories/              # all Supabase queries
events/                    # messages, members, guilds
tasks/                     # scheduled invite worker
supabase/migrations/       # versioned SQL schema and transactional functions
scripts/                   # Mongo export, import, validation
tests/                     # behavior and migration regression checks
```

Use an asynchronous Supabase client. Proposed tables: guild_settings, guild_filter_settings, filter_words, warnings, moderation_cases, scheduled_invites, guild_blacklist_entries. Store AutoMod rule IDs with guild settings. Use stable warning IDs, appropriate uniqueness constraints, transactional escalation, and atomic invite-job claiming with bounded batches, retries, and leases. Discord delivery cannot be made exactly-once across a process crash simply by adding a database transaction.

The user explicitly requires preserving existing MongoDB data. Migrate all seven existing collections, retaining source document IDs for idempotent imports, timestamps, evidence, historical warning data, and pending invite status. Validate counts per guild and representative records. Rehearse restore, pause writes during final export/import, and retain MongoDB for rollback until validation passes. No live database has been inspected or changed.

Keep credentials on the bot backend. Define Supabase table policies and grants deliberately. Preserve Discord snowflake precision across JSON boundaries.

Configure console and rotating file logging once, with module loggers, tracebacks, command/event context, and correlation IDs. Install error handlers for prefix commands, slash commands, events, and background tasks. Redact credentials and return concise error IDs to users. Logging must continue when Supabase is unavailable. Distinguish application error logs from moderation audit records.

## Sequence

1. Preserve unique Revamped files and remove the unused folder.
2. Add logging and regression checks, then stabilize authorization and lifecycle.
3. Extract commands, services, and repositories without unintended behavior changes.
4. Add SQL migrations and Supabase repositories; verify against an isolated database.
5. Rehearse import and validation, then perform a write-paused cutover with rollback available.
6. Recover selected features from the modernization patch after the baseline is verified.

This document is a recommendation, not a completed migration or an approved implementation design.

References:
- https://supabase.com/docs/reference/python/realtime-api
- https://docs.discord.com/developers/resources/auto-moderation
