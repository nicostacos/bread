import discord
from discord import app_commands
from discord.ext import commands
from core.checks import validate_target
from core.errors import defer,UserError,respond
from services.moderation import bounded_positive


class Timeout(commands.Cog):
    def __init__(self,bot):self.bot=bot

    @app_commands.command(name='mute',description='Timeout a member for a positive number of minutes')
    @app_commands.default_permissions(moderate_members=True)
    async def mute(self,interaction:discord.Interaction,member:discord.Member,duration:int=10,reason:str='No reason provided',evidence:str=''):
        validate_target(interaction.guild,interaction.user,member,'moderate_members')
        bounded_positive(duration,40320)
        if member.guild_permissions.administrator:raise UserError('Administrators cannot be timed out.')
        await defer(interaction,ephemeral=True)
        result=await self.bot.moderation.execute(interaction.guild,interaction.user,member,'timeout',reason,evidence,duration)
        await respond(interaction,content=f'Timeout completed for {member.id}: {duration} minutes.'+(f" Audit error: {result['audit_error']}" if result['audit_error'] else ''))


async def setup(bot):await bot.add_cog(Timeout(bot))
