import asyncio
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from bot import BreadBot
from core.settings import Settings
from tasks.scheduled_invites import InviteWorker
from discord import app_commands


class BotTests(unittest.IsolatedAsyncioTestCase):
    async def test_setup_syncs_development_guild_and_closes_owned_resources(self):
        repos=SimpleNamespace(configs=SimpleNamespace(),filters=SimpleNamespace(),close=AsyncMock())
        factory=AsyncMock(return_value=repos)
        bot=BreadBot(Settings('test','https://test.supabase.co','test',guild_id=123),repos_factory=factory)
        bot.tree.sync=AsyncMock(return_value=[])
        async with bot:
            await bot.setup_hook()
            self.assertEqual(len(bot.tree.get_commands(guild=bot.tree.sync.call_args.kwargs['guild'])),23)
            session=bot.session
        self.assertTrue(session.closed)
        self.assertEqual(repos.close.await_count,1)

    async def test_slash_authorization_database_failure_is_handled(self):
        bot=BreadBot(Settings('test','https://test.supabase.co','test'))
        bot.repos=SimpleNamespace(blacklists=SimpleNamespace(contains=AsyncMock(side_effect=RuntimeError('private details'))),close=AsyncMock())
        interaction=SimpleNamespace(guild_id=123,user=SimpleNamespace(id=456),command=SimpleNamespace(name='ping'),
            response=SimpleNamespace(is_done=lambda:False,defer=AsyncMock()))
        async with bot:
            with self.assertLogs('core.errors',level='ERROR'):
                with self.assertRaises(app_commands.CheckFailure) as caught:
                    await bot.tree.interaction_check(interaction)
        self.assertNotIn('private details',str(caught.exception))
        self.assertTrue(interaction.response.defer.call_args.kwargs['ephemeral'])

    async def test_command_inventory_preserved(self):
        bot=BreadBot(Settings('test','https://test.supabase.co','test'))
        async with bot:
            await bot.load_commands()
            expected=json.loads((Path(__file__).parent/'command_inventory.json').read_text())
            self.assertEqual(sorted(c.name for c in bot.tree.get_commands()),expected['slash'])
            self.assertEqual(sorted(c.name for c in bot.commands),expected['prefix'])

    async def test_ready_events_do_not_duplicate_worker(self):
        bot=BreadBot(Settings('test','https://test.supabase.co','test'))
        bot.repos=SimpleNamespace(close=AsyncMock())
        bot.invite_worker=SimpleNamespace(run=AsyncMock(side_effect=lambda:None))
        async with bot:
            await bot.on_ready()
            first=bot.invite_task
            await bot.on_ready()
            self.assertIs(bot.invite_task,first)
        self.assertTrue(first.done())

    async def test_cached_user_fallback_and_saved_invite_reuse(self):
        repo=SimpleNamespace(claim=AsyncMock(return_value=[{'id':'job','guild_id':'1','user_id':'2','reason':'test','invite_url':'https://discord.gg/test','lease_token':'lease'}]),
            complete=AsyncMock(),record_invite=AsyncMock(),fail=AsyncMock())
        user=SimpleNamespace(send=AsyncMock())
        bot=SimpleNamespace(repos=SimpleNamespace(invites=repo),get_guild=lambda _:SimpleNamespace(name='Test'),
                            get_user=lambda _:None,fetch_user=AsyncMock(return_value=user))
        await InviteWorker(bot).run_once()
        self.assertEqual(user.send.await_count,1)
        self.assertEqual(repo.complete.await_count,1)
        self.assertEqual(repo.record_invite.await_count,1)
