import discord
from discord import app_commands
from discord.ext import commands
from core.checks import require_permission
from core.errors import defer,UserError,respond
from services.moderation import bounded_positive


class Purge(commands.Cog):
    def __init__(self,bot):self.bot=bot

    @app_commands.command(name='purge',description='Delete recent messages in this channel')
    @app_commands.default_permissions(manage_messages=True)
    async def purge(self,interaction:discord.Interaction,limit:int=100):
        require_permission(interaction.guild,interaction.user,'manage_messages','manage_messages')
        bounded_positive(limit,2000)
        if not hasattr(interaction.channel,'purge'):raise UserError('This channel does not support message purging.')
        actor_permissions=interaction.channel.permissions_for(interaction.user)
        bot_permissions=interaction.channel.permissions_for(interaction.guild.me)
        if not actor_permissions.manage_messages:raise UserError('You cannot manage messages in this channel.')
        if not all(getattr(bot_permissions,name,False) for name in ('manage_messages','read_message_history','view_channel')):
            raise UserError('The bot needs View Channel, Read Message History and Manage Messages in this channel.')
        await defer(interaction,ephemeral=True)
        deleted=await interaction.channel.purge(limit=limit)
        await respond(interaction,content=f'Purged {len(deleted)} messages.')
        await self.bot.send_mod_log(interaction.guild,'Messages purged',f'{len(deleted)} messages; moderator {interaction.user.id}; channel {interaction.channel_id}')


async def setup(bot):await bot.add_cog(Purge(bot))
