# MongoDB to Supabase migration

The bot must stay offline during export/import/validation. Render was already offline per the user; do not enable Render alongside a new host.

## Completed import

Project: stzbjhimxmzpvmrbnlxg. Versioned schema: 202611050001_initial.sql.
Final source snapshot: backups/mongo-final-20261105T030823Z (private, ignored).
Validation report: validation-report.json inside that snapshot.

Source has 8 BSON documents: server_configs 1, word_filters 1, moderation_warnings 4, moderation_cases 1, scheduled_invites 1, guild_blacklists 0, automod_rule_ids 0. An earlier conversational total of 9 was an arithmetic error.

Destination contains guild_settings 1, guild_filter_settings 1, filter_words 11, warnings 4, moderation_cases 1, scheduled_invites 1, guild_blacklist_entries 0. The private bread_private.source_documents table preserves all 8 original documents in canonical Extended JSON, including unknown fields. The existing AutoMod ID was preserved from server_configs.

Two warnings had no stored number. Display numbers were derived deterministically by per-member timestamp order, matching the old bot's read-time numbering behavior. Existing stored numbers remain in legacy_warning_number and the full archive. Imports never execute moderation actions. Repeated import and complete field validation passed.

## Rehearsal and validation commands

Run from Bread_bot using the configured virtual environment. Install requirements-migration.txt for source tooling. No source writes are performed.

```powershell
python -m scripts.mongo_snapshot backups/new-snapshot
python -m scripts.migrate_supabase backups/new-snapshot
# --apply is deliberate: only while the bot is offline and destination import conflicts have been reviewed.
python -m scripts.migrate_supabase backups/new-snapshot --apply
python -m scripts.validate_migration backups/new-snapshot
```

The SQL transport checks the linked project reference, uses the authenticated CLI, embeds serialized data only as base64 JSON literals, and suppresses private SQL results/errors from console output. The importer is transactional and uses stable source-derived IDs. Validation compares normalized fields and exact raw documents, not just counts. Keep snapshots and credentials out of Git and shared logs.

Do not rerun an import after production Supabase writes begin: upserts could overwrite newer records. The offline source snapshot is not a bidirectional synchronization system.

## Runtime handoff

Set DISCORD_TOKEN, SUPABASE_URL, and SUPABASE_SERVICE_ROLE_KEY privately. Optional NASA_API_KEY; DEMO_KEY has limited quota. Runtime never uses Mongo credentials or a dummy database. Do not start the bot merely to test import: the restored invite worker will process eligible pending jobs on startup.

The scheduled invite has been preserved, not sent during migration. Review pending job intent before going live if it is old. Role/membership events, command checks, and external permissions still need real-server smoke checks after deployment; offline tests must not kick/ban/purge/broadcast.

## Rollback

MongoDB remains unchanged. Before any new Supabase writes, rollback can use the original code snapshot in backups/source-before-supabase.zip and the original Mongo configuration. Never run both writers at the same time.

After new Supabase writes, first stop the bot and export/reconcile those writes before reverting to MongoDB. Simply restarting the old copy would lose new warnings/settings/job progress. Keep local/private and database archives until the retention policy is deliberately changed.
