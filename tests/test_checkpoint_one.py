"""Command callbacks run locally; Discord and persistence boundaries are fakes."""
import unittest
from datetime import datetime,timezone
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
import discord
from bot import BreadBot
from core.settings import Settings
from core.errors import UserError
from services.moderation import ModerationService
from services.filters import FilterService
from services.invites import InviteService


class Session:
    def get(self,*args,**kwargs):return self
    async def __aenter__(self):return self
    async def __aexit__(self,*args):pass
    status=200
    async def json(self):return {'title':'Space','explanation':'Example','media_type':'image','url':'https://example.com/image.jpg'}


class CheckpointOneTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        perms=NS(administrator=True,kick_members=True,ban_members=True,moderate_members=True,
                 manage_messages=True,send_messages=True,create_instant_invite=True,
                 read_message_history=True,view_channel=True)
        self.actor=NS(id=2,name='moderator',mention='<@2>',top_role=10,guild_permissions=perms,
                      created_at=datetime(2026,1,1,tzinfo=timezone.utc))
        self.target=NS(id=3,name='member',mention='<@3>',top_role=1,guild_permissions=NS(administrator=False),
                       created_at=datetime(2026,1,1,tzinfo=timezone.utc),roles=[],kick=AsyncMock(),timeout=AsyncMock())
        self.channel=NS(id=20,mention='<#20>',permissions_for=lambda _:perms,
                        purge=AsyncMock(return_value=[1,2]),send=AsyncMock(),
                        create_invite=AsyncMock(return_value=NS(url='https://discord.gg/example')))
        self.guild=NS(id=10,name='Test server',owner_id=1,owner=NS(name='owner'),
            me=NS(id=9,top_role=9,guild_permissions=perms),icon=None,member_count=4,roles=[],categories=[],
            text_channels=[self.channel],voice_channels=[],created_at=datetime(2026,1,1,tzinfo=timezone.utc),
            get_member=lambda uid:self.target if uid==3 else None,ban=AsyncMock(),unban=AsyncMock())
        self.channel.guild=self.guild
        self.repos=NS(configs=NS(get=AsyncMock(return_value={}),update=AsyncMock()),
            warnings=NS(add=AsyncMock(return_value={'id':'warning','warning_number':1,'escalation':None}),list=AsyncMock(return_value=[])),
            cases=NS(record=AsyncMock()),blacklists=NS(contains=AsyncMock(return_value=False),list=AsyncMock(return_value=[]),add=AsyncMock(),remove=AsyncMock()),
            filters=NS(mutate=AsyncMock(return_value={'enabled':True,'words':[]}),get=AsyncMock(return_value={'enabled':True,'words':[]})),close=AsyncMock())
        self.bot=BreadBot(Settings('test','https://test.supabase.co','test'))
        await self.bot.__aenter__()
        self.bot.repos=self.repos;self.bot.filters=FilterService(self.repos.filters)
        self.bot.automod=NS(sync=AsyncMock());self.bot.send_mod_log=AsyncMock()
        self.bot.moderation=ModerationService(self.repos,self.bot.send_mod_log)
        self.bot.invites=InviteService();self.bot.session=None
        await self.bot.load_commands()
        # Discord supplies these values after login; set the cache without a Gateway connection.
        self.bot._connection.user=NS(id=9,name='Bread',created_at=datetime(2026,1,1,tzinfo=timezone.utc))

    async def asyncTearDown(self):await self.bot.__aexit__(None,None,None)

    def interaction(self,name):
        sent=[];state={'done':False}
        async def send(**kwargs):sent.append(kwargs)
        async def defer(**kwargs):state['done']=True
        return NS(command=self.bot.tree.get_command(name),guild=self.guild,guild_id=10,user=self.actor,
            channel=self.channel,channel_id=20,response=NS(is_done=lambda:state['done'],defer=defer,send_message=send),
            followup=NS(send=send),sent=sent)

    async def call(self,name,**kwargs):
        interaction=self.interaction(name)
        command=interaction.command
        await command.callback(command.binding,interaction,**kwargs)
        return interaction

    async def test_every_original_slash_callback_completes(self):
        external=NS(id=55,send=AsyncMock())
        args={'kick':{'member':self.target},'ban':{'member':self.target},'mute':{'member':self.target},
            'unban':{'user':external},'unkick':{'user':external,'reason':'Test'},
            'warn':{'member':self.target,'reason':'Test','evidence':'proof'},'warnings':{'member':self.target},
            'blacklist':{'action':'list'},'broadcast':{'message':'Test','ping_everyone':False},
            'filter':{'action':'status'},'setlog':{'channel':self.channel},'setwelcome':{'channel':self.channel}}
        for name in sorted(command.name for command in self.bot.tree.get_commands()):
            with self.subTest(command=name):
                if name=='apod':self.bot.session=Session()
                try:
                    result=await self.call(name,**args.get(name,{}))
                    self.assertTrue(result.sent,'Command did not produce a response')
                    self.assertTrue(result.sent[-1].get('content') or result.sent[-1].get('embed'))
                    if name=='botinfo':self.assertFalse(result.sent[-1]['ephemeral'])
                finally:self.bot.session=None

    async def test_sensitive_callbacks_reject_unprivileged_actor(self):
        self.actor.guild_permissions=NS()
        args={'kick':{'member':self.target},'ban':{'member':self.target},'mute':{'member':self.target},
            'purge':{},'warn':{'member':self.target,'reason':'Test'},'warnings':{'member':self.target},
            'unban':{'user':NS(id=55)},'unkick':{'user':NS(id=55),'reason':'Test'},
            'blacklist':{'action':'list'},'broadcast':{'message':'Test'},'filter':{'action':'status'},
            'setlog':{'channel':self.channel},'setwelcome':{'channel':self.channel},'get_channels':{}}
        for name,kwargs in args.items():
            with self.subTest(command=name):
                with self.assertRaises(UserError):await self.call(name,**kwargs)
        self.assertEqual(self.target.kick.await_count,0)
        self.assertEqual(self.guild.ban.await_count,0)
        self.assertEqual(self.repos.warnings.add.await_count,0)

    async def test_warn_failure_never_escalates_or_reports_success(self):
        self.repos.warnings.add.side_effect=RuntimeError('database offline')
        with self.assertRaises(RuntimeError):await self.call('warn',member=self.target,reason='Test')
        self.assertEqual(self.target.kick.await_count,0)
        self.assertEqual(self.guild.ban.await_count,0)

    async def test_protected_targets_never_reach_moderation(self):
        for uid,role in [(1,1),(2,1),(9,1),(3,10)]:
            self.target.id=uid;self.target.top_role=role
            for command in ('kick','ban','mute'):
                with self.subTest(command=command,target=uid,role=role):
                    with self.assertRaises(UserError):await self.call(command,member=self.target)
        self.assertEqual(self.target.kick.await_count,0)
        self.assertEqual(self.guild.ban.await_count,0)

    async def test_purge_and_mute_reject_invalid_bounds(self):
        for value in (-1,0,40321):
            with self.assertRaises(UserError):await self.call('mute',member=self.target,duration=value)
        for value in (-1,0,2001):
            with self.assertRaises(UserError):await self.call('purge',limit=value)

    async def test_broadcast_explicitly_disables_mentions(self):
        await self.call('broadcast',message='@everyone <@3> <@&4>')
        mentions=self.channel.send.call_args.kwargs['allowed_mentions']
        self.assertFalse(mentions.everyone);self.assertFalse(mentions.roles);self.assertFalse(mentions.users)

    async def test_broadcast_reports_partial_delivery(self):
        self.channel.send.side_effect=discord.HTTPException(NS(status=403,reason='Forbidden'),'Denied')
        with self.assertLogs('core.errors',level='ERROR'):
            result=await self.call('broadcast',message='Test')
        self.assertIn('0 channels sent, 1 failed',result.sent[-1]['content'])

    async def test_channel_configuration_rejects_foreign_guild(self):
        self.channel.guild=NS(id=999)
        from discord.ext.commands import BadArgument
        with self.assertRaises(BadArgument):await self.call('setwelcome',channel=self.channel)
        self.assertEqual(self.repos.configs.update.await_count,0)

    async def test_filter_outage_returns_prefix_error_without_invoking_command(self):
        from events.messages import handle_message
        message=NS(author=NS(bot=False),guild=self.guild)
        context=NS(valid=True)
        self.bot.filters.settings=AsyncMock(side_effect=RuntimeError('private database details'))
        self.bot.get_context=AsyncMock(return_value=context)
        self.bot.on_command_error=AsyncMock()
        self.bot.process_commands=AsyncMock()
        with self.assertLogs('core.errors',level='ERROR'):
            await handle_message(self.bot,message)
        self.assertEqual(self.bot.process_commands.await_count,0)
        self.assertEqual(self.bot.on_command_error.await_count,1)
        error=self.bot.on_command_error.call_args.args[1]
        self.assertIsInstance(error,UserError)
        self.assertNotIn('private database details',str(error))

    async def test_every_original_prefix_callback_and_subcommand(self):
        sent=[]
        async def send(*args,**kwargs):sent.append((args,kwargs))
        ctx=NS(guild=self.guild,author=self.actor,send=send)
        args={'hello':{},'help':{},'kick':{'member':self.target},'warn':{'member':self.target,'reason':'Test'},
              'warnings':{'member':self.target},'getchannels':{},'setlog':{'channel':self.channel},'setwelcome':{'channel':self.channel},
              'blacklist':{},'blacklist add':{'user':NS(id=55)},'blacklist remove':{'user':NS(id=55)},'blacklist list':{},
              'filter':{},'filter add':{'word':'alpha'},'filter remove':{'word':'alpha'},
              'filter reset':{},'filter status':{},'filter list':{},'filter enable':{},'filter disable':{}}
        for name,kwargs in args.items():
            with self.subTest(command=name):
                sent.clear();command=self.bot.get_command(name)
                await command.callback(command.cog,ctx,**kwargs)
                self.assertTrue(sent)
                if name in ('kick','warn'):
                    from core.evidence import EvidenceView
                    self.assertIsInstance(sent[-1][1]['view'],EvidenceView)
        self.assertEqual(self.target.kick.await_count,0)
        self.assertEqual(self.repos.warnings.add.await_count,0)

    async def test_evidence_submission_rechecks_revoked_permissions(self):
        from core.evidence import EvidenceView
        view=EvidenceView(self.bot,'kick',2,10,3,'Test')
        self.guild.fetch_member=AsyncMock(return_value=self.target)
        self.actor.guild_permissions=NS()
        with self.assertRaises(UserError):await view.submit(self.interaction('kick'),'Test','Evidence')
        self.assertEqual(self.target.kick.await_count,0)

    async def test_evidence_submission_uses_real_kick_and_warn_callbacks(self):
        from core.evidence import EvidenceView
        self.guild.fetch_member=AsyncMock(return_value=self.target)
        for action in ('kick','warn'):
            with self.subTest(action=action):
                view=EvidenceView(self.bot,action,2,10,3,'Original reason')
                result=self.interaction(action)
                await view.submit(result,'Edited reason','Evidence link')
                self.assertTrue(result.sent)
        self.assertEqual(self.target.kick.await_count,1)
        self.assertEqual(self.repos.warnings.add.await_count,1)
        self.assertEqual(self.repos.warnings.add.call_args.args[-2:],('Edited reason','Evidence link'))

    async def test_invite_missing_permission_has_no_delivery(self):
        self.guild.text_channels=[]
        user=NS(id=55,send=AsyncMock())
        with self.assertRaises(UserError):await self.call('unkick',user=user,reason='Test')
        self.assertEqual(user.send.await_count,0)

    async def test_discord_action_failure_does_not_record_success(self):
        self.target.kick.side_effect=discord.Forbidden(NS(status=403,reason='Forbidden'),'Denied')
        with self.assertRaises(discord.Forbidden):await self.call('kick',member=self.target)
        self.assertEqual(self.repos.cases.record.await_count,0)
