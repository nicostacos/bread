"""Resource ownership and event routing. Importing never logs into Discord."""
import asyncio
import logging
import sys
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from core.checks import authorize
from core.errors import UserError,interaction_error,report_error
from repositories.client import create_repositories
from services.filters import FilterService
from services.automod import AutoModService
from services.moderation import ModerationService
from services.invites import InviteService
from tasks.scheduled_invites import InviteWorker
from config import DEFAULT_FILTER_WORDS,GLOBAL_BLACKLIST

logger=logging.getLogger(__name__)
EXTENSIONS=tuple('commands.'+name for name in (
    'admin.channels','admin.filters','moderation.kick','moderation.ban','moderation.timeout',
    'moderation.purge','moderation.warnings','moderation.blacklist','moderation.invites','moderation.broadcast',
    'utility.ping','utility.fun','utility.info','utility.nasa','utility.help'))


class BreadTree(app_commands.CommandTree):
    async def interaction_check(self,interaction):
        public=getattr(interaction.command,'name',None)=='botinfo'
        if not public and not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        try:
            # Public results must not force blacklist/permission failures to be public.
            # Bound pre-acknowledgement authorization below Discord's response deadline.
            if public:
                async with asyncio.timeout(2):
                    await authorize(interaction.guild_id,interaction.user.id,self.client.repos,GLOBAL_BLACKLIST)
            else:await authorize(interaction.guild_id,interaction.user.id,self.client.repos,GLOBAL_BLACKLIST)
        except UserError:raise
        except Exception as error:
            reference=report_error(error,{'event':'slash_authorization','guild':interaction.guild_id})
            raise UserError('Authorization is temporarily unavailable. Error ID: '+reference) from None
        if public and not interaction.response.is_done():await interaction.response.defer(ephemeral=False)
        return True

    async def on_error(self,interaction,error):await interaction_error(interaction,error)


class BreadBot(commands.Bot):
    def __init__(self,settings,repos_factory=create_repositories):
        intents=discord.Intents.default();intents.message_content=True;intents.members=True
        super().__init__(command_prefix=commands.when_mentioned_or('bread '),case_insensitive=True,
            intents=intents,help_command=None,tree_cls=BreadTree,owner_id=settings.owner_id,
            allowed_mentions=discord.AllowedMentions.none())
        self.settings=settings;self.repos_factory=repos_factory
        self.repos=None;self.session=None;self.invite_task=None;self.database_ready=False;self.online_since=None
        self.add_check(self.prefix_check,call_once=True)

    async def prefix_check(self,ctx):
        await authorize(ctx.guild.id if ctx.guild else None,ctx.author.id,self.repos,GLOBAL_BLACKLIST)
        return True

    async def load_commands(self):
        for extension in EXTENSIONS:
            if extension not in self.extensions:await self.load_extension(extension)

    async def setup_hook(self):
        self.session=aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20))
        self.repos=await self.repos_factory(self.settings,DEFAULT_FILTER_WORDS)
        self.database_ready=True
        self.filters=FilterService(self.repos.filters);self.automod=AutoModService(self.repos.configs,self.repos.filters)
        self.moderation=ModerationService(self.repos,self.send_mod_log);self.invites=InviteService()
        self.invite_worker=InviteWorker(self)
        await self.load_commands()
        if self.settings.guild_id:
            guild=discord.Object(id=self.settings.guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:await self.tree.sync()
        logger.info('Registered %s application commands',len(self.tree.get_commands()))

    async def on_ready(self):
        if self.online_since is None:self.online_since=discord.utils.utcnow()
        if self.invite_task is None:self.invite_task=asyncio.create_task(self.invite_worker.run(),name='scheduled-invites')
        logger.info('Bot ready; reconnects reuse the existing worker')

    async def close(self):
        self.database_ready=False
        if self.invite_task is not None:
            self.invite_task.cancel();await asyncio.gather(self.invite_task,return_exceptions=True)
        try:
            if self.session is not None:await self.session.close()
        finally:
            try:
                if self.repos is not None:await self.repos.close()
            finally:await super().close()

    async def send_mod_log(self,guild,title,description):
        config=await self.repos.configs.get(guild.id)
        if config.get('log_channel'):
            channel=guild.get_channel(int(config['log_channel']))
            if channel:await channel.send(embed=discord.Embed(title=title[:256],description=description[:4096],color=0x5865F2,timestamp=discord.utils.utcnow()))

    async def on_message(self,message):
        from events.messages import handle_message
        await handle_message(self,message)
    async def on_member_join(self,member):
        from events.members import handle_member_join
        await handle_member_join(self,member)
    async def on_guild_remove(self,guild):
        from events.guilds import handle_guild_remove
        await handle_guild_remove(self,guild)
    async def on_guild_join(self,guild):
        from events.guilds import handle_guild_join
        await handle_guild_join(self,guild)

    async def on_error(self,event_method,*args,**kwargs):
        error=sys.exc_info()[1]
        if error:report_error(error,{'event':event_method})

    async def on_command_error(self,ctx,error):
        error=getattr(error,'original',error)
        if isinstance(error,UserError):message=str(error)
        elif isinstance(error,commands.CommandNotFound):message='Command not found. Use bread help.'
        elif isinstance(error,commands.UserInputError):
            from core.presentation import argument_embed
            try:await ctx.send(embed=argument_embed(ctx,error))
            except Exception as failure:report_error(failure,{'event':'argument_error_response'})
            return
        elif isinstance(error,commands.CheckFailure):message='You do not have permission to use this command.'
        else:message='Command failed. Error ID: '+report_error(error,{'command':str(ctx.command),'guild':getattr(ctx.guild,'id',None)})
        try:await ctx.send(message)
        except Exception as failure:report_error(failure,{'event':'prefix_error_response'})
