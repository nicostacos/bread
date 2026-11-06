import discord
from discord import app_commands
from discord.ext import commands
from core.checks import require_permission,validate_target
from core.errors import defer,respond,report_error
from core.pagination import Pager
from core.evidence import EvidenceView
from services.moderation import warning_pages
from core.presentation import warning_embed
from core.warning_controls import WarningControls


class Warnings(commands.Cog):
    def __init__(self,bot):self.bot=bot

    @app_commands.command(name='warn',description='Record a warning and optional evidence')
    @app_commands.default_permissions(moderate_members=True)
    async def warn(self,interaction:discord.Interaction,member:discord.Member,reason:str,evidence:str=''):
        validate_target(interaction.guild,interaction.user,member,'moderate_members')
        await defer(interaction,ephemeral=True)
        row=await self.bot.repos.warnings.add(interaction.guild_id,member.id,interaction.user.id,reason,evidence)
        message=f"Warning #{row['warning_number']} saved for {member.id}."
        try:
            await self.bot.repos.cases.record(interaction.guild_id,member.id,interaction.user.id,'warn',reason,evidence)
            await self.bot.send_mod_log(interaction.guild,'⚠️ Warning recorded',f'👤 Member: <@{member.id}>\n🛡️ Moderator: <@{interaction.user.id}>\n📝 Reason: {reason}\n🔎 Evidence: {evidence}\n🗂️ Case: {row["id"]}')
        except Exception as error:
            message+=' Audit error: '+report_error(error,{'event':'warning_audit','guild':interaction.guild_id})
        if row.get('escalation'):
            action=row['escalation']
            try:
                validate_target(interaction.guild,interaction.user,member,'kick_members' if action=='kick' else 'ban_members')
                result=await self.bot.moderation.execute(interaction.guild,interaction.user,member,action,
                    f"Automatic {action} after warning #{row['warning_number']}",evidence)
                message+=f' Automatic {action} completed.'
                if result['audit_error']:message+=f" Audit error: {result['audit_error']}"
            except Exception as error:
                ref=report_error(error,{'event':'warning_escalation','guild':interaction.guild_id,'warning':row['id']})
                message+=f' Automatic {action} could not be confirmed; check server audit logs before retrying. Error ID: {ref}.'
        row={**row,'user_id':str(member.id),'moderator_id':str(interaction.user.id),'reason':reason,'evidence':evidence}
        await respond(interaction,embed=warning_embed(row,note=message),view=WarningControls(self.bot,interaction.guild_id,[row],interaction.user.id))

    @app_commands.command(name='warnings',description='View member warning history')
    @app_commands.default_permissions(moderate_members=True)
    async def warnings(self,interaction:discord.Interaction,member:discord.Member):
        require_permission(interaction.guild,interaction.user,'moderate_members')
        await defer(interaction,ephemeral=True)
        view=WarningControls(self.bot,interaction.guild_id,await self.bot.repos.warnings.list(interaction.guild_id,member.id),interaction.user.id)
        await respond(interaction,embed=view.embed(),view=view)

    @commands.command(name='warn')
    async def warn_prefix(self,ctx,member:discord.Member,*,reason:str):
        validate_target(ctx.guild,ctx.author,member,'moderate_members')
        await ctx.send(embed=warning_embed({'user_id':str(member.id),'moderator_id':str(ctx.author.id),'reason':reason,'evidence':'Add evidence in the form','id':'Not saved yet','warning_number':'draft'},
            title='📝 Prepare a warning',note='Nothing has been saved yet. Use the button to add evidence and submit. Expires in 3 minutes.'),
            view=EvidenceView(self.bot,'warn',ctx.author.id,ctx.guild.id,member.id,reason))

    @commands.command(name='warnings')
    async def warnings_prefix(self,ctx,member:discord.Member):
        require_permission(ctx.guild,ctx.author,'moderate_members')
        view=WarningControls(self.bot,ctx.guild.id,await self.bot.repos.warnings.list(ctx.guild.id,member.id),ctx.author.id)
        await ctx.send(embed=view.embed(),view=view)


async def setup(bot):await bot.add_cog(Warnings(bot))
