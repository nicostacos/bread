# Friendly command and warning updates

- /help and bread help share a categorized embed generated from registered commands.
- /userinfo shows avatar, username/ID, account creation, server join, roles, and account type in vertical sections with symbols.
- Missing/invalid prefix inputs produce a usage embed identifying the parameter, required/optional arguments, and examples where applicable. bread warn with no member or no reason reaches this path before any action is performed.
- bread warn with valid arguments shows a draft embed and the existing evidence form button. Submission uses /warn's implementation and returns a saved-warning embed.
- /warn, /warnings, and bread warnings expose individual case IDs and delete controls. History shows one bounded case per page. Deletion requires confirmation and fresh server/moderator/blacklist checks; navigation also rechecks authorization.
- Deleted warnings are hidden from active history; deleted_at/deleted_by plus a warning_deleted moderation case preserve the audit trail. Warning numbers are never reused. Deleted warnings do not count toward active escalation; prior kick/ban thresholds are not replayed after deletion.
- Warning log text uses <@member_id> and <@moderator_id> references, making them recognizable Discord mentions. Embeds and AllowedMentions.none do not generate unsolicited notification pings.
- The bot was stopped at the user's request and is not automatically restarted.
- /botinfo now posts a public status-report embed: Gateway status, latency, first-ready uptime, server/member totals, loaded slash/prefix counts (including prefix subcommands), and actual guild-level kick/ban/manage-message permissions. Loaded commands are not labeled as universally tested/working. Authorization errors remain private, with bounded checks before the public acknowledgement. Server member totals count memberships across servers, not unique people. Bot remains stopped until the user requests startup.

Verification: 60 local tests passed; isolated SQL checks cover cross-server deletion rejection, idempotency, audit attribution, active-history filtering, revoked RPC access and existing concurrency behavior. Live deployment of migration 20261105234002_warning_deletion_audit completed. No actual warning was deleted to test it. Visual and button acceptance in Discord still needs a subsequent controlled start.

Independent review: navigation reauthorization gap reproduced by a failing test and fixed; complete suite passes afterward. Upstream discord.py emits Python deprecation warnings without test failures.
