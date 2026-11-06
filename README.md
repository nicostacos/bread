# Bread Bot

A modular discord.py bot backed by Supabase: moderation, word filters and AutoMod, warning history, welcome/log channels, scheduled rejoin invitations, utilities, and NASA APOD.

## Setup

1. Use Python 3.14 and install `python -m pip install -r requirements.txt`.
2. Copy `.env.example` to `.env` and configure Discord and Supabase credentials privately.
3. Enable Discord Message Content and Server Members intents.
4. Run `python main.py` only when ready to connect to Discord and resume pending jobs.

Prefix: `bread ` or a bot mention. Use `/help` or `bread help`. Existing slash and prefix root command names are preserved. Database failures produce errors rather than pretending writes succeeded.

## Structure

- `commands/`: admin, moderation, utility commands grouped by feature.
- `services/`: shared moderation, filters, AutoMod, invitations, NASA behavior.
- `repositories/`: asynchronous Supabase operations; no Mongo runtime access.
- `core/`: validated settings, authorization, logs, responses, pagination.
- `events/` and `tasks/`: event routing and one managed invite worker.
- `supabase/migrations/`: versioned SQL schema, restricted access, atomic warning/filter/job functions.
- `scripts/`: private Mongo snapshot/import/validation tooling.

Run `python -m unittest discover -s tests -v`. Tests load all commands without Discord login or destructive moderation actions.

Migration history and rollback: [docs/migration-runbook.md](docs/migration-runbook.md).
Deployment: [docs/deployment.md](docs/deployment.md).
Hosting comparison: [docs/hosting-options.md](docs/hosting-options.md).

Never commit `.env`, backups, logs, or recovered private configuration. The old source is preserved in the ignored pre-migration snapshot. Supabase service credentials must stay on the backend.
