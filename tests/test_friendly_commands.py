import unittest
from types import SimpleNamespace as NS
from datetime import datetime,timezone
from unittest.mock import AsyncMock
from discord.ext import commands
from bot import BreadBot
from core.settings import Settings
from core.presentation import argument_embed,user_info_embed,warning_embed
from core.warning_controls import WarningControls,DeleteConfirmation
from core.errors import UserError


class FriendlyTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_warn_inputs_name_argument_and_usage(self):
        bot=BreadBot(Settings('test','https://test.supabase.co','test'))
        async with bot:
            await bot.load_commands()
            command=bot.get_command('warn')
            for name in ('member','reason'):
                ctx=NS(command=command,clean_prefix='bread ')
                embed=argument_embed(ctx,commands.MissingRequiredArgument(command.clean_params[name]))
                self.assertIn(name,embed.description)
                self.assertIn('bread warn',str(embed.to_dict()))
                self.assertIn('<member>',str(embed.to_dict()))
                self.assertIn('<reason>',str(embed.to_dict()))

    def test_userinfo_avatar_vertical_and_limits(self):
        user=NS(id=123,name='member',display_name='Member',mention='<@123>',bot=False,
                created_at=datetime(2026,1,1,tzinfo=timezone.utc),display_avatar=NS(url='https://example.com/avatar.png'))
        member=NS(joined_at=user.created_at,roles=[NS(name='everyone')]+[NS(name='a'*100) for _ in range(80)])
        embed=user_info_embed(user,member)
        self.assertEqual(embed.thumbnail.url,user.display_avatar.url)
        self.assertTrue(all(not f.inline and len(f.value)<=1024 for f in embed.fields))

    async def test_warning_controls_recheck_permissions_and_scope(self):
        bot=NS(repos=NS(blacklists=NS(contains=AsyncMock(return_value=False)),
                       warnings=NS(delete=AsyncMock(return_value={'id':'id'}))))
        view=WarningControls(bot,10,[{'id':'id','warning_number':1}],2)
        interaction=NS(guild_id=999,user=NS(id=2))
        with self.assertRaises(UserError):await view.check(interaction)
        self.assertEqual(bot.repos.warnings.delete.await_count,0)

    async def test_delete_confirmation_rechecks_permission_and_is_one_use(self):
        row={'id':'id','warning_number':1,'user_id':'3','moderator_id':'2','deleted_by':'2'}
        repository=NS(delete=AsyncMock(return_value=row))
        bot=NS(repos=NS(blacklists=NS(contains=AsyncMock(return_value=False)),warnings=repository))
        parent=WarningControls(bot,10,[row],2)
        view=DeleteConfirmation(parent,'id',2)
        actor=NS(id=2,guild_permissions=NS(moderate_members=False))
        interaction=NS(guild_id=10,guild=NS(owner_id=1),user=actor,
            response=NS(is_done=lambda:True),followup=NS(send=AsyncMock()))
        with self.assertRaises(UserError):await view.confirm.callback(interaction)
        self.assertEqual(repository.delete.await_count,0)
        actor.guild_permissions.moderate_members=True
        await view.confirm.callback(interaction)
        with self.assertRaises(UserError):await view.confirm.callback(interaction)
        self.assertEqual(repository.delete.await_count,1)
        self.assertEqual(repository.delete.call_args.args,(10,'id',2))

    async def test_warning_navigation_rechecks_revoked_permissions(self):
        bot=NS(repos=NS(blacklists=NS(contains=AsyncMock(return_value=False))))
        view=WarningControls(bot,10,[{'id':'id','warning_number':1},{'id':'other','warning_number':2}],2)
        interaction=NS(guild_id=10,guild=NS(owner_id=1),user=NS(id=2,guild_permissions=NS(moderate_members=False)),
            response=NS(is_done=lambda:True,edit_message=AsyncMock()),edit_original_response=AsyncMock())
        with self.assertRaises(UserError):await view.next.callback(interaction)
        self.assertEqual(interaction.edit_original_response.await_count,0)

    def test_warning_embed_mentions_and_case_id(self):
        row={'id':'case-id','warning_number':1,'reason':'reason','evidence':'proof','user_id':'123','moderator_id':'456'}
        embed=warning_embed(row)
        text=str(embed.to_dict())
        for value in ('<@123>','<@456>','case-id','proof'):self.assertIn(value,text)
