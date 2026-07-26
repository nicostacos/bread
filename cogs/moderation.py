"""
Moderation commands for Bread Bot
"""
import discord
from discord import app_commands
from discord.ext import commands
import datetime
import random
import re
import asyncio

from config import DEFAULT_FILTER_WORDS, GLOBAL_BLACKLIST, BLACKLIST_BLOCK_MESSAGE
from utils.config_manager import (
    save_config, load_config, save_filter_words, load_filter_words,
    reset_filter_words, set_filter_enabled, get_filter_cache, save_automod_rule_id, load_automod_rule_id
)
from utils.helpers import (
    is_user_blocked, add_guild_blacklist, remove_guild_blacklist, get_guild_blacklist,
    send_mod_log, _queue_rejoin_invite, get_member_warnings
)
from utils.database import warnings_collection, moderation_cases_collection, filter_collection


class Moderation(commands.Cog):
    """Moderation commands"""
    
    def __init__(self, bot):
        self.bot = bot
        self._filter_cache = get_filter_cache()
    
    # ===== Kick Commands =====
    
    @commands.command()
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason="No reason provided"):
        """Kick a member from the server (prefix command)"""
        await ctx.send("Use `/kick` so the required reason and evidence form is recorded.")
        return
    
    @app_commands.command(name="kick", description="Kick a member from the server")
    @app_commands.describe(
        member="The member to kick",
        reason="Reason for kicking",
        evidence="Evidence (optional)"
    )
    @app_commands.default_permissions(kick_members=True)
    async def slash_kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided", evidence: str = ""):
        """Kick a member from the server (slash command)"""
        if not interaction.user.guild_permissions.kick_members:
            await interaction.response.send_message(
                "❌ You need Kick members permissions to use this command!", ephemeral=True
            )
            return

        if not interaction.guild.me.guild_permissions.kick_members:
            await interaction.response.send_message(
                "❌ I don't have permission to kick members!", ephemeral=True
            )
            return

        if member == interaction.user:
            await interaction.response.send_message(
                "❌ You can't kick yourself!", ephemeral=True
            )
            return

        if member == interaction.guild.me:
            await interaction.response.send_message(
                "❌ You can't kick me!", ephemeral=True
            )
            return

        if member.top_role >= interaction.user.top_role:
            await interaction.response.send_message(
                "❌ You can't kick someone with equal or higher roles!", ephemeral=True
            )
            return

        try:
            try:
                await member.send(
                    f"You have been kicked from **{interaction.guild.name}**\nReason: {reason}"
                )
                dm_sent = True
            except:
                dm_sent = False

            await member.kick(reason=f"{reason} (kicked by {interaction.user})")

            await interaction.response.send_message(
                f"✅ {member.mention} has been kicked!\nReason: {reason}"
            )

            await send_mod_log(
                guild=interaction.guild,
                title="👢 Member Kicked",
                description=f"{member.mention} has been kicked from the server.",
                color=0xFF9900,
                fields=[
                    ("User", f"{member} ({member.id})", False),
                    ("Moderator", interaction.user.mention, True),
                    ("Reason", reason, True),
                    ("Evidence", evidence if evidence else "None", False),
                    ("Account Created", discord.utils.format_dt(member.created_at, "R"), True),
                ],
                thumbnail=member.avatar.url if member.avatar else None,
            )

        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permission to kick this member!", ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ An error occurred: {e}", ephemeral=True
            )
    
    # ===== Ban Commands =====
    
    @app_commands.command(name="ban", description="Ban a member from the server")
    @app_commands.describe(
        member="The member to ban",
        reason="Reason for banning",
        evidence="Evidence (optional)"
    )
    @app_commands.default_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided", evidence: str = ""):
        if not interaction.user.guild_permissions.ban_members:
            await interaction.response.send_message(
                "❌ You need Ban members permissions to use this command!", ephemeral=True
            )
            return

        if not interaction.guild.me.guild_permissions.ban_members:
            await interaction.response.send_message(
                "❌ I don't have permission to ban members!", ephemeral=True
            )
            return

        if member == interaction.user:
            await interaction.response.send_message(
                "❌ You can't ban yourself!", ephemeral=True
            )
            return

        if member == interaction.guild.me:
            await interaction.response.send_message(
                "❌ I can't ban myself!", ephemeral=True
            )
            return

        if member.top_role >= interaction.user.top_role:
            await interaction.response.send_message(
                "❌ You can't ban someone with equal or higher roles!", ephemeral=True
            )
            return

        try:
            await member.ban(reason=reason)
            await interaction.response.send_message(
                f"✅ {member.mention} has been banned!\nReason: {reason}"
            )

            try:
                await send_mod_log(
                    guild=interaction.guild,
                    title="🚫 Member Banned",
                    description=f"{member.mention} was banned by {interaction.user.mention}",
                    color=0xFF0000,
                    fields=[
                        ("Reason", reason, False),
                        ("Evidence", evidence if evidence else "None", False),
                        ("User ID", str(member.id), True),
                        ("Moderator", interaction.user.mention, True),
                    ],
                    thumbnail=(member.avatar.url if member.avatar else member.default_avatar.url),
                )
            except Exception:
                pass

        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permission to ban this member!", ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ An error occurred: {e}", ephemeral=True
            )
    
    # ===== Unban Command =====
    
    @app_commands.command(name="unban", description="Unban a member from the server")
    @app_commands.describe(
        user="The user to unban",
        reason="Reason for unbanning"
    )
    @app_commands.default_permissions(ban_members=True)
    async def unban(self, interaction: discord.Interaction, user: discord.User, reason: str = "No reason provided"):
        if not interaction.user.guild_permissions.ban_members:
            await interaction.response.send_message(
                "❌ You need mod permissions to use this command!", ephemeral=True
            )
            return

        if not interaction.guild.me.guild_permissions.ban_members:
            await interaction.response.send_message(
                "❌ I don't have permission to unban members!", ephemeral=True
            )
            return

        try:
            await interaction.guild.unban(user, reason=reason)
            await interaction.response.send_message(
                f"✅ {user.name} has been unbanned!\nReason: {reason}"
            )
            try:
                await send_mod_log(
                    guild=interaction.guild,
                    title="🔓 Member Unbanned",
                    description=f"{user.mention} was unbanned by {interaction.user.mention}",
                    color=0x00FF00,
                    fields=[
                        ("User", f"{user} ({user.id})", False),
                        ("Moderator", interaction.user.mention, True),
                        ("Reason", reason, True),
                    ],
                )
            except Exception:
                pass
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permission to unban this user!", ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ An error occurred: {e}", ephemeral=True
            )
    
    # ===== Unkick Command =====
    
    @app_commands.command(name="unkick", description="Send a kicked user a new server invite")
    @app_commands.describe(
        user="Kicked user to invite back",
        reason="Reason for inviting them back"
    )
    @app_commands.default_permissions(kick_members=True)
    async def unkick(self, interaction: discord.Interaction, user: discord.User, reason: str):
        """A kick cannot be reversed; this sends the user a new one-use invite."""
        if not interaction.user.guild_permissions.kick_members:
            await interaction.response.send_message("❌ Kick Members permission is required.", ephemeral=True)
            return
        if interaction.guild.get_member(user.id):
            await interaction.response.send_message("❌ That user is already in the server.", ephemeral=True)
            return
        channel = next(
            (channel for channel in interaction.guild.text_channels
             if channel.permissions_for(interaction.guild.me).create_instant_invite),
            None,
        )
        if not channel:
            await interaction.response.send_message("❌ I need Create Invite permission in at least one text channel.", ephemeral=True)
            return
        try:
            invite = await channel.create_invite(max_age=604800, max_uses=1, reason=f"Unkick by {interaction.user}: {reason}")
            await user.send(f"You have been invited back to **{interaction.guild.name}**.\nReason: {reason}\n{invite.url}")
            await send_mod_log(interaction.guild, "Rejoin invite sent", f"A moderator sent {user.mention} a new invite.", 0x2ECC71,
                [("Moderator", interaction.user.mention, True), ("Reason", reason, False)])
            await interaction.response.send_message(f"✅ A rejoin invite was sent to {user.mention}.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I could not create the invite or DM that user.", ephemeral=True)
        except discord.HTTPException:
            await interaction.response.send_message("❌ Discord could not send that rejoin invite.", ephemeral=True)
    
    # ===== Mute/Timeout Commands =====
    
    @app_commands.command(name="mute", description="Timeout a member for a specified duration")
    @app_commands.describe(
        member="The member to mute",
        duration="Duration in minutes (default: 10)",
        reason="Reason for muting",
        evidence="Evidence (optional)"
    )
    @app_commands.default_permissions(moderate_members=True)
    async def mute(self, interaction: discord.Interaction, member: discord.Member, duration: int = 10, reason: str = "No reason provided", evidence: str = ""):
        if not interaction.user.guild_permissions.moderate_members:
            await interaction.response.send_message(
                "❌ You need moderate members permissions to use this command!",
                ephemeral=True,
            )
            return

        if not interaction.guild.me.guild_permissions.moderate_members:
            await interaction.response.send_message(
                "❌ I don't have permission to timeout members!", ephemeral=True
            )
            return

        if member == interaction.user:
            await interaction.response.send_message(
                "❌ You can't mute yourself!", ephemeral=True
            )
            return

        if member == interaction.guild.me:
            await interaction.response.send_message(
                "❌ I can't mute myself!", ephemeral=True
            )
            return

        if member.top_role >= interaction.user.top_role:
            await interaction.response.send_message(
                "❌ You can't mute someone with equal or higher roles!", ephemeral=True
            )
            return

        if duration > 40320:  # 28 days in minutes
            await interaction.response.send_message(
                "❌ Maximum mute duration is 28 days (40320 minutes)!", ephemeral=True
            )
            return

        try:
            timeout_duration = discord.utils.utcnow() + datetime.timedelta(minutes=duration)

            await member.timeout(timeout_duration, reason=reason)
            await interaction.response.send_message(
                f"✅ {member.mention} has been muted for {duration} minutes!\nReason: {reason}"
            )
            try:
                await send_mod_log(
                    guild=interaction.guild,
                    title="🔇 Member Muted",
                    description=f"{member.mention} has been muted for {duration} minutes.",
                    color=0xFFA500,
                    fields=[
                        ("User", f"{member} ({member.id})", False),
                        ("Moderator", interaction.user.mention, True),
                        ("Duration", f"{duration} minutes", True),
                        ("Reason", reason, True),
                        ("Evidence", evidence if evidence else "None", False),
                        ("Muted Until", discord.utils.format_dt(timeout_duration, "R"), True),
                    ],
                    thumbnail=member.avatar.url if member.avatar else None,
                )
            except Exception:
                pass
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permission to timeout this member!", ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ An error occurred: {e}", ephemeral=True
            )
    
    # ===== Purge Command =====
    
    @app_commands.command(name="purge", description="Purge messages from a channel")
    @app_commands.describe(limit="Number of messages to purge")
    @app_commands.default_permissions(manage_messages=True)
    async def purge(self, interaction: discord.Interaction, limit: int = 100):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message(
                "You cannot purge message as per your roles.", ephemeral=False
            )
            return

        if not interaction.guild.me.guild_permissions.manage_messages:
            await interaction.response.send_message(
                "❌ I don't have permission to manage messages!", ephemeral=True
            )
            return

        if limit > 2000:
            await interaction.response.send_message(
                "❌ Maximum purge limit is 2000 messages!", ephemeral=True
            )
            return

        try:
            await interaction.channel.purge(limit=limit)
            await interaction.response.send_message(
                f"✅ Purged {limit} messages!", ephemeral=True
            )
            try:
                await send_mod_log(
                    guild=interaction.guild,
                    title="🗑️ Messages Purged",
                    description=f"{limit} messages were purged in {interaction.channel.mention}.",
                    color=0x3498DB,
                    fields=[
                        ("Channel", interaction.channel.mention, True),
                        ("Moderator", interaction.user.mention, True),
                        ("Message Count", str(limit), True),
                    ],
                )
            except Exception:
                pass
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permission to manage messages!", ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ An error occurred: {e}", ephemeral=True
            )
    
    # ===== Broadcast Command =====
    
    @app_commands.command(name="broadcast", description="Broadcast a message to all channels")
    @app_commands.describe(
        message="The message to broadcast",
        ping_everyone="Whether to ping @everyone"
    )
    @app_commands.default_permissions(administrator=True)
    async def broadcast(self, interaction: discord.Interaction, message: str, ping_everyone: bool = False):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "No one wants to hear you talking", ephemeral=False
            )
            return

        if not interaction.guild.me.guild_permissions.send_messages:
            await interaction.response.send_message(
                "❌ I don't have permission to send messages!", ephemeral=True
            )
            return

        try:
            channel_count = 0
            for channel in interaction.guild.text_channels:
                if channel.permissions_for(interaction.guild.me).send_messages:
                    try:
                        content = message
                        if ping_everyone:
                            content = "@everyone " + message
                        await channel.send(content)
                        channel_count += 1
                        await asyncio.sleep(0.5)  # Rate limit
                    except Exception as e:
                        print(f"[ERROR] broadcast to {channel.name}: {e}")

            await interaction.response.send_message(
                f"✅ Broadcast sent to {channel_count} channels!", ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ An error occurred: {e}", ephemeral=True
            )

    # ===== Blacklist Commands =====

    @app_commands.command(name="blacklist", description="Manage the server blacklist")
    @app_commands.describe(
        action="Action to perform on the blacklist",
        user="User to add or remove from blacklist",
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="add", value="add"),
        app_commands.Choice(name="remove", value="remove"),
        app_commands.Choice(name="list", value="list"),
    ])
    @app_commands.default_permissions(administrator=True)
    async def blacklist_slash(self, interaction: discord.Interaction, action: str, user: discord.User = None):
        """Manage the server blacklist (slash command)"""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ You need Administrator permissions to use this command!", ephemeral=True
            )
            return

        if action == "add":
            if user is None:
                await interaction.response.send_message(
                    "❌ Please specify a user to add to the blacklist!", ephemeral=True
                )
                return

            if user == interaction.user:
                await interaction.response.send_message(
                    "❌ You can't blacklist yourself!", ephemeral=True
                )
                return

            if user == interaction.guild.me:
                await interaction.response.send_message(
                    "❌ I can't blacklist myself!", ephemeral=True
                )
                return

            member = interaction.guild.get_member(user.id)
            if member and member.top_role >= interaction.user.top_role:
                await interaction.response.send_message(
                    "❌ You can't blacklist someone with equal or higher roles!", ephemeral=True
                )
                return

            success = await add_guild_blacklist(interaction.guild.id, user.id)
            if success:
                await interaction.response.send_message(
                    f"✅ {user.mention} has been added to the blacklist!", ephemeral=True
                )
                await send_mod_log(
                    guild=interaction.guild,
                    title="📛 User Blacklisted",
                    description=f"{user.mention} has been added to the server blacklist.",
                    color=0xFF0000,
                    fields=[
                        ("User", f"{user} ({user.id})", False),
                        ("Moderator", interaction.user.mention, True),
                    ],
                    thumbnail=user.avatar.url if user.avatar else user.default_avatar.url,
                )
            else:
                await interaction.response.send_message(
                    f"❌ Failed to add {user.mention} to the blacklist!", ephemeral=True
                )

        elif action == "remove":
            if user is None:
                await interaction.response.send_message(
                    "❌ Please specify a user to remove from the blacklist!", ephemeral=True
                )
                return

            success = await remove_guild_blacklist(interaction.guild.id, user.id)
            if success:
                await interaction.response.send_message(
                    f"✅ {user.mention} has been removed from the blacklist!", ephemeral=True
                )
                await send_mod_log(
                    guild=interaction.guild,
                    title="🗑️ User Unblacklisted",
                    description=f"{user.mention} has been removed from the server blacklist.",
                    color=0x00FF00,
                    fields=[
                        ("User", f"{user} ({user.id})", False),
                        ("Moderator", interaction.user.mention, True),
                    ],
                )
            else:
                await interaction.response.send_message(
                    f"❌ Failed to remove {user.mention} from the blacklist!", ephemeral=True
                )

        elif action == "list":
            blacklisted_users = await get_guild_blacklist(interaction.guild.id)
            if not blacklisted_users:
                await interaction.response.send_message(
                    "✅ The blacklist is currently empty.", ephemeral=True
                )
                return

            user_mentions = []
            for user_id in blacklisted_users:
                user = interaction.guild.get_member(user_id)
                if user:
                    user_mentions.append(user.mention)
                else:
                    user_mentions.append(f"<@{user_id}> (Left)")

            if len(user_mentions) <= 10:
                users_str = ", ".join(user_mentions)
                await interaction.response.send_message(
                    f"📋 **Blacklisted Users:**\n{users_str}", ephemeral=True
                )
            else:
                chunks = [user_mentions[i:i+10] for i in range(0, len(user_mentions), 10)]
                for i, chunk in enumerate(chunks):
                    users_str = ", ".join(chunk)
                    if i == 0:
                        await interaction.response.send_message(
                            f"📋 **Blacklisted Users (Part {i+1}/{len(chunks)}):**\n{users_str}", ephemeral=True
                        )
                    else:
                        await interaction.followup.send(
                            f"📋 **Blacklisted Users (Part {i+1}/{len(chunks)}):**\n{users_str}", ephemeral=True
                        )

    @commands.group(name="blacklist")
    @commands.has_permissions(administrator=True)
    async def blacklist_cmd(self, ctx):
        """Manage the server blacklist (prefix command)"""
        if ctx.invoked_subcommand is None:
            await ctx.send("Use `/blacklist` for slash commands or `bread blacklist add/remove/list`")

    @blacklist_cmd.command(name="add")
    @commands.has_permissions(administrator=True)
    async def blacklist_add(self, ctx, user: discord.User):
        """Add a user to the server blacklist"""
        if user == ctx.author:
            await ctx.send("❌ You can't blacklist yourself!")
            return

        if user == ctx.guild.me:
            await ctx.send("❌ I can't blacklist myself!")
            return

        member = ctx.guild.get_member(user.id)
        if member and member.top_role >= ctx.author.top_role:
            await ctx.send("❌ You can't blacklist someone with equal or higher roles!")
            return

        success = await add_guild_blacklist(ctx.guild.id, user.id)
        if success:
            await ctx.send(f"✅ {user.mention} has been added to the blacklist!")
            await send_mod_log(
                guild=ctx.guild,
                title="📛 User Blacklisted",
                description=f"{user.mention} has been added to the server blacklist.",
                color=0xFF0000,
                fields=[
                    ("User", f"{user} ({user.id})", False),
                    ("Moderator", ctx.author.mention, True),
                ],
                thumbnail=user.avatar.url if user.avatar else user.default_avatar.url,
            )
        else:
            await ctx.send(f"❌ Failed to add {user.mention} to the blacklist!")

    @blacklist_cmd.command(name="remove")
    @commands.has_permissions(administrator=True)
    async def blacklist_remove(self, ctx, user: discord.User):
        """Remove a user from the server blacklist"""
        success = await remove_guild_blacklist(ctx.guild.id, user.id)
        if success:
            await ctx.send(f"✅ {user.mention} has been removed from the blacklist!")
            await send_mod_log(
                guild=ctx.guild,
                title="🗑️ User Unblacklisted",
                description=f"{user.mention} has been removed from the server blacklist.",
                color=0x00FF00,
                fields=[
                    ("User", f"{user} ({user.id})", False),
                    ("Moderator", ctx.author.mention, True),
                ],
            )
        else:
            await ctx.send(f"❌ Failed to remove {user.mention} from the blacklist!")

    @blacklist_cmd.command(name="list")
    @commands.has_permissions(administrator=True)
    async def blacklist_list(self, ctx):
        """List all blacklisted users"""
        blacklisted_users = await get_guild_blacklist(ctx.guild.id)
        if not blacklisted_users:
            await ctx.send("✅ The blacklist is currently empty.")
            return

        user_mentions = []
        for user_id in blacklisted_users:
            user = ctx.guild.get_member(user_id)
            if user:
                user_mentions.append(user.mention)
            else:
                user_mentions.append(f"<@{user_id}> (Left)")

        if len(user_mentions) <= 10:
            users_str = ", ".join(user_mentions)
            await ctx.send(f"📋 **Blacklisted Users:**\n{users_str}")
        else:
            chunks = [user_mentions[i:i+10] for i in range(0, len(user_mentions), 10)]
            for i, chunk in enumerate(chunks):
                users_str = ", ".join(chunk)
                await ctx.send(f"📋 **Blacklisted Users (Part {i+1}/{len(chunks)}):**\n{users_str}")

    # ===== Warning System Commands =====

    @app_commands.command(name="warn", description="Warn a member with a reason")
    @app_commands.describe(
        member="The member to warn",
        reason="Reason for the warning",
        evidence="Evidence (optional)"
    )
    @app_commands.default_permissions(moderate_members=True)
    async def warn_slash(self, interaction: discord.Interaction, member: discord.Member, reason: str, evidence: str = ""):
        """Warn a member (slash command)"""
        if not interaction.user.guild_permissions.moderate_members:
            await interaction.response.send_message(
                "❌ You need Moderate Members permissions to use this command!", ephemeral=True
            )
            return

        if member == interaction.user:
            await interaction.response.send_message(
                "❌ You can't warn yourself!", ephemeral=True
            )
            return

        if member == interaction.guild.me:
            await interaction.response.send_message(
                "❌ I can't warn myself!", ephemeral=True
            )
            return

        if member.top_role >= interaction.user.top_role:
            await interaction.response.send_message(
                "❌ You can't warn someone with equal or higher roles!", ephemeral=True
            )
            return

        # Get existing warnings
        existing_warnings = await get_member_warnings(interaction.guild.id, member.id)
        warning_number = len(existing_warnings) + 1

        # Store the warning in the database
        await warnings_collection.insert_one({
            "guild_id": interaction.guild.id,
            "user_id": member.id,
            "moderator_id": interaction.user.id,
            "reason": reason,
            "evidence": evidence,
            "created_at": discord.utils.utcnow(),
            "warning_number": warning_number,
        })

        # Send confirmation
        await interaction.response.send_message(
            f"✅ {member.mention} has been warned! (Warning #{warning_number})\nReason: {reason}",
            ephemeral=True
        )

        # Send mod log
        try:
            await send_mod_log(
                guild=interaction.guild,
                title="⚠️ Member Warned",
                description=f"{member.mention} has received warning #{warning_number}.",
                color=0xFFA500,
                fields=[
                    ("User", f"{member} ({member.id})", False),
                    ("Moderator", interaction.user.mention, True),
                    ("Warning #", str(warning_number), True),
                    ("Reason", reason, False),
                    ("Evidence", evidence if evidence else "None", False),
                ],
                thumbnail=member.avatar.url if member.avatar else None,
            )
        except Exception:
            pass

        # Auto-escalation: 3 warnings = kick, 4 warnings = ban
        if warning_number >= 3:
            if warning_number == 3:
                # Kick the user
                try:
                    await member.kick(reason=f"Automatic kick after 3 warnings")
                    await interaction.followup.send(
                        f"⚠️ {member.mention} has been automatically kicked after 3 warnings!",
                        ephemeral=True
                    )
                    await send_mod_log(
                        guild=interaction.guild,
                        title="👢 Auto-Kick (3 Warnings)",
                        description=f"{member.mention} was automatically kicked after accumulating 3 warnings.",
                        color=0xFF9900,
                        fields=[
                            ("User", f"{member} ({member.id})", False),
                            ("Action", "Automatic Kick", True),
                        ],
                    )
                except Exception as e:
                    print(f"[ERROR] Auto-kick failed: {e}")
            elif warning_number >= 4:
                # Ban the user
                try:
                    await member.ban(reason=f"Automatic ban after 4+ warnings")
                    await interaction.followup.send(
                        f"⚠️ {member.mention} has been automatically banned after 4+ warnings!",
                        ephemeral=True
                    )
                    await send_mod_log(
                        guild=interaction.guild,
                        title="🚫 Auto-Ban (4+ Warnings)",
                        description=f"{member.mention} was automatically banned after accumulating {warning_number} warnings.",
                        color=0xFF0000,
                        fields=[
                            ("User", f"{member} ({member.id})", False),
                            ("Warning Count", str(warning_number), True),
                            ("Action", "Automatic Ban", True),
                        ],
                    )
                except Exception as e:
                    print(f"[ERROR] Auto-ban failed: {e}")

    @app_commands.command(name="warnings", description="View a member's warnings")
    @app_commands.describe(member="The member to view warnings for")
    @app_commands.default_permissions(moderate_members=True)
    async def warnings_slash(self, interaction: discord.Interaction, member: discord.Member):
        """View a member's warnings (slash command)"""
        if not interaction.user.guild_permissions.moderate_members:
            await interaction.response.send_message(
                "❌ You need Moderate Members permissions to use this command!", ephemeral=True
            )
            return

        warnings = await get_member_warnings(interaction.guild.id, member.id)

        if not warnings:
            await interaction.response.send_message(
                f"✅ {member.mention} has no warnings.", ephemeral=True
            )
            return

        # Sort by warning number
        warnings.sort(key=lambda x: x.get("warning_number", 0))

        embed = discord.Embed(
            title=f"⚠️ Warnings for {member}",
            description=f"Total warnings: {len(warnings)}",
            color=0xFFA500,
            timestamp=discord.utils.utcnow()
        )

        for warning in warnings:
            moderator = interaction.guild.get_member(warning.get("moderator_id"))
            moderator_name = moderator.mention if moderator else f"<@{warning.get('moderator_id')}>"
            reason = warning.get("reason", "No reason provided")
            evidence = warning.get("evidence", "")
            warning_num = warning.get("warning_number", 0)
            created_at = warning.get("created_at")
            if created_at:
                created_str = discord.utils.format_dt(created_at, "R")
            else:
                created_str = "Unknown"

            embed.add_field(
                name=f"Warning #{warning_num}",
                value=f"**Reason:** {reason}\n**Moderator:** {moderator_name}\n**Evidence:** {evidence if evidence else 'None'}\n**Date:** {created_str}",
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.command(name="warn")
    @commands.has_permissions(moderate_members=True)
    async def warn_cmd(self, ctx, member: discord.Member, *, reason: str):
        """Warn a member (prefix command)"""
        await ctx.send("Use `/warn` for the form with evidence field.")

    @commands.command(name="warnings")
    @commands.has_permissions(moderate_members=True)
    async def warnings_cmd(self, ctx, member: discord.Member):
        """View a member's warnings (prefix command)"""
        warnings = await get_member_warnings(ctx.guild.id, member.id)

        if not warnings:
            await ctx.send(f"✅ {member.mention} has no warnings.")
            return

        warnings.sort(key=lambda x: x.get("warning_number", 0))

        embed = discord.Embed(
            title=f"⚠️ Warnings for {member}",
            description=f"Total warnings: {len(warnings)}",
            color=0xFFA500,
            timestamp=discord.utils.utcnow()
        )

        for warning in warnings:
            moderator = ctx.guild.get_member(warning.get("moderator_id"))
            moderator_name = moderator.mention if moderator else f"<@{warning.get('moderator_id')}>"
            reason = warning.get("reason", "No reason provided")
            evidence = warning.get("evidence", "")
            warning_num = warning.get("warning_number", 0)
            created_at = warning.get("created_at")
            if created_at:
                created_str = discord.utils.format_dt(created_at, "R")
            else:
                created_str = "Unknown"

            embed.add_field(
                name=f"Warning #{warning_num}",
                value=f"**Reason:** {reason}\n**Moderator:** {moderator_name}\n**Evidence:** {evidence if evidence else 'None'}\n**Date:** {created_str}",
                inline=False
            )

        await ctx.send(embed=embed)


async def setup(bot):
    """Add the cog to the bot"""
    await bot.add_cog(Moderation(bot))
