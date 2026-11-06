import unittest
from datetime import datetime,timezone
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
from commands.utility.info import bot_info_embed
from bot import BreadBot
from core.settings import Settings
from core.errors import UserError


class BotInfoTests(unittest.IsolatedAsyncioTestCase):
    def test_report_counts_uptime_and_real_permissions(self):
        since=datetime(2026,11,5,tzinfo=timezone.utc)
        bot=NS(is_ready=lambda:True,latency=.089,online_since=since,
            guilds=[NS(member_count=12),NS(member_count=19)],
            tree=NS(get_commands=lambda:[1,2]),walk_commands=lambda:iter([1,2,3]),
            user=NS(display_avatar=NS(url='https://example.com/bot.png')))
        guild=NS(name='Test server',me=NS(guild_permissions=NS(kick_members=True,ban_members=False,manage_messages=True)))
        embed=bot_info_embed(bot,guild,NS(display_name='Moderator'))
        text=str(embed.to_dict())
        for item in ('89 ms','31','Test server','Kick Members','Ban Members','❌','✅','<t:'):
            self.assertIn(item,text)
        self.assertIn('Moderator',embed.footer.text)
        self.assertNotIn('All Working',text)
        self.assertEqual(embed.thumbnail.url,'https://example.com/bot.png')

    async def test_botinfo_is_acknowledged_publicly_after_authorization(self):
        bot=BreadBot(Settings('test','https://test.supabase.co','test'))
        bot.repos=NS(blacklists=NS(contains=AsyncMock(return_value=False)),close=AsyncMock())
        interaction=NS(guild_id=123,user=NS(id=456),command=NS(name='botinfo'),
            response=NS(is_done=lambda:False,defer=AsyncMock()))
        async with bot:await bot.tree.interaction_check(interaction)
        self.assertFalse(interaction.response.defer.call_args.kwargs['ephemeral'])

    async def test_blocked_botinfo_never_acknowledged_publicly(self):
        bot=BreadBot(Settings('test','https://test.supabase.co','test'))
        bot.repos=NS(blacklists=NS(contains=AsyncMock(return_value=True)),close=AsyncMock())
        interaction=NS(guild_id=123,user=NS(id=456),command=NS(name='botinfo'),
            response=NS(is_done=lambda:False,defer=AsyncMock()))
        async with bot:
            with self.assertRaises(UserError):await bot.tree.interaction_check(interaction)
        self.assertEqual(interaction.response.defer.await_count,0)
