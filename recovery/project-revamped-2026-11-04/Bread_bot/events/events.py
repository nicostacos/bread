"""
Discord bot event handlers
"""
import asyncio
import re

import aiohttp
import discord
from discord.ext import commands

from config import PING_URL, TIME_ID, DEFAULT_FILTER_WORDS, BLACKLIST_BLOCK_MESSAGE, GLOBAL_BLACKLIST
from utils.config_manager import load_config, load_filter_words, get_filter_cache
from utils.helpers import is_user_blocked, send_mod_log, _queue_rejoin_invite
from utils.database import scheduled_invites_collection, warnings_collection

bot_start_time = None


async def on_guild_remove(guild):
    """Clean up cache and database entries when the bot leaves a guild."""
    from utils.database import (
        config_collection, filter_collection, warnings_collection,
        moderation_cases_collection, scheduled_invites_collection, guild_blacklist_collection
    )
    guild_id = guild.id
    _filter_cache = get_filter_cache()
    _filter_cache.pop(guild_id, None)
    await config_collection.delete_one({"guild_id": guild_id})
    await filter_collection.delete_many({"guild_id": guild_id})
    await warnings_collection.delete_many({"guild_id": guild_id})
    await moderation_cases_collection.delete_many({"guild_id": guild_id})
    await scheduled_invites_collection.delete_many({"guild_id": guild_id})
    await guild_blacklist_collection.delete_many({"guild_id": guild_id})


async def global_prefix_block_check(ctx):
    """Check for blacklisted users in prefix commands"""
    try:
        if not ctx.guild:
            return
        if await is_user_blocked(ctx.guild.id, ctx.author.id):
            try:
                block_type = "Global blacklist" if int(ctx.author.id) in GLOBAL_BLACKLIST else "Server blacklist"
            except Exception:
                block_type = "Server blacklist"
            try:
                command_name = getattr(ctx.command, 'name', None) or ctx.invoked_with or 'unknown'
            except Exception:
                command_name = 'unknown'
            await ctx.send(BLACKLIST_BLOCK_MESSAGE)

            try:
                await send_mod_log(
                    guild=ctx.guild,
                    title="\u26d4 Blocked Command Attempt",
                    description=f"{ctx.author.mention} attempted to use `{command_name}` but was blocked.",
                    color=0xFF0000,
                    fields=[
                        ("User", f"{ctx.author} ({ctx.author.id})", False),
                        ("Command", f"`{command_name}`", True),
                        ("Block Type", block_type, True),
                    ],
                )
            except Exception:
                pass
    except Exception as e:
        print(f"[ERROR] global_prefix_block_check: {e}")


async def global_slash_block_check(interaction: discord.Interaction):
    """Check for blacklisted users in slash commands"""
    try:
        if not interaction.guild:
            return True
        if await is_user_blocked(interaction.guild.id, interaction.user.id):
            try:
                block_type = "Global blacklist" if int(interaction.user.id) in GLOBAL_BLACKLIST else "Server blacklist"
            except Exception:
                block_type = "Server blacklist"
            command_name = 'unknown'
            if interaction.command is not None:
                command_name = getattr(interaction.command, 'name', 'unknown')
            await interaction.response.send_message(BLACKLIST_BLOCK_MESSAGE, ephemeral=True)

            try:
                await send_mod_log(
                    guild=interaction.guild,
                    title="\u26d4 Blocked Slash Command Attempt",
                    description=f"{interaction.user.mention} attempted to use `/{command_name}` but was blocked.",
                    color=0xFF0000,
                    fields=[
                        ("User", f"{interaction.user} ({interaction.user.id})", False),
                        ("Command", f"/{command_name}", True),
                        ("Block Type", block_type, True),
                    ],
                )
            except Exception:
                pass
            return False
        return True
    except Exception as e:
        print(f"[ERROR] global_slash_block_check: {e}")
        return True


async def keep_alive_task(bot):
    """Background task to keep the bot alive"""
    import aiohttp
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(PING_URL) as response:
                    if response.status != 200:
                        print(f"[WARN] Keep-alive ping failed: {response.status}")
        except Exception as e:
            print(f"[ERROR] Keep-alive error: {e}")
        
        await asyncio.sleep(60)  # Check every minute


async def process_scheduled_invites(bot):
    """Background task to process scheduled invites"""
    while True:
        try:
            now = discord.utils.utcnow()
            # Find invites that need to be sent
            # scheduled_invites_collection.find may be a coroutine in this driver
            # so await it if necessary to get an async cursor before iterating.
            find_result = scheduled_invites_collection.find({
                "status": "pending",
                "send_at": {"$lte": now}
            })
            cursor = await find_result if asyncio.iscoroutine(find_result) else find_result

            pending = []
            try:
                if hasattr(cursor, "to_list"):
                    pending = await cursor.to_list(length=None)
                else:
                    async for invite_data in cursor: # type: ignore
                        pending.append(invite_data)
            except Exception as e:
                print(f"[ERROR] fetching scheduled invites cursor: {e}")

            for invite_data in pending:
                try:
                    guild = bot.get_guild(invite_data["guild_id"])
                    user = bot.get_user(invite_data["user_id"])
                    
                    if guild and user:
                        # Create invite
                        channel = next(
                            (ch for ch in guild.text_channels
                             if ch.permissions_for(guild.me).create_instant_invite),
                            None
                        )
                        if channel:
                            invite = await channel.create_invite(
                                max_age=604800,
                                max_uses=1,
                                reason=f"Scheduled unkick: {invite_data.get('reason', 'No reason')}"
                            )
                            try:
                                await user.send(
                                    f"You have been invited back to **{guild.name}**.\n"
                                    f"Reason: {invite_data.get('reason', 'No reason')}\n"
                                    f"{invite.url}"
                                )
                                await scheduled_invites_collection.update_one(
                                    {"_id": invite_data["_id"]},
                                    {"$set": {"status": "sent"}}
                                )
                            except Exception as e:
                                print(f"[ERROR] Failed to send scheduled invite to {user}: {e}")
                except Exception as e:
                    print(f"[ERROR] Processing scheduled invite: {e}")
        except Exception as e:
            print(f"[ERROR] process_scheduled_invites: {e}")
        
        await asyncio.sleep(60)  # Check every minute


async def on_message(bot, message):
    """Handle message events including chat filtering"""
    if message.author == bot.user:
        return

    if isinstance(message.channel, discord.DMChannel):
        if message.content.startswith("bread "):
            await message.channel.send(
                "Hello! You cannot use prefix commands in DMs, use slash commands instead."
            )
        return

    if message.content.startswith("bread "):
        await bot.process_commands(message)
        return

    if message.guild:
        guild_id = message.guild.id
        guild_filter_words = await load_filter_words(guild_id)
        _filter_cache = get_filter_cache()
        filter_enabled = _filter_cache[guild_id][0]

        if filter_enabled and guild_filter_words:
            message_lower = message.content.lower()
            # Create a regex pattern that matches any of the filter words
            pattern = re.compile(r"\b" + "\b|\b".join(map(re.escape, guild_filter_words)) + "\b", re.IGNORECASE)
            matches = pattern.findall(message_lower)

            if matches:
                try:
                    await message.delete()
                    embed = discord.Embed(
                        title="\ud83d\udeab Message Filtered",
                        description=f"Your message contained forbidden words: {', '.join(set(matches))}",
                        color=0xFF0000,
                    )
                    embed.add_field(name="Note", value="Repeated offenses may result in a kick or ban.", inline=False)
                    try:
                        await message.author.send(embed=embed)
                    except discord.Forbidden:
                        pass  # User has DMs disabled
                    
                    await send_mod_log(
                        guild=message.guild,
                        title="\ud83d\udeab Message Filtered",
                        description=f"{message.author.mention}'s message was filtered.",
                        color=0xFF0000,
                        fields=[
                            ("User", f"{message.author} ({message.author.id})", False),
                            ("Channel", message.channel.mention, True),
                            ("Matched Words", ", ".join(set(matches)), True),
                        ],
                        thumbnail=(message.author.avatar.url if message.author.avatar else None),
                    )
                except discord.Forbidden:
                    pass
                except Exception as e:
                    print(f"[ERROR] filtering message: {e}")


async def on_member_join(bot, member):
    """Send welcome message to new members"""
    try:
        _, welcome_channel_id = await load_config(member.guild.id)

        if welcome_channel_id:
            channel = member.guild.get_channel(welcome_channel_id)
            if channel:
                embed = discord.Embed(
                    title="Welcome!",
                    description=f"{member.mention} has joined the server!",
                    color=discord.Color.green(),
                )
                if member.avatar:
                    embed.set_thumbnail(url=member.avatar.url)
                await channel.send(embed=embed)
    except Exception as e:
        print(f"Failed to send DM to {member.name}: {e}")
    
    try:
        if hasattr(bot.tree, "add_check"):
            bot.tree.add_check(global_slash_block_check)
        else:
            for cmd in bot.tree.get_commands():
                try:
                    if not hasattr(cmd, "checks"):
                        continue
                    cmd.checks.append(global_slash_block_check)
                except Exception:
                    continue
    except Exception as e:
        print(f"[WARN] Could not register global slash check: {e}")
    
    # Create database indexes (async)
    try:
        await scheduled_invites_collection.create_index([("status", 1), ("send_at", 1)])
        await warnings_collection.create_index([("guild_id", 1), ("user_id", 1), ("created_at", 1)])
    except Exception as e:
        print(f"[WARN] Could not create database indexes: {e}")


async def on_ready(bot):
    """Called when the bot is ready"""
    global bot_start_time
    if bot_start_time is None:
        bot_start_time = discord.utils.utcnow()

    print(f"We are ready to go in, {bot.user.name}")
    try:
        synced = bot.tree.get_commands()
        print(f"\u2705 Synced {len(synced)} global commands: {[cmd.name for cmd in synced]}")
        # Print debug info on startup
        from utils.database import check_mongodb_connection, debug_db
        await check_mongodb_connection()
        await debug_db()
    except Exception as e:
        print(f"\u274c Failed to sync commands: {e}")

async def setup_hook(bot):
    """Setup hook for bot initialization"""
    # Use discord's aiohttp session
    bot.aiohttp_session = aiohttp.ClientSession()