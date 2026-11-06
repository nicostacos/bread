import discord
from discord import app_commands
from discord.ext import commands
from core.checks import require_permission
from core.errors import defer,respond


class Channels(commands.Cog):
    def __init__(self,bot):self.bot=bot

    async def save(self,guild,actor,key,channel):
        require_permission(guild,actor,'administrator')
        if channel.guild.id!=guild.id:raise commands.BadArgument('Choose a channel in this server.')
        await self.bot.repos.configs.update(guild.id,{key:str(channel.id)})

    @app_commands.command(name='setlog',description='Set the moderation log channel')
    @app_commands.default_permissions(administrator=True)
    async def setlog(self,interaction:discord.Interaction,channel:discord.TextChannel):
        await defer(interaction,ephemeral=True)
        await self.save(interaction.guild,interaction.user,'log_channel',channel)
        await respond(interaction,content=f'Log channel saved: {channel.mention}')

    @app_commands.command(name='setwelcome',description='Set the welcome channel')
    @app_commands.default_permissions(administrator=True)
    async def setwelcome(self,interaction:discord.Interaction,channel:discord.TextChannel):
        await defer(interaction,ephemeral=True)
        await self.save(interaction.guild,interaction.user,'welcome_channel',channel)
        await respond(interaction,content=f'Welcome channel saved: {channel.mention}')

    @app_commands.command(name='get_channels',description='Show saved server channels')
    @app_commands.default_permissions(administrator=True)
    async def get_channels(self,interaction:discord.Interaction):
        require_permission(interaction.guild,interaction.user,'administrator')
        await defer(interaction,ephemeral=True)
        await respond(interaction,content=await self.describe(interaction.guild.id))

    async def describe(self,guild_id):
        settings=await self.bot.repos.configs.get(guild_id)
        return '\n'.join(f"{key}: "+(f"<#{settings[key]}>" if settings.get(key) else 'Not configured') for key in ('log_channel','welcome_channel'))

    @commands.command(name='setlog')
    async def prefix_setlog(self,ctx,channel:discord.TextChannel):
        await self.save(ctx.guild,ctx.author,'log_channel',channel);await ctx.send(f'Log channel saved: {channel.mention}')

    @commands.command(name='setwelcome')
    async def prefix_setwelcome(self,ctx,channel:discord.TextChannel):
        await self.save(ctx.guild,ctx.author,'welcome_channel',channel);await ctx.send(f'Welcome channel saved: {channel.mention}')

    @commands.command(name='getchannels')
    async def prefix_getchannels(self,ctx):
        require_permission(ctx.guild,ctx.author,'administrator');await ctx.send(await self.describe(ctx.guild.id))


async def setup(bot):await bot.add_cog(Channels(bot))
