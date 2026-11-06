import discord
from discord import app_commands
from discord.ext import commands
from core.checks import require_permission
from core.errors import defer,UserError,respond


class Blacklist(commands.Cog):
    def __init__(self,bot):self.bot=bot

    async def operation(self,guild,actor,action,user=None):
        require_permission(guild,actor,'administrator')
        if action=='list':
            rows=await self.bot.repos.blacklists.list(guild.id)
            return ('Blacklisted users:\n'+', '.join(row['user_id'] for row in rows))[:1900] if rows else 'No users are blacklisted.'
        if action not in ('add','remove') or user is None:raise UserError('Choose add/remove and provide a user.')
        if user.id in (guild.owner_id,guild.me.id,actor.id):raise UserError('That user cannot be blacklisted here.')
        await getattr(self.bot.repos.blacklists,action)(guild.id,user.id)
        return f'Blacklist {action} saved for {user.id}.'

    @app_commands.command(name='blacklist',description='Manage this server’s bot blacklist')
    @app_commands.default_permissions(administrator=True)
    @app_commands.choices(action=[app_commands.Choice(name=x,value=x) for x in ('add','remove','list')])
    async def blacklist(self,interaction:discord.Interaction,action:str,user:discord.User|None=None):
        await defer(interaction,ephemeral=True)
        await respond(interaction,content=await self.operation(interaction.guild,interaction.user,action,user))

    @commands.group(name='blacklist',invoke_without_command=True)
    async def blacklist_prefix(self,ctx):await ctx.send(await self.operation(ctx.guild,ctx.author,'list'))
    @blacklist_prefix.command(name='add')
    async def add(self,ctx,user:discord.User):await ctx.send(await self.operation(ctx.guild,ctx.author,'add',user))
    @blacklist_prefix.command(name='remove')
    async def remove(self,ctx,user:discord.User):await ctx.send(await self.operation(ctx.guild,ctx.author,'remove',user))
    @blacklist_prefix.command(name='list')
    async def list_users(self,ctx):await ctx.send(await self.operation(ctx.guild,ctx.author,'list'))


async def setup(bot):await bot.add_cog(Blacklist(bot))
