import discord
from discord import app_commands
from discord.ext import commands
from core.checks import require_permission
from core.errors import defer,UserError, respond, report_error


class Filters(commands.Cog):
    def __init__(self,bot):self.bot=bot

    async def operation(self,guild,actor,action,word=''):
        require_permission(guild,actor,'manage_messages')
        if action not in ('add','remove','reset','status','list','enable','disable'):raise UserError('Unknown filter operation.')
        if action in ('add','remove') and not word.strip():raise UserError('Provide a word.')
        if len(word)>60:raise UserError('Filter words must be at most 60 characters.')
        settings=await self.bot.filters.mutate(guild.id,'status' if action=='list' else action,word.strip().lower() or None)
        message=f"Filter {'enabled' if settings['enabled'] else 'disabled'}; {len(settings['words'])} words saved."
        if action in ('list','status'):
            message+='\n'+(', '.join(settings['words'])[:1700] or 'No filtered words.')
        else:
            try:await self.bot.automod.sync(guild,settings)
            except Exception as error:
                reference=report_error(error,{'event':'automod_sync_after_filter_save','guild':guild.id})
                message+=f' Local filter saved; Discord AutoMod synchronization failed. Error ID: {reference}.'
        return message

    @app_commands.command(name='filter',description='Manage the server chat filter')
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.choices(action=[app_commands.Choice(name=x,value=x) for x in ('add','remove','reset','status','enable','disable')])
    async def filter_slash(self,interaction:discord.Interaction,action:str,word:str=''):
        await defer(interaction,ephemeral=True)
        await respond(interaction,content=await self.operation(interaction.guild,interaction.user,action,word))

    @commands.group(name='filter',invoke_without_command=True)
    async def filter_prefix(self,ctx):await ctx.send(await self.operation(ctx.guild,ctx.author,'status'))

    @filter_prefix.command(name='add')
    async def add(self,ctx,*,word:str):await ctx.send(await self.operation(ctx.guild,ctx.author,'add',word))
    @filter_prefix.command(name='remove')
    async def remove(self,ctx,*,word:str):await ctx.send(await self.operation(ctx.guild,ctx.author,'remove',word))
    @filter_prefix.command(name='reset')
    async def reset(self,ctx):await ctx.send(await self.operation(ctx.guild,ctx.author,'reset'))
    @filter_prefix.command(name='status')
    async def status(self,ctx):await ctx.send(await self.operation(ctx.guild,ctx.author,'status'))
    @filter_prefix.command(name='list')
    async def list_words(self,ctx):await ctx.send(await self.operation(ctx.guild,ctx.author,'list'))
    @filter_prefix.command(name='enable')
    async def enable(self,ctx):await ctx.send(await self.operation(ctx.guild,ctx.author,'enable'))
    @filter_prefix.command(name='disable')
    async def disable(self,ctx):await ctx.send(await self.operation(ctx.guild,ctx.author,'disable'))


async def setup(bot):await bot.add_cog(Filters(bot))
