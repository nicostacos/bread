from core.errors import respond
import discord
from discord import app_commands
from discord.ext import commands
from core.presentation import user_info_embed
import math


def bot_info_embed(bot,guild,requester):
    embed=discord.Embed(title='🤖 Bot Status Report',color=0x57F287 if bot.is_ready() else 0xFEE75C,
                        timestamp=discord.utils.utcnow())
    latency=bot.latency
    latency_text=f'{latency*1000:.0f} ms' if math.isfinite(latency) else 'Connecting…'
    since=getattr(bot,'online_since',None)
    embed.add_field(name='🔧 Bot Info',value=(
        f'**Status:** {"Online ✅" if bot.is_ready() else "Connecting ⏳"}\n'
        f'**Latency:** {latency_text}\n'
        f'**Online Since:** {discord.utils.format_dt(since,"R") if since else "Starting up…"}'),inline=False)
    known=[g.member_count for g in bot.guilds if g.member_count is not None]
    count=f'{sum(known):,}'+(' (partial)' if len(known)<len(bot.guilds) else '')
    embed.add_field(name='📊 Server Stats',value=(
        f'**Servers:** {len(bot.guilds):,}\n**Total Members:** {count}\n'
        f'**Current Server:** {discord.utils.escape_markdown(guild.name)[:200]}'),inline=True)
    embed.add_field(name='⚡ Commands',value=(
        f'**Slash Commands:** {len(bot.tree.get_commands())}\n'
        f'**Prefix Commands:** {sum(1 for _ in bot.walk_commands())}\n'
        '**Status:** Loaded ✅'),inline=True)
    permissions=getattr(guild.me,'guild_permissions',None)
    names=(('kick_members','Kick Members'),('ban_members','Ban Members'),('manage_messages','Manage Messages'))
    lines=[f'**{label}:** '+('✅' if getattr(permissions,key,False) else '❌') for key,label in names]
    complete=all(getattr(permissions,key,False) for key,_ in names)
    lines.append('**Status:** '+('Ready ✅' if complete else 'Some permissions missing ⚠️'))
    embed.add_field(name='🔑 Bot Permissions',value='\n'.join(lines),inline=False)
    avatar=getattr(bot.user,'display_avatar',None)
    if avatar:embed.set_thumbnail(url=avatar.url)
    embed.set_footer(text=f'Requested by {getattr(requester,"display_name",str(requester))}'[:2048])
    return embed


def server_info_embed(guild):
    owner=discord.utils.escape_markdown(guild.owner.name) if guild.owner else f'<@{guild.owner_id}>'
    members=f'{guild.member_count:,}' if guild.member_count is not None else 'Unknown'
    embed=discord.Embed(title=guild.name,color=0x3498DB,
        description=f'**Owner:** {owner}\n**Members:** {members}\n**Roles:** {len(guild.roles):,}')
    if guild.icon:embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(name='Channels',value=(
        f'**Category Channels:** {len(guild.categories):,}\n'
        f'**Text Channels:** {len(guild.text_channels):,}\n'
        f'**Voice Channels:** {len(guild.voice_channels):,}'),inline=False)
    embed.add_field(name='Server details',value=(
        f'**ID:** `{guild.id}`\n'
        f'**Server Created:** {discord.utils.format_dt(guild.created_at,"F")} '
        f'({discord.utils.format_dt(guild.created_at,"R")})'),inline=False)
    return embed


class Info(commands.Cog):
    def __init__(self,bot):self.bot=bot
    @app_commands.command(name='botinfo',description='Show bot information')
    async def botinfo(self,interaction:discord.Interaction):
        await respond(interaction,embed=bot_info_embed(self.bot,interaction.guild,interaction.user),ephemeral=False)
    @app_commands.command(name='serverinfo',description='Show server information')
    async def serverinfo(self,interaction:discord.Interaction):
        await respond(interaction,embed=server_info_embed(interaction.guild))
    @app_commands.command(name='userinfo',description='Show user information')
    async def userinfo(self,interaction:discord.Interaction,user:discord.User|None=None):
        user=user or interaction.user
        member=interaction.guild.get_member(user.id)
        await respond(interaction,embed=user_info_embed(user,member))


async def setup(bot):await bot.add_cog(Info(bot))
