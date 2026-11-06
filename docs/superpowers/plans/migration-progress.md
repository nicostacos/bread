# Execution ledger: 2026-11-04-supabase-migration.md

User approved design, then requested continuation after hosting research; native execution with final independent review selected from that instruction. The bot is offline on Render. No deployment is authorized yet.

Working in the requested canonical Bread_bot directory on existing bread-modernization feature branch. Pre-existing edits and original source preserved in ignored backups/source-before-supabase.zip; no unrelated changes will be staged or discarded.

Dependencies: normalization defines rows consumed by schema/import validation; SQL RPC interfaces consumed by repositories; repositories and checks consumed by feature commands; bot owns resources used by commands and worker. Implement and verify in that order.

Task 1: complete. Six initial normalization tests RED to GREEN; actual snapshot exposed missing historical warning numbers. Added regression; derive stable display numbers and retain legacy values and raw records.

Task 2: complete. Schema applied with CLI migration history after rollback rehearsal passed. RLS/RPC privilege checks, escalation, filter mutation, job claim exclusivity and guild history retention passed. Isolated-schema cross-session concurrency checks also passed for warning sequence/escalation, filter lost-update protection, disjoint job claims, stale lease rejection and retry exhaustion; temporary schemas removed.

Tasks 3-4: implemented. Async repository pagination/error propagation and shared authorization, response selection, settings validation and traceback redaction tests pass. Runtime credential retrieval was rejected by auto-review because the CLI would reveal all keys; user was asked to configure one runtime key privately. No keys were fetched or saved.

Tasks 5-6: implemented. 23 slash and 10 prefix root command names match the original fixture, with split feature modules; old implementations removed after snapshot and parity test. Lifecycle and worker tests pass. Additional integration and fresh review remain.

Task 7: completed data import into stzbjhimxmzpvmrbnlxg using final snapshot backups/mongo-final-20261105T030823Z. 8 source documents preserved; normalized values and raw records verified, repeated import and validation passed. Source MongoDB unchanged.

Ruling: historical warning display numbers are deterministic chronological per-member ordinals, with original numbers kept separately — source has missing numbers and the old reader already enumerated them — risk is changed display order for exact timestamp ties; stable source IDs break ties and preserve record identity.

Task 8: implementation/review/offline verification complete; live runtime connection remains pending private runtime key configuration. No bot process has connected to Discord; no hosting deployment occurred.

Final review completed: no Critical findings; three Important findings reproduced and fixed. Slash authorization DB exceptions now become handled errors (test_slash_authorization_database_failure_is_handled RED to GREEN); AutoMod serializes per guild and re-reads saved settings (test_automod_serializes_creation_and_rereads_saved_state RED to GREEN); purge enforces effective channel permissions (test_purge_honors_channel_denial RED to GREEN). Full suite passed after the fix pass. SQL tests and migration content checks remain separate from mocked unit tests.

Ruling: initial slash acknowledgements are private for every command so authorization failures cannot publicly disclose blacklist status — public acknowledgements previously forced even error followups to inherit public visibility — first utility replies now also default to private, while command names and actions remain unchanged.

Additional lifecycle verification: installed real async Supabase client initializes against a mock HTTP boundary and closes its owned transport; setup copies all 23 commands to a development guild and closes its owned session. Existing dependency emits an upstream asyncio.iscoroutinefunction deprecation warning on Python 3.14; no application test fails.

No Git commit was created: current checkout includes pre-existing user edits and its .git directory is read-only in the supplied filesystem profile. Source and migration artifacts remain reviewable in the working tree. No push or deployment was attempted.

Final evidence: 33/33 unittest tests passed; pip check passed; compileall passed; git diff --check passed after README LF normalization. Isolated real SQL concurrency checks passed and removed only their test schemas. Final Supabase normalized-field/raw-document validation passed after review fixes. Final read-only Mongo inventory reported no unknown collections and the same 8 source documents. Runtime client lifecycle was exercised with the installed real library and a mock HTTP boundary; an actual Supabase runtime-key connection has not been tested because those settings remain absent. Startup/deployment is deliberately not claimed.

Runtime access follow-up: the user configured Supabase credentials privately. Removed only the optional BOT_OWNER_ID=your_user_id_here template value, leaving it blank. An actual read-only query through the installed async runtime client succeeded and the client closed cleanly. HEALTH_PORT is unset, as intended for worker-only hosting. Discord was not started and no invite or moderation actions ran. Remaining handoff: choose/provision the host and perform safe Discord startup checks when ready to run jobs.
