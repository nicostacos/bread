import discord
from discord import app_commands
from discord.ext import commands
from core.checks import require_permission
from core.errors import defer,UserError,respond


class Invites(commands.Cog):
    def __init__(self,bot):self.bot=bot

    @app_commands.command(name='unkick',description='Send a user a fresh one-use server invite')
    @app_commands.default_permissions(kick_members=True)
    async def unkick(self,interaction:discord.Interaction,user:discord.User,reason:str):
        require_permission(interaction.guild,interaction.user,'kick_members')
        if interaction.guild.get_member(user.id):raise UserError('That user is already in this server.')
        await defer(interaction,ephemeral=True)
        await self.bot.invites.send_once(interaction.guild,user,reason)
        await respond(interaction,content=f'Invite sent to {user.id}.')


async def setup(bot):await bot.add_cog(Invites(bot))
