import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from commands.admin.channels import Channels
from commands.admin.filters import Filters
from commands.moderation.purge import Purge
from core.errors import UserError


class CommandTests(unittest.IsolatedAsyncioTestCase):
    def interaction(self):
        actor=SimpleNamespace(id=1,guild_permissions=SimpleNamespace(administrator=True,manage_messages=True))
        me=SimpleNamespace(guild_permissions=SimpleNamespace(manage_messages=True))
        guild=SimpleNamespace(id=10,owner_id=1,me=me)
        response=SimpleNamespace(is_done=lambda:False,defer=AsyncMock(),send_message=AsyncMock())
        return SimpleNamespace(guild=guild,user=actor,response=response,followup=SimpleNamespace(send=AsyncMock()),
                               channel=SimpleNamespace(purge=AsyncMock(return_value=['a','b']),
                                   permissions_for=lambda _:SimpleNamespace(manage_messages=True,read_message_history=True,view_channel=True)),channel_id=20)

    async def test_purge_reports_actual_deletions(self):
        bot=SimpleNamespace(send_mod_log=AsyncMock())
        interaction=self.interaction()
        await Purge.purge.callback(Purge(bot),interaction,100)
        self.assertEqual(interaction.response.send_message.call_args.kwargs['content'],'Purged 2 messages.')

    async def test_purge_honors_channel_denial(self):
        interaction=self.interaction()
        interaction.user.id=2
        interaction.channel.permissions_for=lambda member:SimpleNamespace(manage_messages=False,read_message_history=True,view_channel=True)
        with self.assertRaises(UserError):await Purge.purge.callback(Purge(SimpleNamespace(send_mod_log=AsyncMock())),interaction,100)
        self.assertEqual(interaction.channel.purge.await_count,0)

    async def test_welcome_database_failure_does_not_report_success(self):
        bot=SimpleNamespace(repos=SimpleNamespace(configs=SimpleNamespace(update=AsyncMock(side_effect=RuntimeError('offline')))))
        interaction=self.interaction()
        channel=SimpleNamespace(id=20,guild=interaction.guild,mention='#welcome')
        with self.assertRaises(RuntimeError):await Channels.setwelcome.callback(Channels(bot),interaction,channel)
        self.assertEqual(interaction.response.send_message.await_count,0)

    async def test_filter_database_failure_does_not_sync_automod(self):
        bot=SimpleNamespace(filters=SimpleNamespace(mutate=AsyncMock(side_effect=RuntimeError('offline'))),
                            automod=SimpleNamespace(sync=AsyncMock()))
        interaction=self.interaction()
        with self.assertRaises(RuntimeError):await Filters(bot).operation(interaction.guild,interaction.user,'add','alpha')
        self.assertEqual(bot.automod.sync.await_count,0)
