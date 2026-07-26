"""
Admin commands for Bread Bot
"""
import discord
from discord import app_commands
from discord.ext import commands
import re
import asyncio

from config import DEFAULT_FILTER_WORDS
from utils.config_manager import (
    save_config, load_config, save_filter_words, load_filter_words,
    reset_filter_words, set_filter_enabled, get_filter_cache, save_automod_rule_id, load_automod_rule_id
)
from utils.helpers import send_mod_log, _queue_rejoin_invite
from utils.database import filter_collection


class Admin(commands.Cog):
    """Admin commands"""
    
    def __init__(self, bot):
        self.bot = bot
        self._filter_cache = get_filter_cache()
    
    # ===== Filter Commands (Slash) =====
    
    @app_commands.command(name="filter", description="Manage the chat filter")
    @app_commands.describe(
        action="add/remove/reset/status",
        word="Word to add or remove"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="add", value="add"),
        app_commands.Choice(name="remove", value="remove"),
        app_commands.Choice(name="reset", value="reset"),
        app_commands.Choice(name="status", value="status"),
    ])
    @app_commands.default_permissions(manage_messages=True)
    async def filter_slash(self, interaction: discord.Interaction, action: str, word: str = ""):
        """Manage chat filter (slash command)"""
        guild_id = interaction.guild.id
        
        if action == "add":
            if not word:
                await interaction.response.send_message(
                    "❌ Please provide a word to add!", ephemeral=True
                )
                return
            
            word = word.lower()
            current_words = await load_filter_words(guild_id)
            
            if word in current_words:
                await interaction.response.send_message(
                    f"❌ `{word}` is already in the filter!", ephemeral=True
                )
                return
            
            current_words.append(word)
            await save_filter_words(guild_id, current_words)
            
            embed = discord.Embed(
                title="✅ Word Added to Filter",
                description=f"Added `{word}` to the chat filter",
                color=0x00FF00,
            )
            embed.add_field(
                name="Total Filtered Words", value=str(len(current_words)), inline=True
            )
            embed.set_footer(text=f"Modified by {interaction.user.name}")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
            # Attempt to update automod rule if present
            try:
                existing_rule_id = await load_automod_rule_id(guild_id)
                log_channel_id, _ = await load_config(guild_id)
                alert_channel = int(log_channel_id) if log_channel_id else None
                
                if existing_rule_id:
                    updated = await self._update_automod_rule_keywords(
                        interaction.guild, existing_rule_id, current_words, alert_channel
                    )
            except Exception as e:
                print(f"[ERROR] updating automod after filter add: {e}")

        elif action == "remove":
            if not word:
                await interaction.response.send_message(
                    "❌ Please provide a word to remove!", ephemeral=True
                )
                return
            
            word = word.lower()
            current_words = await load_filter_words(guild_id)
            
            if word not in current_words:
                await interaction.response.send_message(
                    f"❌ `{word}` is not in the filter!", ephemeral=True
                )
                return
            
            current_words.remove(word)
            await save_filter_words(guild_id, current_words)
            await interaction.response.send_message(
                f"✅ Removed `{word}` from the filter!", ephemeral=True
            )
            
            # Attempt to update automod rule if present
            try:
                existing_rule_id = await load_automod_rule_id(guild_id)
                log_channel_id, _ = await load_config(guild_id)
                alert_channel = int(log_channel_id) if log_channel_id else None
                
                if existing_rule_id:
                    updated = await self._update_automod_rule_keywords(
                        interaction.guild, existing_rule_id, current_words, alert_channel
                    )
                    if updated:
                        await interaction.followup.send("ℹ️ AutoMod rule was updated to remove the word.", ephemeral=True)
            except Exception as e:
                print(f"[ERROR] updating automod after filter remove: {e}")

        elif action == "reset":
            old_words = await load_filter_words(guild_id)
            old_count = len(old_words)
            
            await reset_filter_words(guild_id)
            new_words = await load_filter_words(guild_id)
            new_count = len(new_words)
            
            embed = discord.Embed(
                title="🔄 Filter Reset",
                description="Chat filter has been reset to default settings",
                color=0xFF0000,
            )
            embed.add_field(name="Previous Word Count", value=str(old_count), inline=True)
            embed.add_field(name="New Word Count", value=str(new_count), inline=True)
            embed.add_field(name="Status", value="Enabled", inline=True)
            embed.set_footer(text=f"Reset by {interaction.user.name}")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
            await set_filter_enabled(guild_id, True)
            current_words = await load_filter_words(guild_id)
            
            # Attempt to update/delete any stored AutoMod rule to reflect the reset
            try:
                existing_rule_id = await load_automod_rule_id(guild_id)
                log_channel_id, _ = await load_config(guild_id)
                alert_channel = int(log_channel_id) if log_channel_id else None
                
                if existing_rule_id:
                    updated = await self._update_automod_rule_keywords(
                        interaction.guild, existing_rule_id, current_words, alert_channel
                    )
                    if updated:
                        await send_mod_log(
                            interaction.guild, "✅ AutoMod Updated",
                            f"AutoMod rule updated after filter reset; rule now has {len(current_words)} keywords.",
                            0x00FF00,
                        )
            except Exception as e:
                print(f"[ERROR] updating automod after filter reset (slash): {e}")

        elif action == "status":
            current_words = await load_filter_words(guild_id)
            enabled = self._filter_cache[guild_id][0]
            embed = discord.Embed(
                title="Chat Filter Status", color=0x00FF00 if enabled else 0xFF9900
            )
            embed.add_field(
                name="Status", value="Enabled" if enabled else "Disabled", inline=True
            )
            embed.add_field(
                name="Filtered Words", value=str(len(current_words)), inline=True
            )
            embed.add_field(
                name="Using Default Words",
                value=(
                    "✅ Yes" if current_words == DEFAULT_FILTER_WORDS else "❌ No (Custom)"
                ),
                inline=True,
            )
            embed.set_footer(text=f"Requested by {interaction.user.name}")
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    # ===== Filter Commands (Prefix) =====
    
    @commands.group(name="filter", invoke_without_command=True)
    @commands.has_permissions(manage_messages=True)
    async def filter_cmd(self, ctx):
        """Manage the chat filter (prefix command)"""
        await ctx.send("Usage: `bread filter add <word>`, `bread filter remove <word>`, `bread filter reset`, `bread filter status`")
    
    @filter_cmd.command(name="add")
    @commands.has_permissions(manage_messages=True)
    async def filter_add(self, ctx, word: str):
        """Add a word to the chat filter"""
        guild_id = ctx.guild.id
        
        word = word.lower()
        current_words = await load_filter_words(guild_id)
        
        if word in current_words:
            await ctx.send(f"❌ `{word}` is already in the filter!")
            return
        
        current_words.append(word)
        await save_filter_words(guild_id, current_words)
        await ctx.send(f"✅ Added `{word}` to the filter!")
        
        # Attempt to update automod rule if present
        try:
            existing_rule_id = await load_automod_rule_id(guild_id)
            log_channel_id, _ = await load_config(guild_id)
            alert_channel = int(log_channel_id) if log_channel_id else None
            
            if existing_rule_id:
                updated = await self._update_automod_rule_keywords(
                    ctx.guild, existing_rule_id, current_words, alert_channel
                )
                if updated:
                    await ctx.send("ℹ️ AutoMod rule was updated to add the word.")
        except Exception as e:
            print(f"[ERROR] updating automod after filter add (prefix): {e}")
    
    @filter_cmd.command(name="remove")
    @commands.has_permissions(manage_messages=True)
    async def filter_remove(self, ctx, word: str):
        """Remove a word from the chat filter"""
        guild_id = ctx.guild.id
        
        word = word.lower()
        current_words = await load_filter_words(guild_id)
        
        if word not in current_words:
            await ctx.send(f"❌ `{word}` is not in the filter!")
            return
        
        current_words.remove(word)
        await save_filter_words(guild_id, current_words)
        await ctx.send(f"✅ Removed `{word}` from the filter!")
        
        # Attempt to update automod rule if present
        try:
            existing_rule_id = await load_automod_rule_id(guild_id)
            log_channel_id, _ = await load_config(guild_id)
            alert_channel = int(log_channel_id) if log_channel_id else None
            
            if existing_rule_id:
                updated = await self._update_automod_rule_keywords(
                    ctx.guild, existing_rule_id, current_words, alert_channel
                )
                if updated:
                    await ctx.send("ℹ️ AutoMod rule was updated to remove the word.")
        except Exception as e:
            print(f"[ERROR] updating automod after filter remove (prefix): {e}")
    
    @filter_cmd.command(name="reset")
    @commands.has_permissions(manage_messages=True)
    async def filter_reset(self, ctx):
        """Reset filter words to defaults"""
        guild_id = ctx.guild.id
        
        old_words = await load_filter_words(guild_id)
        old_count = len(old_words)
        
        await reset_filter_words(guild_id)
        new_words = await load_filter_words(guild_id)
        new_count = len(new_words)
        
        embed = discord.Embed(
            title="🔄 Filter Reset",
            description="Chat filter has been reset to default settings",
            color=0xFF0000,
        )
        embed.add_field(name="Previous Word Count", value=str(old_count), inline=True)
        embed.add_field(name="New Word Count", value=str(new_count), inline=True)
        embed.add_field(name="Status", value="Enabled", inline=True)
        embed.set_footer(text=f"Reset by {ctx.author}")
        await ctx.send(embed=embed)
        
        await set_filter_enabled(guild_id, True)
        current_words = await load_filter_words(guild_id)
        
        # Attempt to update/delete any stored AutoMod rule to reflect the reset
        try:
            existing_rule_id = await load_automod_rule_id(guild_id)
            log_channel_id, _ = await load_config(guild_id)
            alert_channel = int(log_channel_id) if log_channel_id else None
            
            if existing_rule_id:
                updated = await self._update_automod_rule_keywords(
                    ctx.guild, existing_rule_id, new_words, alert_channel
                )
                if updated:
                    await ctx.send("ℹ️ AutoMod rule was updated to reflect the reset.")
        except Exception as e:
            print(f"[ERROR] updating automod after filter reset (prefix): {e}")
    
    @filter_cmd.command(name="status")
    @commands.has_permissions(manage_messages=True)
    async def filter_status(self, ctx):
        """Show chat filter status"""
        guild_id = ctx.guild.id
        current_words = await load_filter_words(guild_id)
        enabled = self._filter_cache[guild_id][0]
        
        embed = discord.Embed(
            title="Chat Filter Status", color=0x00FF00 if enabled else 0xFF9900
        )
        embed.add_field(
            name="Status", value="Enabled" if enabled else "Disabled", inline=True
        )
        embed.add_field(
            name="Filtered Words", value=str(len(current_words)), inline=True
        )
        embed.add_field(
            name="Using Default Words",
            value=(
                "✅ Yes" if current_words == DEFAULT_FILTER_WORDS else "❌ No (Custom)"
            ),
            inline=True,
        )
        embed.set_footer(text=f"Requested by {ctx.author}")
        await ctx.send(embed=embed)
    
    @filter_cmd.command(name="list")
    @commands.has_permissions(manage_messages=True)
    async def filter_list(self, ctx):
        """List all filtered words"""
        guild_id = ctx.guild.id
        current_words = await load_filter_words(guild_id)
        
        if not current_words:
            embed = discord.Embed(
                title="📋 Chat Filter List",
                description="No words are currently being filtered.",
                color=0x808080,
            )
        else:
            chunk_size = 20
            chunks = [
                current_words[i : i + chunk_size]
                for i in range(0, len(current_words), chunk_size)
            ]
            
            embeds = []
            for i, chunk in enumerate(chunks):
                embed = discord.Embed(
                    title="📋 Chat Filter List",
                    description=f"Words {i * chunk_size + 1}-{min((i + 1) * chunk_size, len(current_words))} of {len(current_words)}",
                    color=0x3498DB,
                )
                embed.add_field(
                    name="Filtered Words",
                    value=", ".join(f"`{w}`" for w in chunk),
                    inline=False,
                )
                embed.add_field(
                    name="Using Default Words",
                    value=(
                        "✅ Yes" if current_words == DEFAULT_FILTER_WORDS else "❌ No (Custom)"
                    ),
                    inline=True,
                )
                embeds.append(embed)
            
            for embed in embeds:
                await ctx.send(embed=embed)
    
    @filter_cmd.command(name="enable")
    @commands.has_permissions(manage_messages=True)
    async def filter_enable(self, ctx):
        """Enable the chat filter"""
        guild_id = ctx.guild.id
        await set_filter_enabled(guild_id, True)
        current_words = await load_filter_words(guild_id)
        
        embed = discord.Embed(
            title="✅ Filter Enabled",
            description="Chat filter has been enabled for this server.",
            color=0x00FF00,
        )
        embed.add_field(
            name="Filtered Words", value=str(len(current_words)), inline=True
        )
        embed.set_footer(text=f"Enabled by {ctx.author}")
        await ctx.send(embed=embed)
        
        # Attempt to create/update AutoMod rule
        try:
            log_channel_id, _ = await load_config(guild_id)
            alert_channel = int(log_channel_id) if log_channel_id else None
            
            if current_words:
                rule_id = await self._create_automod_rule(ctx.guild, current_words, alert_channel)
                if rule_id:
                    await save_automod_rule_id(guild_id, str(rule_id))
                    await ctx.send("ℹ️ AutoMod rule created and enabled.")
        except Exception as e:
            print(f"[ERROR] creating automod after filter enable: {e}")
    
    @filter_cmd.command(name="disable")
    @commands.has_permissions(manage_messages=True)
    async def filter_disable(self, ctx):
        """Disable the chat filter"""
        guild_id = ctx.guild.id
        await set_filter_enabled(guild_id, False)
        current_words = await load_filter_words(guild_id)
        
        embed_disabled = discord.Embed(
            title="⚠ Filter Disabled",
            description="Chat filter has been disabled for this server",
            color=0xFF9900,
        )
        embed_disabled.add_field(
            name="Filtered Words", value=str(len(current_words)), inline=True
        )
        embed_disabled.add_field(
            name="Note", value="Words are still saved, just not active", inline=False
        )
        embed_disabled.set_footer(text=f"Disabled by {ctx.author}")
        await ctx.send(embed=embed_disabled)
        
        # Attempt to delete AutoMod rule if present
        try:
            existing_rule_id = await load_automod_rule_id(guild_id)
            if existing_rule_id:
                ok = await self._delete_automod_rule(ctx.guild, existing_rule_id)
                if ok:
                    await save_automod_rule_id(guild_id, None)
                    await ctx.send("ℹ️ AutoMod rule was deleted.")
        except Exception as e:
            print(f"[ERROR] deleting automod after filter disable: {e}")
    
    # ===== Set Channel Commands =====
    
    @app_commands.command(name="setlog", description="Set the log channel for moderation logs")
    @app_commands.describe(channel="The channel to use for moderation logs")
    @app_commands.default_permissions(administrator=True)
    async def set_log_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Set the log channel for new members (slash command)"""
        global LOG_CHANNEL_ID
        try:
            _, current_welcome = await load_config(interaction.guild.id)

            await save_config(
                guild_id=interaction.guild.id,
                log_channel=channel.id,
                welcome_channel=current_welcome,  # Keep existing welcome channel
            )
            LOG_CHANNEL_ID = channel.id

            await interaction.response.send_message(
                f"✅ Log channel set to {channel.mention}", ephemeral=True
            )

            try:
                await send_mod_log(
                    guild=interaction.guild,
                    title="🔧 Log Channel Set",
                    description="Moderation logs will now be sent to this channel.",
                    color=0x00FF00,
                    fields=[
                        ("Channel", channel.mention, True),
                        ("Moderator", interaction.user.mention, True),
                    ],
                )
            except Exception:
                pass
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e!s}", ephemeral=True)

    @app_commands.command(name="setwelcome", description="Set the welcome channel for new members")
    @app_commands.describe(channel="The channel to use for welcome messages")
    @app_commands.default_permissions(administrator=True)
    async def set_welcome_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Set the welcome channel for new members (slash command)"""
        global WELCOME_CHANNEL_ID
        try:
            await save_config(guild_id=interaction.guild.id, welcome_channel=channel.id)
        except Exception:
            pass

        WELCOME_CHANNEL_ID = channel.id
        await interaction.response.send_message(
            f"✅ Welcome channel set to {channel.mention}", ephemeral=True
        )

        try:
            await send_mod_log(
                guild=interaction.guild,
                title="🎉 Welcome Channel Set",
                description=f"Welcome channel set to {channel.mention} by {interaction.user.mention}",
                color=0x00FF00,
                fields=[
                    ("Channel", channel.mention, True),
                    ("Moderator", interaction.user.mention, True),
                ],
            )
        except Exception:
            pass

    @commands.command(name="setlog")
    @commands.has_permissions(administrator=True)
    async def setlog_cmd(self, ctx, channel: discord.TextChannel):
        """Set the log channel (prefix command)"""
        global LOG_CHANNEL_ID
        try:
            _, current_welcome = await load_config(ctx.guild.id)

            await save_config(
                guild_id=ctx.guild.id,
                log_channel=channel.id,
                welcome_channel=current_welcome,
            )
            LOG_CHANNEL_ID = channel.id

            await ctx.send(f"✅ Log channel set to {channel.mention}")
        except Exception as e:
            await ctx.send(f"❌ Error: {e!s}")

    @commands.command(name="setwelcome")
    @commands.has_permissions(administrator=True)
    async def setwelcome_cmd(self, ctx, channel: discord.TextChannel):
        """Set the welcome channel (prefix command)"""
        global WELCOME_CHANNEL_ID
        try:
            await save_config(guild_id=ctx.guild.id, welcome_channel=channel.id)
        except Exception:
            pass

        WELCOME_CHANNEL_ID = channel.id
        await ctx.send(f"✅ Welcome channel set to {channel.mention}")

    @commands.command(name="getchannels")
    @commands.has_permissions(administrator=True)
    async def getchannels(self, ctx):
        """Show the current channel configuration (prefix command)"""
        try:
            log_channel_id, welcome_channel_id = await load_config(ctx.guild.id)

            embed = discord.Embed(
                title="Channel Configuration",
                description=f"Current channel settings for {ctx.guild.name}",
                color=discord.Color.blue(),
            )

            embed.add_field(
                name="Log Channel",
                value=f"<#{log_channel_id}>" if log_channel_id else "Not set",
                inline=False,
            )

            embed.add_field(
                name="Welcome Channel",
                value=f"<#{welcome_channel_id}>" if welcome_channel_id else "Not set",
                inline=False,
            )

            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f"❌ Error: {e!s}")

    @app_commands.command(name="get_channels", description="Show the current channel configuration")
    @app_commands.default_permissions(administrator=True)
    async def get_channels(self, interaction: discord.Interaction):
        """Show the current channel configuration for this server"""
        try:
            log_channel_id, welcome_channel_id = await load_config(interaction.guild_id)

            embed = discord.Embed(
                title="Channel Configuration",
                description=f"Current channel settings for {interaction.guild.name}",
                color=discord.Color.blue(),
            )
            embed.add_field(
                name="Log Channel",
                value=f"<#{log_channel_id}>" if log_channel_id else "Not set",
                inline=False,
            )
            embed.add_field(
                name="Welcome Channel",
                value=f"<#{welcome_channel_id}>" if welcome_channel_id else "Not set",
                inline=False,
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e!s}", ephemeral=True)
    
    # ===== AutoMod Helper Methods =====
    
    async def _create_automod_rule(self, guild: discord.Guild, keywords: list, alert_channel_id: int | None):
        """Create a minimal automod rule via Discord REST. Returns rule id or None."""
        if not keywords:
            return None

        payload = {
            "name": "Bread Bot - AutoMod Filter",
            "event_type": 1,  # MESSAGE_SEND
            "trigger_type": 1,  # KEYWORD
            "trigger_metadata": {"keyword_filter": keywords},
            "actions": [
                {"type": 1},  # BLOCK_MESSAGE
            ],
            "enabled": True,
        }

        # Add alert action if channel is provided
        if alert_channel_id:
            payload["actions"].append({"type": 4, "metadata": {"channel_id": str(alert_channel_id)}})

        try:
            url = f"https://discord.com/api/v10/guilds/{guild.id}/auto-moderation/rules"
            headers = {"Authorization": f"Bot {self.bot.http.token}", "Content-Type": "application/json"}
            async with self.bot.aiohttp_session.post(url, json=payload, headers=headers) as r:
                if r.status in (200, 201):
                    data = await r.json()
                    return data.get("id")
                else:
                    # Try to parse JSON error body
                    try:
                        err_data = await r.json()
                    except Exception:
                        err_data = None
                    
                    # Log the original error body
                    try:
                        txt = await r.text()
                    except Exception:
                        txt = str(err_data)
                    print(f"AutoMod create failed: {r.status} {txt}")
                    
                    # Detect AUTO_MODERATION_ACTION_TYPE_DISALLOWED
                    def _contains_disallowed(obj):
                        if isinstance(obj, dict):
                            for k, v in obj.items():
                                if _contains_disallowed(v):
                                    return True
                            return False
                        if isinstance(obj, list):
                            for item in obj:
                                if _contains_disallowed(item):
                                    return True
                            return False
                        if isinstance(obj, str):
                            return "AUTO_MODERATION_ACTION_TYPE_DISALLOWED" in obj
                        return False

                    if err_data and _contains_disallowed(err_data):
                        print("AutoMod create failed due to disallowed action type; retrying without alert action...")
                        # Retry without the alert action (keep only BLOCK_MESSAGE)
                        payload_no_alert = {
                            "name": payload.get("name"),
                            "event_type": payload.get("event_type"),
                            "trigger_type": payload.get("trigger_type"),
                            "trigger_metadata": payload.get("trigger_metadata"),
                            "actions": [{"type": 1}],
                            "enabled": payload.get("enabled", True),
                        }
                        async with self.bot.aiohttp_session.post(url, json=payload_no_alert, headers=headers) as r2:
                            if r2.status in (200, 201):
                                data2 = await r2.json()
                                print("AutoMod created without alert action (fallback)")
                                return data2.get("id")
                            else:
                                try:
                                    t2 = await r2.text()
                                except Exception:
                                    t2 = None
                                print(f"AutoMod create retry (no alert) failed: {r2.status} {t2}")
                                return None

                    return None
        except Exception as e:
            print(f"Error creating automod rule: {e}")
            return None

    async def _delete_automod_rule(self, guild: discord.Guild, rule_id: str):
        """Delete an AutoMod rule via Discord REST. Returns True on success."""
        try:
            url = f"https://discord.com/api/v10/guilds/{guild.id}/auto-moderation/rules/{rule_id}"
            headers = {"Authorization": f"Bot {self.bot.http.token}"}
            async with self.bot.aiohttp_session.delete(url, headers=headers) as r:
                if r.status in (200, 204):
                    return True
                else:
                    txt = await r.text()
                    print(f"AutoMod delete failed: {r.status} {txt}")
                    return False
        except Exception as e:
            print(f"Error deleting automod rule: {e}")
            return False

    async def _update_automod_rule_keywords(self, guild: discord.Guild, rule_id: str, keywords: list, alert_channel_id: int | None = None):
        """Update an existing automod rule's keyword list. Returns True on success."""
        try:
            if not keywords:
                print("No keywords left; deleting automod rule instead of updating")
                return await self._delete_automod_rule(guild, rule_id)

            payload_base = {
                "name": "Bread Bot - AutoMod Filter",
                "event_type": 1,
                "trigger_type": 1,
                "trigger_metadata": {"keyword_filter": keywords},
                "enabled": True,
            }

            # Try to preserve the alert action if an alert_channel_id was provided
            actions_with_alert = [{"type": 1}]
            if alert_channel_id:
                actions_with_alert.append({"type": 4, "metadata": {"channel_id": str(alert_channel_id)}})

            # Attempt PATCH using discord.py http if available
            if hasattr(self.bot, "http") and hasattr(self.bot.http, "request"):
                try:
                    import discord.http
                    data_payload = dict(payload_base)
                    data_payload["actions"] = actions_with_alert if alert_channel_id else [{"type": 1}]
                    route = discord.http.Route("PATCH", "/guilds/{guild_id}/auto-moderation/rules/{rule_id}", guild_id=guild.id, rule_id=rule_id)
                    resp = await self.bot.http.request(route, json=data_payload)
                    if isinstance(resp, dict):
                        return True
                except Exception:
                    pass

            # Fallback to aiohttp
            async with self.bot.aiohttp_session as session:
                url = f"https://discord.com/api/v10/guilds/{guild.id}/auto-moderation/rules/{rule_id}"
                headers = {"Authorization": f"Bot {self.bot.http.token}", "Content-Type": "application/json"}

                # First try with alert action if provided
                first_payload = dict(payload_base)
                first_payload["actions"] = actions_with_alert if alert_channel_id else [{"type": 1}]

                async with session.patch(url, json=first_payload, headers=headers) as r:
                    if r.status in (200, 201):
                        return True
                    # parse error body
                    try:
                        err = await r.json()
                    except Exception:
                        err = None
                    txt = await r.text()
                    print(f"AutoMod update failed: {r.status} {txt}")

                    # detect disallowed action type and retry without alert action
                    def _contains_disallowed(obj):
                        if isinstance(obj, dict):
                            for k, v in obj.items():
                                if _contains_disallowed(v):
                                    return True
                            return False
                        if isinstance(obj, list):
                            for item in obj:
                                if _contains_disallowed(item):
                                    return True
                            return False
                        if isinstance(obj, str):
                            return "AUTO_MODERATION_ACTION_TYPE_DISALLOWED" in obj
                        return False

                    if err and _contains_disallowed(err):
                        print("AutoMod update: alert action disallowed, retrying with block-only actions...")
                        payload_block_only = dict(payload_base)
                        payload_block_only["actions"] = [{"type": 1}]
                        async with session.patch(url, json=payload_block_only, headers=headers) as r2:
                            if r2.status in (200, 201):
                                print("AutoMod updated successfully with block-only actions")
                                return True
                            else:
                                t2 = await r2.text()
                                print(f"AutoMod update (block-only) failed: {r2.status} {t2}")
                                return False

                    return False
        except Exception as e:
            print(f"Error updating automod rule: {e}")
            return False


async def setup(bot):
    """Add the cog to the bot"""
    await bot.add_cog(Admin(bot))
