"""
Discord bot event handlers
"""
import discord
from discord.ext import commands
import asyncio
import re
from config import PING_URL, TIME_ID, DEFAULT_FILTER_WORDS, BLACKLIST_BLOCK_MESSAGE, GLOBAL_BLACKLIST
from utils.config_manager import load_config, load_filter_words, get_filter_cache
from utils.helpers import is_user_blocked, send_mod_log, _queue_rejoin_invite
from utils.database import scheduled_invites_collection, warnings_collection


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
                    title="⛔ Blocked Command Attempt",
                    description=f"{ctx.author.mention} attempted to run `{command_name}` but was blocked.",
                    color=0xFF0000,
                    fields=[
                        ("User", f"{ctx.author} ({ctx.author.id})", False),
                        ("Type", block_type, True),
                        ("Command", command_name, True),
                        ("Channel", ctx.channel.mention if ctx.channel else "DM", True),
                        ("Context", "prefix", True),
                    ],
                    thumbnail=(ctx.author.avatar.url if ctx.author.avatar else None),
                )
            except Exception:
                pass

            raise commands.CheckFailure("user_blacklisted")
    except commands.CheckFailure:
        raise
    except Exception as e:
        print(f"[WARN] global_prefix_block_check error: {e}")


async def global_slash_block_check(interaction: discord.Interaction):
    """Check for slash/app command invocations from blacklisted users."""
    try:
        if not interaction.guild:
            return True
        if await is_user_blocked(interaction.guild.id, interaction.user.id):
            try:
                await interaction.response.send_message(BLACKLIST_BLOCK_MESSAGE, ephemeral=True)
            except Exception:
                pass
            try:
                block_type = "Global blacklist" if int(interaction.user.id) in GLOBAL_BLACKLIST else "Server blacklist"
            except Exception:
                block_type = "Server blacklist"
            try:
                cmd_name = None
                if hasattr(interaction, 'command') and interaction.command:
                    cmd_name = getattr(interaction.command, 'name', None)
                if not cmd_name:
                    cmd_name = interaction.data.get('name') if isinstance(interaction.data, dict) else None
                if not cmd_name:
                    cmd_name = 'unknown'
            except Exception:
                cmd_name = 'unknown'
            try:
                if interaction.guild:
                    ch_mention = interaction.channel.mention if getattr(interaction, 'channel', None) else 'DM'
                    await send_mod_log(
                        guild=interaction.guild,
                        title="⛔ Blocked Command Attempt",
                        description=f"{interaction.user.mention} attempted to run `{cmd_name}` but was blocked.",
                        color=0xFF0000,
                        fields=[
                            ("User", f"{interaction.user} ({interaction.user.id})", False),
                            ("Type", block_type, True),
                            ("Command", cmd_name, True),
                            ("Channel", ch_mention, True),
                            ("Context", "slash", True),
                        ],
                        thumbnail=(interaction.user.avatar.url if interaction.user.avatar else None),
                    )
            except Exception:
                pass

            raise discord.app_commands.CheckFailure("user_blacklisted")
        return True
    except discord.app_commands.CheckFailure:
        raise
    except Exception as e:
        print(f"[WARN] global_slash_block_check error: {e}")
        return True


async def keep_alive_task(bot):
    """Keep-alive task to ping the bot's endpoint"""
    await bot.wait_until_ready()
    channel = bot.get_channel(TIME_ID)

    if channel is None:
        print(f"❌ Could not find channel with ID {TIME_ID}")
        return

    while not bot.is_closed():
        try:
            async with bot.aiohttp_session.get(PING_URL) as resp:
                status = resp.status
            embed = discord.Embed(
                title="🌐 Keep Alive Ping",
                description=f"Pinged `{PING_URL}`",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow(),
            )
            embed.add_field(name="Status", value=f"{status}", inline=True)
            await channel.send(embed=embed)
            print(f"[KeepAlive] Sent ping with status {status}")
        except Exception as e:
            embed = discord.Embed(
                title="⚠️ Keep Alive Error",
                description=f"Failed to ping `{PING_URL}`",
                color=discord.Color.red(),
                timestamp=discord.utils.utcnow(),
            )
            embed.add_field(name="Error", value=str(e), inline=False)
            await channel.send(embed=embed)
            print(f"[KeepAlive] Error: {e}")
        await asyncio.sleep(300)  # every 5 minutes


async def process_scheduled_invites(bot):
    """Process scheduled rejoin invites"""
    await bot.wait_until_ready()
    
    while not bot.is_closed():
        try:
            now = discord.utils.utcnow()
            # Find pending invites that should be sent now
            cursor = scheduled_invites_collection.find({
                "status": "pending",
                "send_at": {"$lte": now}
            })
            
            items = await cursor.to_list(length=None)
            
            for item in items:
                try:
                    guild = bot.get_guild(item["guild_id"])
                    user = bot.get_user(item["user_id"]) or await bot.fetch_user(item["user_id"])
                    channel = next((c for c in guild.text_channels if c.permissions_for(guild.me).create_instant_invite), None) if guild else None
                    if not channel:
                        raise RuntimeError("No channel is available for creating an invite")
                    invite = await channel.create_invite(max_age=604800, max_uses=1, reason="Scheduled moderation rejoin invite")
                    await user.send(f"You may rejoin **{guild.name}**: {invite.url}")
                    await scheduled_invites_collection.update_one({"_id": item["_id"]}, {"$set": {"status": "sent", "sent_at": discord.utils.utcnow()}})
                    await send_mod_log(guild, "Rejoin invite sent", f"A scheduled invite was sent to <@{item['user_id']}>.", 0x2ECC71)
                except Exception as exc:
                    print(f"[ERROR] scheduled invite: {exc}")
                    await scheduled_invites_collection.update_one({"_id": item["_id"]}, {"$set": {"status": "failed", "error": str(exc)}})
        except Exception as e:
            print(f"[ERROR] process_scheduled_invites: {e}")
        
        await asyncio.sleep(60)  # Check every minute


async def on_message(message):
    """Handle message events including chat filtering"""
    if message.author == message.guild.me:
        return

    if isinstance(message.channel, discord.DMChannel):
        if message.content.startswith("bread "):
            await message.channel.send(
                "Hello! You cannot use prefix commands in DMs, use slash commands instead."
            )
        return

    if message.content.startswith("bread "):
        # Process prefix commands
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
                        title="🚫 Message Filtered",
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
                        title="🚫 Message Filtered",
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


async def on_member_join(member):
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


async def setup_hook(bot):
    """Setup hook for bot initialization"""
    bot.aiohttp_session = bot.http._HTTPClient__session  # Use discord's aiohttp session
    bot.background_task = asyncio.create_task(keep_alive_task(bot))
    bot.scheduled_invite_task = asyncio.create_task(process_scheduled_invites(bot))
    
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
    
    print("Syncing application commands...")
    await bot.tree.sync()

    # Create database indexes (async)
    await scheduled_invites_collection.create_index([("status", 1), ("send_at", 1)])
    await warnings_collection.create_index([("guild_id", 1), ("user_id", 1), ("created_at", 1)])


async def on_ready(bot):
    """Called when the bot is ready"""
    global bot_start_time
    if bot_start_time is None:
        bot_start_time = discord.utils.utcnow()

    print(f"We are ready to go in, {bot.user.name}")
    try:
        synced = bot.tree.get_commands()
        print(f"✅ Synced {len(synced)} global commands: {[cmd.name for cmd in synced]}")
        # Print debug info on startup
        from utils.database import check_mongodb_connection, debug_db
        await check_mongodb_connection()
        await debug_db()
    except Exception as e:
        print(f"❌ Failed to sync commands: {e}")


# Global variable for bot start time
bot_start_time = None
