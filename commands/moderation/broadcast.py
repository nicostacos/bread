import discord
from discord import app_commands
from discord.ext import commands
from core.checks import require_permission
from core.errors import defer,UserError,respond,report_error


class Broadcast(commands.Cog):
    def __init__(self,bot):self.bot=bot

    @app_commands.command(name='broadcast',description='Broadcast a message to server text channels')
    @app_commands.default_permissions(administrator=True)
    async def broadcast(self,interaction:discord.Interaction,message:str,ping_everyone:bool=False):
        require_permission(interaction.guild,interaction.user,'administrator')
        if not message.strip() or len(message)+(10 if ping_everyone else 0)>2000:raise UserError('Message must be nonempty and at most 2000 characters including the optional ping.')
        await defer(interaction,ephemeral=True)
        sent=failed=0
        for channel in interaction.guild.text_channels:
            if not channel.permissions_for(interaction.guild.me).send_messages:continue
            try:
                await channel.send(('@everyone '+message) if ping_everyone else message,
                    allowed_mentions=discord.AllowedMentions(everyone=ping_everyone,users=False,roles=False))
                sent+=1
            except discord.HTTPException as error:
                failed+=1;report_error(error,{'event':'broadcast_channel','guild':interaction.guild_id,'channel':channel.id})
        await respond(interaction,content=f'Broadcast completed: {sent} channels sent, {failed} failed.')


async def setup(bot):await bot.add_cog(Broadcast(bot))
