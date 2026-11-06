import discord
from discord import app_commands
from discord.ext import commands
from core.checks import validate_target
from core.errors import defer,respond
from core.evidence import EvidenceView


class Kick(commands.Cog):
    def __init__(self,bot):self.bot=bot

    @app_commands.command(name='kick',description='Kick a member with a reason and optional evidence')
    @app_commands.default_permissions(kick_members=True)
    async def kick_slash(self,interaction:discord.Interaction,member:discord.Member,reason:str='No reason provided',evidence:str=''):
        validate_target(interaction.guild,interaction.user,member,'kick_members')
        await defer(interaction,ephemeral=True)
        result=await self.bot.moderation.execute(interaction.guild,interaction.user,member,'kick',reason,evidence)
        await respond(interaction,content=f'Kick completed for {member.id}.'+(f" Audit logging needs attention: {result['audit_error']}" if result['audit_error'] else ''))

    @commands.command(name='kick')
    async def kick_prefix(self,ctx,member:discord.Member,*,reason='No reason provided'):
        validate_target(ctx.guild,ctx.author,member,'kick_members')
        await ctx.send(f'Kick requested for {member.id}. Add evidence and submit the form to perform the action. Expires in 3 minutes.',
            view=EvidenceView(self.bot,'kick',ctx.author.id,ctx.guild.id,member.id,reason))


async def setup(bot):await bot.add_cog(Kick(bot))
