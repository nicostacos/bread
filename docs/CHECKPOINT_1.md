# Checkpoint 1 — Original command verification

Status: offline verification and evidence-button implementation complete; live command acceptance remains pending a designated test server/accounts. This is not a claim that destructive moderation was exercised against real members.

## Evidence

- Full local suite: 54 tests pass. discord.py emits upstream Python deprecation warnings; no test failures.
- All 23 original slash callbacks execute with fake Discord/persistence boundaries and produce a response. All 10 prefix roots and their filter/blacklist subcommands are exercised with typed arguments. Discord's actual argument conversion and API permissions still require live checks.
- Sensitive command callbacks reject an unprivileged actor without executing actions or saving a warning. Protected targets and invalid timeout/purge limits are rejected.
- Tests cover Discord action failure, persistence failure, foreign-server channel configuration, blocked authorization, channel-specific purge denial, mention controls, partial broadcast, and pagination/embedding bounds.
- Earlier controlled startup registered 23 commands and connected to Discord. It did not establish successful live responses for every command.
- Independent review found no Important issues in the new evidence flow or filter-outage fix. Added a real-callback evidence integration test after the reviewer identified the initial mocked-callback coverage gap.
- No schema changes, production command actions, source imports, or data writes were performed for this checkpoint. The intentionally deleted invitation has not been restored.

## Common behavior

All commands are server-only and pass the shared global/server blacklist check. Authorization persistence failures deny execution. Slash replies are private by default; prefix replies appear in the channel. A component/modal reply is private. Public result visibility can be redesigned explicitly in checkpoint 2.

Permission labels: MM = Manage Messages; MOD = Moderate Members; KICK = Kick Members; BAN = Ban Members; ADMIN = Administrator. Bot permission/hierarchy checks apply where the action requires them. Guild owners are permitted appropriately, but the bot cannot act above its own role.

O below means automated callback/feature behavior verified with fake external boundaries. It does not mean a live Discord action succeeded. Live acceptance is pending for every row unless stated separately.

| Slash | Prefix support | Inputs | Permission | Persistence / audit | Verification |
| --- | --- | --- | --- | --- | --- |
| /ping | — | none | member | authorization read only | O |
| /test | — | none | member | authorization read only | O |
| /hello | bread hello | none | member | authorization read only | O |
| /coin_toss | — | none | member | authorization read only | O |
| /help | bread help | none | member | authorization read only | O; help lists installed commands |
| /botinfo | — | none | member | authorization read only | O |
| /serverinfo | — | none | member | authorization read only | O; icon/owner/count/timestamp cases covered |
| /userinfo | — | optional user | member | authorization read only | O |
| /apod | — | none | member | authorization read; NASA HTTP | O for image/video/errors; live NASA availability tracked below |
| /kick | bread kick | member, reason, optional evidence | KICK | moderation case + configured Discord log | O; prefix opens evidence form |
| /ban | — | member, reason, optional evidence | BAN | moderation case + configured Discord log | O |
| /unban | — | user, reason | BAN | moderation case + configured Discord log | O |
| /unkick | — | user, reason | KICK; bot Create Invite in a channel | immediate invite DM; no scheduled job | O; missing permission produces no DM |
| /mute | — | member, positive duration up to 40320 minutes, reason/evidence | MOD | moderation case + configured Discord log | O; hierarchy/admin target checks |
| /purge | — | positive limit up to 2000 | MM; effective actor/bot channel permissions | configured Discord log; no case row currently | O; actual deleted count and channel denial covered |
| /warn | bread warn | member, required reason, optional evidence | MOD; KICK/BAN additionally required for escalation | warning + case + configured Discord log | O; failed write cannot escalate; prefix evidence form |
| /warnings | bread warnings | member | MOD | warning-history read | O; pagination |
| /blacklist | bread blacklist add/remove/list | action, user when needed | ADMIN | blacklist membership writes for add/remove; no case row | O |
| /broadcast | — | message, optional deliberate everyone ping | ADMIN | outgoing channel sends; per-channel failures logged | O; no live broadcast |
| /setlog | bread setlog | channel | ADMIN | server configuration write | O |
| /setwelcome | bread setwelcome | channel | ADMIN | server configuration write | O; failed save cannot report success |
| /get_channels | bread getchannels | none | ADMIN | server configuration read | O |
| /filter | bread filter add/remove/reset/status/list/enable/disable | action, word when needed | MM; bot Manage Server for AutoMod sync | atomic filter/settings writes; AutoMod ID; sync errors logged | O; partial sync failure distinguished from saved local settings |

## Prefix evidence flow (user-selected)

`bread kick @member reason` and `bread warn @member reason` reply with an **Add evidence & continue** button. They do not immediately perform the action.

1. Only the original moderator can open/use the form in the original server.
2. Form contains an editable reason and optional evidence text/links. It does not upload attachments.
3. Submission is private; the action is performed when the form is submitted, not when the button is pressed.
4. Recheck blacklist and fetch the current target member. The actual slash callback rechecks current actor/bot permissions and role hierarchy.
5. Expire after three minutes. Concurrent submissions execute at most once; ambiguous external failures consume the form rather than replay an action.
6. Existing reasons/evidence persistence and audit behavior come from the shared slash path. Warn retains existing escalation behavior.

Tests cover other-user rejection, expiry, blacklist changes, revoked permissions, fresh target lookup, concurrent submits, failure replay prevention, and both real kick/warn callbacks with fake external boundaries.

## Fix found during verification

If filter persistence failed, prefix commands were silently dropped. They now remain blocked but return a sanitized error ID for recognized commands. No command runs while filtering is unavailable. Regression reproduced before the fix and passes afterward.

## Live acceptance checklist

- [ ] Identify test server and designated moderation test accounts; ensure only one bot process is running.
- [ ] Verify /ping, /help, /hello, /coin_toss, /botinfo, /serverinfo, /userinfo and prefix equivalents.
- [ ] Verify /apod against a valid NASA key and current service availability.
- [ ] Verify an ordinary member cannot invoke administrator/moderator commands; verify DM rejection.
- [ ] Use disposable log/welcome channels for set/get settings, filter changes and welcome behavior; restore intentional settings afterward.
- [ ] Use designated test accounts for kick, ban/unban, timeout, warning/escalation, blacklist and invitation tests.
- [ ] Use a disposable channel for purge and a controlled server/channel set for broadcast.
- [ ] Verify the evidence button opens in desktop/mobile Discord, only its requester can submit, and saved evidence appears in history.
- [ ] Record actual results and error IDs here; fix/retest failures before calling live acceptance complete.

The NASA live read-only request returned HTTP 500 with DEMO_KEY; offline parsing and error behavior pass. Do not report that as a successful live /apod test. No credential values were printed.

Command-audit enhancements (e.g. persistent purge/broadcast/blacklist case records) and full-list pagination belong to later checkpoints; the current behavior is documented here rather than implied to exist.
