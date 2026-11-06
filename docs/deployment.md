# Deployment preparation

No new host has been provisioned or deployed. Heroku Basic under redeemed GitHub Student credits is recommended; the user has not yet selected a destination account/app. See hosting-options.md for checked terms and alternatives.

## Heroku worker

- Python 3.14, requirements.txt, Procfile: worker: python main.py.
- One Basic worker dyno, zero web dynos; disable the old Render service. Multiple bot replicas would duplicate Gateway handlers and are not supported by this deployment.
- Set DISCORD_TOKEN, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY in platform configuration; set NASA_API_KEY if available. Do not add Heroku Postgres or Redis: persistence is Supabase.
- Set LOG_PATH to an empty string for console-only platform logging. Local rotating files are optional and ephemeral; never rely on them as an audit archive.
- Leave HEALTH_PORT unset for a worker-only deployment. If a host requires a listener, configure HEALTH_PORT explicitly; /health returns 503 until Discord and the database are ready.
- Enable Message Content and Server Members intents in the Discord developer portal. Grant only required bot permissions for the installed commands; AutoMod management needs Manage Server.
- Leave DISCORD_GUILD_ID empty for global commands. A development guild ID copies/syncs commands to that guild correctly.
- Slash acknowledgements and first replies default to private so permission/blacklist failures do not become public. Prefix replies remain normal channel messages.
- Allow graceful SIGTERM shutdown. The bot cancels workers and closes its HTTP/database clients before exit.

Student credit does not impose a hard account spending cap. Basic is priced per dyno; additional dynos, one-off processes, and add-ons can cost more. Redeem and confirm the student allowance before provisioning anything.

## Preflight

```powershell
python -m unittest discover -s tests -v
python -m pip check
python main.py
```

Only run the last command when ready for the bot to connect to Discord and resume scheduled jobs. Import and offline registration tests do not log into Discord. Check command registration and a harmless /ping first, then test permissions in a dedicated test server.
