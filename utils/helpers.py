"""
Helper functions and utilities
"""
import discord
import datetime
from datetime import timezone
from config import GLOBAL_BLACKLIST, BLACKLIST_BLOCK_MESSAGE
from utils.database import guild_blacklist_collection, warnings_collection, scheduled_invites_collection, moderation_cases_collection


async def add_guild_blacklist(guild_id: int, user_id: int):
    """Add a user to the guild blacklist"""
    try:
        await guild_blacklist_collection.update_one(
            {"guild_id": int(guild_id)},
            {"$addToSet": {"user_ids": int(user_id)}},
            upsert=True,
        )
        return True
    except Exception as e:
        print(f"[ERROR] add_guild_blacklist: {e}")
        return False


async def remove_guild_blacklist(guild_id: int, user_id: int):
    """Remove a user from the guild blacklist"""
    try:
        await guild_blacklist_collection.update_one(
            {"guild_id": int(guild_id)}, {"$pull": {"user_ids": int(user_id)}}
        )
        return True
    except Exception as e:
        print(f"[ERROR] remove_guild_blacklist: {e}")
        return False


async def get_guild_blacklist(guild_id: int):
    """Get all blacklisted users for a guild"""
    try:
        doc = await guild_blacklist_collection.find_one({"guild_id": int(guild_id)})
        if doc and "user_ids" in doc:
            return [int(u) for u in doc.get("user_ids", [])]
        return []
    except Exception as e:
        print(f"[ERROR] get_guild_blacklist: {e}")
        return []


async def is_user_blocked(guild_id: int, user_id: int):
    """Check if a user is blocked (global or guild blacklist)"""
    if int(user_id) in GLOBAL_BLACKLIST:
        return True
    try:
        blacklist = await get_guild_blacklist(guild_id)
        return int(user_id) in blacklist
    except Exception:
        return False


async def get_member_warnings(guild_id, user_id):
    """Get all warnings for a member"""
    cursor = warnings_collection.find({"guild_id": guild_id, "user_id": user_id}).sort("created_at", 1)
    warnings = await cursor.to_list(length=None)
    for i, warning in enumerate(warnings):
        warning['warning_number'] = i + 1
    return warnings


async def send_mod_log(guild, title, description, color, fields=None, thumbnail=None):
    """Send a moderation log message to the configured log channel"""
    from utils.config_manager import load_config  # Import here to avoid circular dependency
    try:
        log_channel_id, _ = await load_config(guild.id)
        if not log_channel_id:
            return
        
        channel = guild.get_channel(int(log_channel_id))
        if not channel:
            return
        
        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=discord.utils.utcnow()
        )
        
        if fields:
            for name, value, inline in fields:
                embed.add_field(name=name, value=value, inline=inline)
        
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
        
        await channel.send(embed=embed)
    except Exception as e:
        print(f"[ERROR] send_mod_log: {e}")


async def _queue_rejoin_invite(guild, user_id, days, reason):
    """Queue a rejoin invite to be sent after a timeout"""
    await scheduled_invites_collection.update_one(
        {"guild_id": guild.id, "user_id": user_id, "status": "pending"},
        {"$set": {
            "guild_id": guild.id, "user_id": user_id, "reason": reason,
            "send_at": discord.utils.utcnow() + datetime.timedelta(days=days),
            "status": "pending", "created_at": discord.utils.utcnow(),
        }}, upsert=True,
    )


async def log_moderation_case(guild, member, moderator, action, reason, evidence, duration_label=None, dm_sent=False):
    """Log a moderation case to the database"""
    await moderation_cases_collection.insert_one({
        "guild_id": guild.id, "user_id": member.id, "moderator_id": moderator.id,
        "action": action, "reason": reason, "evidence": evidence,
        "duration": duration_label, "created_at": discord.utils.utcnow(),
    })
    
    past_tense = {"ban": "banned", "kick": "kicked", "timeout": "timed out"}.get(action, action)
    await send_mod_log(guild, f"{action.title()} issued", f"{member.mention} was {past_tense}.", 0xE74C3C,
        [("Moderator", moderator.mention, True), ("Reason", reason, False),
         ("Evidence", evidence, False), ("Duration", duration_label, True),
         ("DM delivered", "Yes" if dm_sent else "No / not required", True)],
        member.display_avatar.url)
