# Bread Bot threat model

Repository: `nicostacos/bread` (discord.py moderation bot backed by Supabase). No infrastructure-as-code exists; per the user there is no infrastructure repository (Heroku is configured in its dashboard, see `docs/deployment.md`). `SECURITY.md` only gives a reporting contact, so it doesn't describe a security model.

## System overview and trust boundaries

- A single Heroku worker dyno runs `python main.py` (`Procfile`). It connects out to the Discord Gateway with `DISCORD_TOKEN`, and to Supabase with `SUPABASE_SERVICE_ROLE_KEY` (`core/settings.py`, `repositories/client.py`).
- Boundary 1, Discord users to bot: any member of any guild the bot is in can send prefix commands (`bread ` / mention), slash commands, modal/button interactions and ordinary messages. Ordinary messages pass through the word filter (`events/messages.py`).
- Boundary 2, guild to guild: one bot process and one Supabase project serve every guild. Isolation between guilds depends entirely on the bot passing the right `guild_id` (`repositories/*.py`, the `bread_*` SQL functions).
- Boundary 3, bot to Supabase: the service-role key bypasses RLS. All tables have RLS enabled and `anon`/`authenticated` revoked, and the functions run as `security invoker` and are granted only to `service_role` (`supabase/migrations/`).
- Boundary 4, bot to outbound services: the NASA APOD API (`services/nasa.py`), and Discord DMs/invites sent by the invite worker (`tasks/scheduled_invites.py`).
- Optional `/health` aiohttp listener on `0.0.0.0:HEALTH_PORT` (`main.py`). It's unset by default for the worker-only deployment.

## Components

| Component | Code |
|---|---|
| Bot runtime | `bot.py`, `main.py`, `core/`, `events/` (startup, authorization `core/checks.py`, error/log handling, message filter routing, health endpoint) |
| Commands | `commands/` (except `commands/moderation/invites.py`), `services/filters.py`, `services/automod.py`, `services/moderation.py`, `services/nasa.py`, `config.py` |
| Invite worker | `tasks/scheduled_invites.py`, `services/invites.py`, `commands/moderation/invites.py`, `repositories/invites.py` |
| Data layer | `repositories/` (other than invites), `supabase/` |
| Migration tooling | `scripts/` (local, owner-run Mongo to Supabase export/import/validation) |
| Legacy code | `recovery/`, `bread_bot_fixes.patch`, `webhook_utils.md` (not deployed) |

## Entry points

- Slash commands. `BreadTree.interaction_check` calls `authorize`, which rejects DMs and blacklisted users. Each command then calls `require_permission`/`validate_target` against the caller's guild permissions.
- Prefix commands. `BreadBot.prefix_check` runs the same `authorize`.
- Evidence modal/buttons (`core/evidence.py`), bound to the requesting moderator and guild.
- Every guild message goes through the word filter regex (`services/filters.py`).
- Guild join/leave and member join events (`events/`).
- `/health` (only when `HEALTH_PORT` is set).

## Assets

**Critical (named by the user):**
- `DISCORD_TOKEN` and `SUPABASE_SERVICE_ROLE_KEY`. Leaking the token gives full control of the bot in every guild. Leaking the key gives full read/write on all guilds' data.
- Per-guild isolation of moderation data: warnings, blacklists, moderation cases, filter words, guild settings, scheduled invites. One guild must not be able to read or alter another guild's data, or moderate through another guild's configuration.

The user also selected "all equally". Other assets (bot availability, not being usable to spam/mass-ping, members' DMs) still matter at their normal severity.

## Attackers (per the user)

- **In scope:** regular members of any guild the bot is in, and hostile servers. A hostile server's own admins/mods can try to use the bot to reach other guilds, the bot's secrets, the shared database, or the host.
- **Trusted:** server admins/mods acting within their own server. Abuse of legitimately held Discord permissions inside one's own guild is not a threat the user cares about. Examples: an admin broadcasting `@everyone` in their own server, a moderator warning/kicking/purging in their own server, an admin blacklisting their own members.
- Anyone on the internet only reaches the bot through Discord, or through `/health` when it is enabled.

## Existing controls

- `authorize` rejects DMs and global/guild-blacklisted users before any command runs (`core/checks.py`).
- `require_permission`/`validate_target` check Discord permissions and role hierarchy, and block targeting the owner, the bot or oneself.
- `allowed_mentions=none` globally. Broadcast allows `@everyone` only when the admin opts in.
- RLS on all tables, plus grants for `service_role` only. SQL functions use `search_path=''` and advisory locks for warning numbering.
- Secret redaction in logs (`core/logging.py`). `.env`, logs and backups are gitignored.
- Ephemeral slash responses by default, and a bounded authorization timeout for public commands.

## Out of scope / accepted risk (per the user)

- `recovery/` and `bread_bot_fixes.patch`: old code, not deployed. Findings there aren't worth fixing.
- Misuse by server admins/mods of permissions they legitimately hold in their own guild.

## Open questions

- Is `HEALTH_PORT` ever set in production? The docs say leave it unset.
- Which Discord permissions does the bot's install link request? (`docs/deployment.md` says only required ones.)
