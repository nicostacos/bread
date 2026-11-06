import discord
from discord import app_commands
from discord.ext import commands
from core.checks import validate_target,require_permission
from core.errors import defer,respond


class Ban(commands.Cog):
    def __init__(self,bot):self.bot=bot

    @app_commands.command(name='ban',description='Ban a member')
    @app_commands.default_permissions(ban_members=True)
    async def ban(self,interaction:discord.Interaction,member:discord.Member,reason:str='No reason provided',evidence:str=''):
        validate_target(interaction.guild,interaction.user,member,'ban_members')
        await defer(interaction,ephemeral=True)
        result=await self.bot.moderation.execute(interaction.guild,interaction.user,member,'ban',reason,evidence)
        await respond(interaction,content=f'Ban completed for {member.id}.'+(f" Audit error: {result['audit_error']}" if result['audit_error'] else ''))

    @app_commands.command(name='unban',description='Unban a user')
    @app_commands.default_permissions(ban_members=True)
    async def unban(self,interaction:discord.Interaction,user:discord.User,reason:str='No reason provided'):
        require_permission(interaction.guild,interaction.user,'ban_members','ban_members')
        await defer(interaction,ephemeral=True)
        result=await self.bot.moderation.execute(interaction.guild,interaction.user,user,'unban',reason)
        await respond(interaction,content=f'Unban completed for {user.id}.'+(f" Audit error: {result['audit_error']}" if result['audit_error'] else ''))


async def setup(bot):await bot.add_cog(Ban(bot))
