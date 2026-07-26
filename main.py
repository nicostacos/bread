import asyncio
import datetime
import logging
import os
import random
import sys
import threading

# from webhook_utils import send_webhook_message
from datetime import timezone

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from flask import Flask

# --- MongoDB Setup

load_dotenv()

mongo_user = os.getenv("MONGO_USER")
mongo_pass = os.getenv("MONGO_PASS")
mongo_db = os.getenv("MONGO_DB")
mongo_host = os.getenv("MONGO_HOST")

mongo_uri = f"mongodb+srv://{mongo_user}:{mongo_pass}@{mongo_host}/{mongo_db}?retryWrites=true&w=majority"

client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5_000)
db = client[mongo_db]
config_collection = db[
    "server_configs"
]

try:
    db.create_collection("word_filters")
    print("✅ Created word_filters collection")
except Exception as e:
    print(f"ℹ️ word_filters collection already exists or error creating: {e}")

filter_collection = db["word_filters"]
# Moderation state is kept separately from server configuration so warning
# history and delayed re-invites survive restarts.
warnings_collection = db["moderation_warnings"]
moderation_cases_collection = db["moderation_cases"]
scheduled_invites_collection = db["scheduled_invites"]

try:
    filter_collection.create_index("guild_id", unique=True)
    print("✅ Created index on guild_id for word_filters")
except Exception as e:
    print(f"ℹ️ Could not create index (might already exist): {e}")

default_filter_words = [
    "fuck",
    "shit",
    "bitch",
    "nigger",
    "nigga",
    "niggers",
    "niggas",
    "nigguh",
    "nigguhs",
]

print("✅ Connected to MongoDB:", db.name)


def check_mongodb_connection():
    try:
        server_info = client.server_info()
        print(f"✅ MongoDB Server Version: {server_info.get('version')}")

        collections = db.list_collection_names()
        print(f"✅ Available collections: {collections}")


        print(f"✅ Server configs collection exists: {'server_configs' in collections}")
        print(f"✅ Word filters collection exists: {'word_filters' in collections}")

        if "word_filters" in collections:
            count = db.word_filters.count_documents({})
            print(f"✅ Word filters collection has {count} documents")
            if count > 0:
                print("✅ Sample document:", db.word_filters.find_one())

        return True
    except Exception as e:
        print(f"❌ MongoDB Connection Error: {e!s}")
        return False


LOG_CHANNEL_ID = None
WELCOME_CHANNEL_ID = None

# The message event runs for every message.  Cache per-guild settings so it
# does not perform a synchronous MongoDB query for every incoming message.
_filter_cache: dict[int, tuple[bool, tuple[str, ...]]] = {}

async def on_guild_remove(guild):
    """Clean up cache and database entries when the bot leaves a guild."""
    guild_id = guild.id
    _filter_cache.pop(guild_id, None)
    config_collection.delete_one({"guild_id": guild_id})
    automod_rule_id_collection.delete_one({"guild_id": guild_id})
    filter_collection.delete_many({"guild_id": guild_id})
    warnings_collection.delete_many({"guild_id": guild_id})
    moderation_cases_collection.delete_many({"guild_id": guild_id})
    scheduled_invites_collection.delete_many({"guild_id": guild_id})
    blacklist_collection.delete_many({"guild_id": guild_id})


def save_config(guild_id, log_channel=None, welcome_channel=None):
    global config_collection
    update_data = {}
    if log_channel is not None:
        update_data["log_channel"] = log_channel
    if welcome_channel is not None:
        update_data["welcome_channel"] = welcome_channel

    if update_data:
        config_collection.update_one(
            {"guild_id": guild_id}, {"$set": update_data}, upsert=True
        )


def load_config(guild_id):
    global config_collection
    data = config_collection.find_one({"guild_id": guild_id})
    if data:
        return data.get("log_channel"), data.get("welcome_channel")
    return None, None


def save_automod_rule_id(guild_id: int, rule_id: str | None):
    try:
        config_collection.update_one({"guild_id": int(guild_id)}, {"$set": {"automod_rule_id": rule_id}}, upsert=True)
        return True
    except Exception as e:
        print(f"[ERROR] save_automod_rule_id: {e}")
        return False


def load_automod_rule_id(guild_id: int):
    try:
        doc = config_collection.find_one({"guild_id": int(guild_id)})
        if doc:
            return doc.get("automod_rule_id")
        return None
    except Exception as e:
        print(f"[ERROR] load_automod_rule_id: {e}")
        return None


# ===== Filter Helper Functions =====





def save_filter_words(guild_id, words):
    """Save filter words for a specific guild to MongoDB"""
    try:
        guild_id = int(guild_id)
        words = [str(w).lower() for w in words] if words else []

        result = filter_collection.update_one(
            {"guild_id": guild_id},
            {"$set": {"filter_words": words, "updated_at": datetime.datetime.now(timezone.utc)}},
            upsert=True,
        )
        if result.acknowledged:
            previous = _filter_cache.get(guild_id)
            if previous is None:
                existing = filter_collection.find_one(
                    {"guild_id": guild_id}, {"enabled": 1}
                )
                enabled = bool(existing.get("enabled", True)) if existing else True
            else:
                enabled = previous[0]
            _filter_cache[guild_id] = (
                enabled,
                tuple(words),
            )
        return result.acknowledged
    except Exception as e:
        print(f"[ERROR] save_filter_words: {e}")
        return False


def load_filter_words(guild_id):
    """Load filter words for a specific guild from MongoDB"""
    try:
        guild_id = int(guild_id)
        cached = _filter_cache.get(guild_id)
        if cached is not None:
            return list(cached[1])
        doc = filter_collection.find_one({"guild_id": guild_id})
        words = [str(w).lower() for w in doc.get("filter_words", default_filter_words)] if doc else list(default_filter_words)
        enabled = bool(doc.get("enabled", True)) if doc else True
        _filter_cache[guild_id] = (enabled, tuple(words))
        return list(words)
    except Exception as e:
        print(f"[ERROR] load_filter_words: {e}")
        return list(default_filter_words)


def reset_filter_words(guild_id):
    """Reset a guild's filter words back to defaults"""
    try:
        guild_id = int(guild_id)
        filter_collection.update_one(
            {"guild_id": guild_id},
            {
                "$set": {
                    "filter_words": list(default_filter_words),
                    "updated_at": datetime.datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )
        _filter_cache[guild_id] = (True, tuple(default_filter_words))
        return list(default_filter_words)
    except Exception as e:
        print(f"[ERROR] reset_filter_words: {e}")
        return list(default_filter_words)


def set_filter_enabled(guild_id, enabled: bool):
    """Enable or disable the filter for a guild (stores flag in word_filters collection)."""
    try:
        guild_id = int(guild_id)
        filter_collection.update_one(
            {"guild_id": guild_id},
            {"$set": {"enabled": bool(enabled), "updated_at": datetime.datetime.now(timezone.utc)}},
            upsert=True,
        )
        cached = _filter_cache.get(guild_id)
        words = cached[1] if cached else tuple(load_filter_words(guild_id))
        _filter_cache[guild_id] = (bool(enabled), words)
        return True
    except Exception as e:
        print(f"[ERROR] set_filter_enabled: {e}")
        return False


def debug_filter_db():
    """Debug function to print all filter documents"""
    global filter_collection
    print("\n=== DEBUG: MongoDB Filter Collection ===")
    for doc in filter_collection.find():
        print(
            f"Guild {doc.get('guild_id')}: {len(doc.get('filter_words', []))} words, enabled: {doc.get('enabled', True)}"
        )
    print("=== End of Filter Debug ===\n")


def debug_db():
    """Debug function to print all documents in the config collection"""
    print("\n=== DEBUG: MongoDB Config Collection ===")
    for doc in config_collection.find():
        print(f"Document: {doc}")
    print("=== End of MongoDB Debug ===\n")




app = Flask(__name__)


def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, use_reloader=False)


def start_flask_thread():
    thread = threading.Thread(target=run_flask, daemon=True, name="flask-health-server")
    thread.start()
    return thread


@app.route("/")
def home():
    return "Bread Bot is running! 🍞"


@app.route("/health")
def health():
    return {"status": "healthy", "bot": "online"}


load_dotenv()
token = os.getenv("DISCORD_TOKEN")

handler = logging.FileHandler(filename="discord.log", encoding="utf-8", mode="a")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="bread ", intents=intents, help_command=None)
bot_start_time = None


try:
    env_owner = os.getenv("BOT_OWNER_ID")
    if env_owner:
        bot.owner_id = int(env_owner)
except Exception:
    pass

TIME_ID = 1413747681163087893
PING_URL = "https://bread-bot-8rqr.onrender.com/"


async def keep_alive_task():
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
        await asyncio.sleep(30)

        await asyncio.sleep(300)  # every 5 minutes

def check_mongodb_connection():
    try:
        server_info = client.server_info()
        print(f"✅ MongoDB Server Version: {server_info.get('version')}")

        collections = db.list_collection_names()
        print(f"✅ Available collections: {collections}")


        print(f"✅ Server configs collection exists: {'server_configs' in collections}")
        print(f"✅ Word filters collection exists: {'word_filters' in collections}")

        if "word_filters" in collections:
            count = db.word_filters.count_documents({})
            print(f"✅ Word filters collection has {count} documents")
            if count > 0:
                print("✅ Sample document:", db.word_filters.find_one())

        return True
    except Exception as e:
        print(f"❌ MongoDB Connection Error: {e!s}")
        return False


async def _create_automod_rule_via_rest(guild: discord.Guild, keywords: list, alert_channel_id: int):
    """Create a minimal automod rule via Discord REST. Returns rule id or None."""
    if not keywords:
        return None

    payload = {
        "name": "Bread Bot - AutoMod Filter",
        "event_type": 1,  # MESSAGE_SEND
        "trigger_type": 1,  # KEYWORD
        # Discord expects keyword trigger metadata under the `keyword_filter` key
        "trigger_metadata": {"keyword_filter": keywords},
        "actions": [
            {"type": 1},  # BLOCK_MESSAGE
            {"type": 4, "metadata": {"channel_id": str(alert_channel_id)}},  # SEND_ALERT_MESSAGE
        ],
        "enabled": True,
    }

    try:
        # Prefer discord.py HTTP client if available
        if hasattr(bot, "http") and hasattr(bot.http, "request"):
            try:
                route = discord.http.Route("POST", "/guilds/{guild_id}/auto-moderation/rules", guild_id=guild.id)
                resp = await bot.http.request(route, json=payload)
                if isinstance(resp, dict):
                    return resp.get("id")
            except Exception:
                pass

        # Use shared aiohttp session
        url = f"https://discord.com/api/v10/guilds/{guild.id}/auto-moderation/rules"
        headers = {"Authorization": f"Bot {token}", "Content-Type": "application/json"}
        async with bot.aiohttp_session.post(url, json=payload, headers=headers) as r:
            if r.status in (200, 201):
                data = await r.json()
                return data.get("id")
            else:
                # Try to parse JSON error body to detect disallowed action types
                try:
                    err_data = await r.json()
                except Exception:
                    err_data = None

                # Log the original error body (string) for visibility
                try:
                    txt = await r.text()
                except Exception:
                    txt = str(err_data)
                print(f"AutoMod create failed: {r.status} {txt}")

                # Detect AUTO_MODERATION_ACTION_TYPE_DISALLOWED anywhere in the error payload
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
                    async with bot.aiohttp_session.post(url, json=payload_no_alert, headers=headers) as r2:
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


async def _delete_automod_rule_via_rest(guild: discord.Guild, rule_id: str):
    try:
        if hasattr(bot, "http") and hasattr(bot.http, "request"):
            try:
                route = discord.http.Route("DELETE", "/guilds/{guild_id}/auto-moderation/rules/{rule_id}", guild_id=guild.id, rule_id=rule_id)
                await bot.http.request(route)
                return True
            except Exception:
                pass

        url = f"https://discord.com/api/v10/guilds/{guild.id}/auto-moderation/rules/{rule_id}"
        headers = {"Authorization": f"Bot {token}"}
        async with bot.aiohttp_session.delete(url, headers=headers) as r:
            if r.status in (200, 204):
                return True
            else:
                txt = await r.text()
                print(f"AutoMod delete failed: {r.status} {txt}")
                return False
    except Exception as e:
        print(f"Error deleting automod rule: {e}")
        return False


async def _update_automod_rule_keywords_via_rest(guild: discord.Guild, rule_id: str, keywords: list, alert_channel_id: int | None = None):
    """Update an existing automod rule's keyword list. If keywords is empty, delete the rule.
    Returns True on success (including deletion), False otherwise."""
    try:
        # If there are no keywords left, delete the automod rule entirely
        if not keywords:
            print("No keywords left; deleting automod rule instead of updating")
            return await _delete_automod_rule_via_rest(guild, rule_id)

        payload_base = {
            "name": "Bread Bot - AutoMod Filter",
            "event_type": 1,
            "trigger_type": 1,
            "trigger_metadata": {"keyword_filter": keywords},
            "enabled": True,
        }

        # Try to preserve the alert action if an alert_channel_id was provided; otherwise attempt block-only.
        actions_with_alert = [{"type": 1}]
        if alert_channel_id:
            actions_with_alert.append({"type": 4, "metadata": {"channel_id": str(alert_channel_id)}})

        # Attempt PATCH using discord.py http if available
        if hasattr(bot, "http") and hasattr(bot.http, "request"):
            try:
                data_payload = dict(payload_base)
                data_payload["actions"] = actions_with_alert if alert_channel_id else [{"type": 1}]
                route = discord.http.Route("PATCH", "/guilds/{guild_id}/auto-moderation/rules/{rule_id}", guild_id=guild.id, rule_id=rule_id)
                resp = await bot.http.request(route, json=data_payload)
                if isinstance(resp, dict):
                    return True
            except Exception:
                pass

        # Fallback to aiohttp
        async with aiohttp.ClientSession() as session:
            url = f"https://discord.com/api/v10/guilds/{guild.id}/auto-moderation/rules/{rule_id}"
            headers = {"Authorization": f"Bot {token}", "Content-Type": "application/json"}

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


def save_automod_rule_id(guild_id: int, rule_id: str | None):
    try:
        config_collection.update_one({"guild_id": int(guild_id)}, {"$set": {"automod_rule_id": rule_id}}, upsert=True)
        return True
    except Exception as e:
        print(f"[ERROR] save_automod_rule_id: {e}")
        return False


def load_automod_rule_id(guild_id: int):
    try:
        doc = config_collection.find_one({"guild_id": int(guild_id)})
        if doc:
            return doc.get("automod_rule_id")
        return None
    except Exception as e:
        print(f"[ERROR] load_automod_rule_id: {e}")
        return None


@bot.tree.command(name="automod", description="Enable/disable Discord AutoMod using current filter words")
@app_commands.describe(action="enable or disable AutoMod for this server")
@app_commands.choices(action=[app_commands.Choice(name="enable", value="enable"), app_commands.Choice(name="disable", value="disable")])
@app_commands.default_permissions(manage_guild=True)
async def automod(interaction: discord.Interaction, action: str):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("❌ Manage Server permission required", ephemeral=True)
        return

    guild = interaction.guild
    guild_id = guild.id
    log_channel_id, _ = load_config(guild_id)
    target_channel = log_channel_id or LOG_CHANNEL_ID
    if not target_channel:
        await interaction.response.send_message("❌ No mod-log or log channel configured. Use setchannel/setlog first.", ephemeral=True)
        return

    if action == "enable":
        keywords = load_filter_words(guild_id)
        if not keywords:
            await interaction.response.send_message("❌ No filter words found to create automod rule.", ephemeral=True)
            return

        rule_id = await _create_automod_rule_via_rest(guild, keywords, int(target_channel))
        if not rule_id:
            await interaction.response.send_message("❌ Failed to create AutoMod rule. Check bot permissions and logs.", ephemeral=True)
            return

        save_automod_rule_id(guild_id, str(rule_id))
        await interaction.response.send_message("✅ AutoMod rule created and enabled for this server.", ephemeral=True)
        try:
            await send_mod_log(
                guild=guild,
                title="⚙️ AutoMod Enabled",
                description=f"AutoMod rule created using filter words. Rule ID: {rule_id}",
                color=0x00FF00,
            )
        except Exception:
            pass

    else:  # disable
        existing = load_automod_rule_id(guild_id)
        if not existing:
            await interaction.response.send_message("❌ No AutoMod rule is currently stored for this server.", ephemeral=True)
            return

        ok = await _delete_automod_rule_via_rest(guild, existing)
        if ok:
            save_automod_rule_id(guild_id, None)
            await interaction.response.send_message("✅ AutoMod rule deleted.", ephemeral=True)
            try:
                await send_mod_log(
                    guild=guild,
                    title="⚙️ AutoMod Disabled",
                    description=f"AutoMod rule (ID: {existing}) has been deleted.",
                    color=0xFF0000,
                )
            except Exception:
                pass
        else:
            await interaction.response.send_message("❌ Failed to delete AutoMod rule. Check logs.", ephemeral=True)


@bot.command(name="automod", aliases=["am", "auto-mod"])
@commands.has_permissions(manage_guild=True)
async def automod_cmd(ctx, action: str = None):
    if not action:
        await ctx.send("❌ Please specify `enable` or `disable`")
        return
    if action.lower() in {"on", "enable"}:
        guild = ctx.guild
        guild_id = guild.id
        log_channel_id, _ = load_config(guild_id)
        target_channel = log_channel_id or LOG_CHANNEL_ID
        if not target_channel:
            await ctx.send("❌ No mod-log or log channel configured. Use setchannel/setlog first.")
            return
        keywords = load_filter_words(guild_id)
        if not keywords:
            await ctx.send("❌ No filter words found to create automod rule.")
            return
        rule_id = await _create_automod_rule_via_rest(guild, keywords, int(target_channel))
        if not rule_id:
            await ctx.send("❌ Failed to create AutoMod rule. Check bot permissions and logs.")
            return
        save_automod_rule_id(guild_id, str(rule_id))
        await ctx.send("✅ AutoMod rule created and enabled for this server.")
        try:
            await send_mod_log(guild=guild, title="⚙️ AutoMod Enabled", description=f"AutoMod rule created using filter words. Rule ID: {rule_id}", color=0x00FF00)
        except Exception:
            pass

    elif action.lower() in {"off", "disable"}:
        guild_id = ctx.guild.id
        existing = load_automod_rule_id(guild_id)
        if not existing:
            await ctx.send("❌ No AutoMod rule is currently stored for this server.")
            return
        ok = await _delete_automod_rule_via_rest(ctx.guild, existing)
        if ok:
            save_automod_rule_id(guild_id, None)
            await ctx.send("✅ AutoMod rule deleted.")
            try:
                await send_mod_log(guild=ctx.guild, title="⚙️ AutoMod Disabled", description=f"AutoMod rule (ID: {existing}) has been deleted.", color=0xFF0000)
            except Exception:
                pass
        else:
            await ctx.send("❌ Failed to delete AutoMod rule. Check logs.")


@bot.event
async def setup_hook():
    bot.aiohttp_session = aiohttp.ClientSession()
    bot.background_task = asyncio.create_task(keep_alive_task())
    bot.scheduled_invite_task = asyncio.create_task(process_scheduled_invites())
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

    # Create database indexes
    scheduled_invites_collection.create_index([("status", 1), ("send_at", 1)])
    warnings_collection.create_index([("guild_id", 1), ("user_id", 1), ("created_at", 1)])


@bot.event
async def on_ready():
    global bot_start_time
    if bot_start_time is None:
        bot_start_time = discord.utils.utcnow()

    print(f"We are ready to go in, {bot.user.name}")
    try:
        synced = bot.tree.get_commands()
        print(f"✅ Synced {len(synced)} global commands: {[cmd.name for cmd in synced]}")
        # Print debug info on startup
        debug_db()
    except Exception as e:
        print(f"❌ Failed to sync commands: {e}")


# --- Guild blacklist collection and global blacklist
guild_blacklist_collection = db["guild_blacklists"]
try:
    guild_blacklist_collection.create_index("guild_id", unique=True)
    print("✅ Created index on guild_id for guild_blacklists")
except Exception as e:
    print(f"ℹ️ Could not create index for guild_blacklists: {e}")

# Global blacklist only editable in source code
GLOBAL_BLACKLIST = [
  1400613835445899416, # Tray's main acc ##################### Pinkly #chloe's main acc
  1420535411339563234, #Tray's alt  # Pinkly main

]

BLACKLIST_BLOCK_MESSAGE = "You are banned from using this bot. If you think this is an mistake please contact either the server admins or the bot owner."


def add_guild_blacklist(guild_id: int, user_id: int):
    try:
        guild_blacklist_collection.update_one(
            {"guild_id": int(guild_id)},
            {"$addToSet": {"user_ids": int(user_id)}},
            upsert=True,
        )
        return True
    except Exception as e:
        print(f"[ERROR] add_guild_blacklist: {e}")
        return False


def remove_guild_blacklist(guild_id: int, user_id: int):
    try:
        guild_blacklist_collection.update_one(
            {"guild_id": int(guild_id)}, {"$pull": {"user_ids": int(user_id)}}
        )
        return True
    except Exception as e:
        print(f"[ERROR] remove_guild_blacklist: {e}")
        return False


def get_guild_blacklist(guild_id: int):
    try:
        doc = guild_blacklist_collection.find_one({"guild_id": int(guild_id)})
        if doc and "user_ids" in doc:
            return [int(u) for u in doc.get("user_ids", [])]
        return []
    except Exception as e:
        print(f"[ERROR] get_guild_blacklist: {e}")
        return []


def is_user_blocked(guild_id: int, user_id: int):
    if int(user_id) in GLOBAL_BLACKLIST:
        return True
    try:
        return int(user_id) in get_guild_blacklist(guild_id)
    except Exception:
        return False


@bot.before_invoke
async def global_prefix_block_check(ctx):
    try:
        if not ctx.guild:
            return
        if is_user_blocked(ctx.guild.id, ctx.author.id):
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
    """Check for slash/app command invocations from blacklisted users.
    This will be registered with bot.tree.add_check(...) after the bot is created.
    """
    try:
        if not interaction.guild:
            return True
        if is_user_blocked(interaction.guild.id, interaction.user.id):
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

            raise app_commands.CheckFailure("user_blacklisted")
        return True
    except app_commands.CheckFailure:
        raise
    except Exception as e:
        print(f"[WARN] global_slash_block_check error: {e}")
        return True


@bot.tree.command(name="blacklist", description="Manage the server blacklist (admins only)")
@app_commands.describe(action="add/remove/list", user="User to add/remove")
@app_commands.choices(action=[app_commands.Choice(name="add", value="add"), app_commands.Choice(name="remove", value="remove"), app_commands.Choice(name="list", value="list")])
@commands.has_permissions(administrator=True)
async def blacklist(interaction: discord.Interaction, action: str, user: discord.Member = None):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Administrator permissions required", ephemeral=True)
        return

    guild_id = interaction.guild_id
    if action == "add":
        if not user:
            await interaction.response.send_message("❌ Please specify a user to add", ephemeral=True)
            return
        # Enforce role hierarchy: issuer must have higher role than target (unless guild owner)
        issuer = interaction.guild.get_member(interaction.user.id)
        target = interaction.guild.get_member(user.id) if isinstance(user, discord.Member) else None
        if not issuer or not target:
            await interaction.response.send_message("❌ Could not resolve the target member in this server.", ephemeral=True)
            return
        if issuer.id != interaction.guild.owner_id:
            # can't blacklist the owner
            if target.id == interaction.guild.owner_id:
                await interaction.response.send_message("❌ You cannot blacklist the server owner.", ephemeral=True)
                return
            if target.top_role >= issuer.top_role:
                await interaction.response.send_message("❌ You cannot blacklist a member with an equal or higher role than you.", ephemeral=True)
                return
        # ensure bot role is higher than the target for manage-like actions (best-effort)
        bot_member = interaction.guild.get_member(bot.user.id)
        if bot_member and target.top_role >= bot_member.top_role:
            await interaction.response.send_message("❌ I cannot modify this user due to role hierarchy (my role is not high enough).", ephemeral=True)
            return

        add_guild_blacklist(guild_id, user.id)
        await interaction.response.send_message(f"✅ {user.mention} added to server blacklist", ephemeral=True)
        try:
            await send_mod_log(
                guild=interaction.guild,
                title="⛔ User Blacklisted (Server)",
                description=f"{user.mention} was added to the server blacklist by {interaction.user.mention}",
                color=0xFF0000,
                fields=[("User", f"{user} ({user.id})", False), ("Moderator", interaction.user.mention, True)],
            )
        except Exception:
            pass
    elif action == "remove":
        if not user:
            await interaction.response.send_message("❌ Please specify a user to remove", ephemeral=True)
            return
        issuer = interaction.guild.get_member(interaction.user.id)
        target = interaction.guild.get_member(user.id) if isinstance(user, discord.Member) else None
        if not issuer or not target:
            await interaction.response.send_message("❌ Could not resolve the target member in this server.", ephemeral=True)
            return
        if issuer.id != interaction.guild.owner_id:
            if target.id == interaction.guild.owner_id:
                await interaction.response.send_message("❌ You cannot remove the server owner from the blacklist.", ephemeral=True)
                return
            if target.top_role >= issuer.top_role:
                await interaction.response.send_message("❌ You cannot remove a blacklist entry for a member with an equal or higher role than you.", ephemeral=True)
                return

        remove_guild_blacklist(guild_id, user.id)
        await interaction.response.send_message(f"✅ {user.mention} removed from server blacklist", ephemeral=True)
        try:
            await send_mod_log(
                guild=interaction.guild,
                title="✅ User Removed from Blacklist",
                description=f"{user.mention} was removed from server blacklist by {interaction.user.mention}",
                color=0x00FF00,
                fields=[("User", f"{user} ({user.id})", False), ("Moderator", interaction.user.mention, True)],
            )
        except Exception:
            pass
    else:  # list
        users = get_guild_blacklist(guild_id)
        if not users:
            await interaction.response.send_message("No users are blacklisted on this server.", ephemeral=True)
            return
        mentions = []
        for uid in users:
            member = interaction.guild.get_member(int(uid))
            mentions.append(member.mention if member else f"<@{uid}>")
        await interaction.response.send_message("Blacklisted users: " + ", ".join(mentions), ephemeral=True)


@bot.command(name="blacklist", help="Manage server blacklist (admin only)")
@commands.has_permissions(administrator=True)
async def blacklist_cmd(ctx, action: str, user: discord.Member = None):
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ Administrator permissions required")
        return

    guild_id = ctx.guild.id
    if action.lower() == "add":
        if not user:
            await ctx.send("❌ Please specify a user to add")
            return
        issuer = ctx.guild.get_member(ctx.author.id)
        target = ctx.guild.get_member(user.id) if isinstance(user, discord.Member) else None
        if not issuer or not target:
            await ctx.send("❌ Could not resolve the target member in this server.")
            return
        if issuer.id != ctx.guild.owner_id:
            if target.id == ctx.guild.owner_id:
                await ctx.send("❌ You cannot blacklist the server owner.")
                return
            if target.top_role >= issuer.top_role:
                await ctx.send("❌ You cannot blacklist a member with an equal or higher role than you.")
                return
        bot_member = ctx.guild.get_member(bot.user.id)
        if bot_member and target.top_role >= bot_member.top_role:
            await ctx.send("❌ I cannot modify this user due to role hierarchy (my role is not high enough).")
            return

        add_guild_blacklist(guild_id, user.id)
        await ctx.send(f"✅ {user.mention} added to server blacklist")
        try:
            await send_mod_log(
                guild=ctx.guild,
                title="⛔ User Blacklisted (Server)",
                description=f"{user.mention} was added to the server blacklist by {ctx.author.mention}",
                color=0xFF0000,
                fields=[("User", f"{user} ({user.id})", False), ("Moderator", ctx.author.mention, True)],
            )
        except Exception:
            pass
    elif action.lower() == "remove":
        if not user:
            await ctx.send("❌ Please specify a user to remove")
            return
        issuer = ctx.guild.get_member(ctx.author.id)
        target = ctx.guild.get_member(user.id) if isinstance(user, discord.Member) else None
        if not issuer or not target:
            await ctx.send("❌ Could not resolve the target member in this server.")
            return
        if issuer.id != ctx.guild.owner_id:
            if target.id == ctx.guild.owner_id:
                await ctx.send("❌ You cannot remove the server owner from the blacklist.")
                return
            if target.top_role >= issuer.top_role:
                await ctx.send("❌ You cannot remove a blacklist entry for a member with an equal or higher role than you.")
                return

        remove_guild_blacklist(guild_id, user.id)
        await ctx.send(f"✅ {user.mention} removed from server blacklist")
        try:
            await send_mod_log(
                guild=ctx.guild,
                title="✅ User Removed from Blacklist",
                description=f"{user.mention} was removed from server blacklist by {ctx.author.mention}",
                color=0x00FF00,
                fields=[("User", f"{user} ({user.id})", False), ("Moderator", ctx.author.mention, True)],
            )
        except Exception:
            pass
    elif action.lower() == "list":
        users = get_guild_blacklist(guild_id)
        if not users:
            await ctx.send("No users are blacklisted on this server.")
            return
        mentions = []
        for uid in users:
            member = ctx.guild.get_member(int(uid))
            mentions.append(member.mention if member else f"<@{uid}>")
        await ctx.send("Blacklisted users: " + ", ".join(mentions))
    else:
        await ctx.send("❌ Invalid action. Use: add, remove, list")


@bot.tree.command(name="test", description="A simple test command")
async def test_command(interaction: discord.Interaction):
    await interaction.response.send_message("Test command works! ✅")


@bot.tree.command(name="ping", description="Check if the bot is responsive")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("Pong! 🏓")


@bot.tree.command(name="hello", description="Say hello to the bot")
async def slash_hello(interaction: discord.Interaction):
    await interaction.response.send_message(f"Hello, {interaction.user.mention}! 👋")


@bot.command()
async def hello(ctx):
    """Say hello to the bot (prefix command)"""
    await ctx.send(f"Hello, {ctx.author.mention}! 👋")


@bot.tree.command(name="coin_toss", description="flips a coin")
async def coin_toss(interaction: discord.Interaction):
    result = random.choice(["Heads", "Tails"])
    emoji = "👑" if result == "Heads" else "🔢"

    embed = discord.Embed(
        title="🪙 Coin Toss",
        description=f"{emoji} **{result}**!",
        color=0x00FF00 if result == "Heads" else 0xFF0000,
    )
    await interaction.response.send_message(embed=embed)


@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason="No reason provided"):
    """Kick a member from the server (prefix command)"""
    await ctx.send("Use `/kick` so the required reason and evidence form is recorded.")
    return
    if not ctx.guild.me.guild_permissions.kick_members:
        await ctx.send("❌ I don't have permission to kick members!")
        return
    if member == ctx.author:
        await ctx.send("❌ You can't kick yourself!")
        return

    if member == ctx.guild.owner:
        await ctx.send("❌ You can't kick the server owner!")
        return

    if member.top_role >= ctx.guild.me.top_role:
        await ctx.send("❌ I can't kick someone with a role higher or equal to mine!")
        return

    if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
        await ctx.send(
            "❌ You can't kick someone with a role higher or equal to yours!"
        )
        return

    try:
        try:
            await member.send(
                f"You have been kicked from **{ctx.guild.name}**\nReason: {reason}"
            )
        except:
            pass

        await member.kick(reason=f"{reason} (kicked by {ctx.author})")

        await ctx.send(f"✅ {member.mention} has been kicked!\nReason: {reason}")

        await send_mod_log(
            guild=ctx.guild,
            title="👢 Member Kicked",
            description=f"{member.mention} has been kicked from the server.",
            color=0xFF9900,
            fields=[
                ("User", f"{member} ({member.id})", False),
                ("Moderator", ctx.author.mention, True),
                ("Reason", reason, True),
                (
                    "Account Created",
                    discord.utils.format_dt(member.created_at, "R"),
                    True,
                ),
            ],
            thumbnail=member.avatar.url if member.avatar else None,
        )

    except discord.Forbidden:
        await ctx.send("❌ I don't have permission to kick this member!")
    except Exception as e:
        await ctx.send(f"❌ An error occurred: {e}")
        await send_mod_log(
            guild=ctx.guild,
            title="❌ Kick Failed",
            description=f"Failed to kick {member.mention}",
            color=0xFF0000,
            fields=[
                ("Error", str(e), False),
                ("Moderator", ctx.author.mention, True),
                ("Target", f"{member} ({member.id})", True),
            ],
        )


async def kick_slash(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str = "No reason provided",
):
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
        await interaction.response.send_message("❌ You can't kick me!", ephemeral=True)
        return
    if (
        member.top_role >= interaction.user.top_role
        and interaction.user != interaction.guild.owner
    ):
        await interaction.response.send_message(
            "❌ You can't kick someone with equal or higher roles!", ephemeral=True
        )
        return

    try:
        try:
            await member.send(
                f"You have been kicked from **{interaction.guild.name}**\nReason: {reason}"
            )
        except:
            pass  # User has DMs disabled or blocked the bot

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
                (
                    "Account Created",
                    discord.utils.format_dt(member.created_at, "R"),
                    True,
                ),
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
        await send_mod_log(
            guild=interaction.guild,
            title="❌ Kick Failed",
            description=f"Failed to kick {member.mention}",
            color=0xFF0000,
            fields=[
                ("Error", str(e), False),
                ("Moderator", interaction.user.mention, True),
                ("Target", f"{member} ({member.id})", True),
            ],
        )


async def ban(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str = "No reason provided",
):
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


@bot.tree.command(name="unban", description="Unban a member from the server")
@app_commands.describe(user="The user to unban", reason="Reason for unbanning")
async def unban(
    interaction: discord.Interaction,
    user: discord.User,
    reason: str,
):
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


@bot.tree.command(name="unkick", description="Send a kicked user a new server invite")
@app_commands.describe(user="Kicked user to invite back", reason="Reason for inviting them back")
async def unkick(interaction: discord.Interaction, user: discord.User, reason: str):
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


async def mute(
    interaction: discord.Interaction,
    member: discord.Member,
    duration: int = 10,
    reason: str = "No reason provided",
):
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


@bot.command()
@commands.has_permissions(moderate_members=True)
async def mute(
    ctx, member: discord.Member, duration: int = 10, *, reason="No reason provided"
):
    """Mute a member for a specified duration (in minutes)"""
    await ctx.send("Use `/mute` so the required reason and evidence form is recorded.")
    return
    if not ctx.guild.me.guild_permissions.moderate_members:
        await ctx.send("❌ I don't have permission to timeout members!")
        return

    if member == ctx.author:
        await ctx.send("❌ You can't mute yourself!")
        return

    if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
        await ctx.send("❌ You can't mute someone with equal or higher roles!")
        return

    if member == ctx.guild.me:
        await ctx.send("❌ You can't mute me!")
        return

    try:
        timeout_until = discord.utils.utcnow() + datetime.timedelta(minutes=duration)

        try:
            await member.send(
                f"You have been muted in **{ctx.guild.name}** for {duration} minutes.\nReason: {reason}"
            )
        except:
            pass  # User has DMs disabled or blocked the bot

        await member.timeout(timeout_until, reason=f"{reason} (by {ctx.author})")

        await ctx.send(
            f"✅ {member.mention} has been muted for {duration} minutes!\nReason: {reason}"
        )

        await send_mod_log(
            guild=ctx.guild,
            title="🔇 Member Muted",
            description=f"{member.mention} has been muted for {duration} minutes.",
            color=0xFFA500,
            fields=[
                ("User", f"{member} ({member.id})", False),
                ("Moderator", ctx.author.mention, True),
                ("Duration", f"{duration} minutes", True),
                ("Reason", reason, True),
                ("Muted Until", discord.utils.format_dt(timeout_until, "R"), True),
            ],
            thumbnail=member.avatar.url if member.avatar else None,
        )

    except discord.Forbidden:
        await ctx.send("❌ I don't have permission to timeout this member!")
    except Exception as e:
        await ctx.send(f"❌ An error occurred: {e}")
        await send_mod_log(
            guild=ctx.guild,
            title="❌ Mute Failed",
            description=f"Failed to mute {member.mention}",
            color=0xFF0000,
            fields=[
                ("Error", str(e), False),
                ("Moderator", ctx.author.mention, True),
                ("Target", f"{member} ({member.id})", True),
            ],
        )



@bot.tree.command(name="purge", description="Purge messages from a channel")
@app_commands.describe(limit="Number of messages to purge")
async def purge(interaction: discord.Interaction, limit: int = 2000):
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


@bot.tree.command(name="broadcast", description="Broadcast a message to all channels")
@app_commands.describe(
    message="The message to broadcast", ping_everyone="Whether to ping @everyone"
)
async def broadcast(
    interaction: discord.Interaction, message: str, ping_everyone: bool = False
):
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
        broadcast_message = f"@everyone {message}" if ping_everyone else message

        for channel in interaction.guild.text_channels:
            try:
                await channel.send(broadcast_message)
                channel_count += 1
            except discord.Forbidden:
                continue

        ping_status = "with @everyone ping" if ping_everyone else "without ping"
        await interaction.response.send_message(
            f"✅ Broadcasted message to {channel_count} channels {ping_status}!",
            ephemeral=True,
        )
        try:
            await send_mod_log(
                guild=interaction.guild,
                title="📣 Broadcast Sent",
                description=f"Broadcast sent by {interaction.user.mention} to {channel_count} channels ({ping_status}).",
                color=0xF1C40F,
                fields=[
                    ("Moderator", interaction.user.mention, True),
                    ("Channels Sent", str(channel_count), True),
                    ("Ping Status", ping_status, True),
                    ("Message", (message[:1024] + '...') if len(message) > 1024 else message, False),
                ],
            )
        except Exception:
            pass
    except Exception as e:
        await interaction.response.send_message(
            f"❌ An error occurred: {e}", ephemeral=True
        )


@bot.tree.command(
    name="setwelcome", description="Set the welcome channel for new members"
)
@app_commands.describe(channel="The channel to send welcome messages in")
@commands.has_permissions(manage_channels=True)
async def set_welcome_channel(
    interaction: discord.Interaction, channel: discord.TextChannel
):
    """Set the welcome channel for new members (slash command)"""
    global WELCOME_CHANNEL_ID
    try:
        save_config(guild_id=interaction.guild.id, welcome_channel=channel.id)
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


async def send_mod_log(
    guild: discord.Guild,
    title: str,
    description: str,
    color: int,
    fields: list = None,
    thumbnail: str = None,
):
    """Helper function to send mod logs to the log channel"""
    global LOG_CHANNEL_ID

    try:
        log_channel_id = None
        try:
            if guild and hasattr(guild, "id"):
                saved_log, _ = load_config(guild.id)
                if saved_log:
                    log_channel_id = saved_log
        except Exception:
            log_channel_id = None

        if not log_channel_id:
            log_channel_id = LOG_CHANNEL_ID

        if not log_channel_id:
            return False

        log_channel = None
        if guild:
            try:
                log_channel = guild.get_channel(int(log_channel_id))
            except Exception:
                log_channel = None

        if not log_channel and 'bot' in globals():
            try:
                log_channel = bot.get_channel(int(log_channel_id))
            except Exception:
                log_channel = None

        if not log_channel:
            return False

        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=discord.utils.utcnow(),
        )

        if fields:
            for name, value, inline in fields:
                embed.add_field(name=name, value=value, inline=inline)

        if thumbnail:
            embed.set_thumbnail(url=thumbnail)

        await log_channel.send(embed=embed)
        return True
    except Exception as e:
        print(f"Failed to send mod log: {e}")
        return False


# ===== Modal moderation workflow =====
def _moderation_target_allowed(guild, moderator, member):
    """Return a short error when a moderator cannot act on a member."""
    if member == moderator:
        return "You cannot moderate yourself."
    if member == guild.owner:
        return "You cannot moderate the server owner."
    if member == guild.me or member.top_role >= guild.me.top_role:
        return "I cannot moderate that member because of role hierarchy."
    if moderator != guild.owner and member.top_role >= moderator.top_role:
        return "You cannot moderate a member with an equal or higher role."
    return None


async def _send_temporary_confirmation(interaction, content):
    await interaction.response.send_message(content)
    message = await interaction.original_response()
    await asyncio.sleep(60)
    try:
        await message.delete()
    except (discord.NotFound, discord.Forbidden):
        pass


async def _dm_punishment(member, guild, action, reason, evidence, duration):
    embed = discord.Embed(title=f"Moderation notice: {action.title()}", color=0xE74C3C)
    embed.add_field(name="Server", value=guild.name, inline=False)
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.add_field(name="Duration", value=duration, inline=True)
    embed.add_field(name="Evidence", value=evidence, inline=False)
    try:
        await member.send(embed=embed)
        return True
    except (discord.Forbidden, discord.HTTPException):
        return False


def _find_member(guild, value):
    """Resolve a modal's username, mention, or numeric ID to a guild member."""
    value = value.strip()
    if value.startswith("<@") and value.endswith(">"):
        value = value.strip("<@!>")
    if value.isdigit():
        return guild.get_member(int(value))
    lowered = value.casefold()
    return discord.utils.find(
        lambda member: member.name.casefold() == lowered
        or member.display_name.casefold() == lowered
        or str(member).casefold() == lowered,
        guild.members,
    )


async def _queue_rejoin_invite(guild, user_id, days, reason):
    scheduled_invites_collection.update_one(
        {"guild_id": guild.id, "user_id": user_id, "status": "pending"},
        {"$set": {
            "guild_id": guild.id, "user_id": user_id, "reason": reason,
            "send_at": discord.utils.utcnow() + datetime.timedelta(days=days),
            "status": "pending", "created_at": discord.utils.utcnow(),
        }}, upsert=True,
    )


async def _perform_moderation(interaction, member, action, reason, evidence, duration=None, rejoin_days=None):
    guild = interaction.guild
    moderator = interaction.user
    error = _moderation_target_allowed(guild, moderator, member)
    if error:
        await interaction.response.send_message(f"❌ {error}", ephemeral=True)
        return

    permission = {"ban": "ban_members", "kick": "kick_members", "timeout": "moderate_members"}[action]
    if not getattr(moderator.guild_permissions, permission) or not getattr(guild.me.guild_permissions, permission):
        await interaction.response.send_message("❌ You or I do not have the required moderation permission.", ephemeral=True)
        return

    duration_label = "Permanent" if action == "ban" else (f"{duration} minutes" if action == "timeout" else f"Invite sent in {rejoin_days} days")
    dm_sent = False
    try:
        if action in {"ban", "kick"}:
            dm_sent = await _dm_punishment(member, guild, action, reason, evidence, duration_label)
        if action == "ban":
            await member.ban(reason=f"{reason} | Evidence: {evidence} | Moderator: {moderator}")
        elif action == "kick":
            await member.kick(reason=f"{reason} | Evidence: {evidence} | Moderator: {moderator}")
            await _queue_rejoin_invite(guild, member.id, rejoin_days, reason)
        else:
            until = discord.utils.utcnow() + datetime.timedelta(minutes=duration)
            await member.timeout(until, reason=f"{reason} | Evidence: {evidence} | Moderator: {moderator}")
        moderation_cases_collection.insert_one({
            "guild_id": guild.id, "user_id": member.id, "moderator_id": moderator.id,
            "action": action, "reason": reason, "evidence": evidence,
            "duration": duration_label, "created_at": discord.utils.utcnow(),
        })
        past_tense = {"ban": "banned", "kick": "kicked", "timeout": "timed out"}[action]
        await send_mod_log(guild, f"{action.title()} issued", f"{member.mention} was {past_tense}.", 0xE74C3C,
            [("Moderator", moderator.mention, True), ("Reason", reason, False),
             ("Evidence", evidence, False), ("Duration", duration_label, True),
             ("DM delivered", "Yes" if dm_sent else "No / not required", True)],
            member.display_avatar.url)
        await _send_temporary_confirmation(interaction, f"✅ {member.mention} has been {past_tense}. This confirmation disappears in 60 seconds.")
    except discord.Forbidden:
        await interaction.response.send_message("❌ Discord denied that moderation action. Check my role and permissions.", ephemeral=True)
    except Exception as exc:
        print(f"[ERROR] moderation action failed: {exc}")
        await interaction.response.send_message("❌ The moderation action could not be completed.", ephemeral=True)


class ModerationModal(discord.ui.Modal):
    def __init__(self, action):
        super().__init__(title=f"{action.title()} member")
        self.action = action
        self.target = discord.ui.TextInput(label="Discord username or user ID", placeholder="Example: @name, username, or 123456789", max_length=100)
        self.reason = discord.ui.TextInput(label="Why / reason", placeholder="Required", style=discord.TextStyle.paragraph, max_length=500)
        self.evidence = discord.ui.TextInput(label="Evidence (optional)", placeholder="Message link, image link, or summary", required=False, style=discord.TextStyle.paragraph, max_length=1000)
        self.add_item(self.target)
        self.add_item(self.reason)
        self.add_item(self.evidence)
        if action == "timeout":
            self.duration = discord.ui.TextInput(label="Timeout length (minutes)", placeholder="1 to 40320", max_length=5)
            self.add_item(self.duration)
        elif action == "kick":
            self.rejoin_days = discord.ui.TextInput(label="Send new invite after (days)", placeholder="5 to 30", max_length=2)
            self.add_item(self.rejoin_days)

    async def on_submit(self, interaction):
        reason, evidence = self.reason.value.strip(), self.evidence.value.strip()
        member = _find_member(interaction.guild, self.target.value)
        if not member:
            await interaction.response.send_message("❌ I could not find that member. Use their exact username, mention, or user ID.", ephemeral=True)
            return
        if not reason:
            await interaction.response.send_message("❌ A reason is required.", ephemeral=True)
            return
        evidence = evidence or "Not provided"
        duration = rejoin_days = None
        try:
            if self.action == "timeout":
                duration = int(self.duration.value)
                if not 1 <= duration <= 40320:
                    raise ValueError
            elif self.action == "kick":
                rejoin_days = int(self.rejoin_days.value)
                if not 5 <= rejoin_days <= 30:
                    raise ValueError
        except ValueError:
            label = "Timeout length must be 1–40320 minutes." if self.action == "timeout" else "Rejoin delay must be 5–30 days."
            await interaction.response.send_message(f"❌ {label}", ephemeral=True)
            return
        await _perform_moderation(interaction, member, self.action, reason, evidence, duration, rejoin_days)


@bot.tree.command(name="ban", description="Ban a member using a reason and evidence form")
async def modal_ban(interaction: discord.Interaction):
    await interaction.response.send_modal(ModerationModal("ban"))


@bot.tree.command(name="kick", description="Kick a member using a reason and evidence form")
async def modal_kick(interaction: discord.Interaction):
    await interaction.response.send_modal(ModerationModal("kick"))


@bot.tree.command(name="mute", description="Mute a member using a reason and evidence form")
async def modal_mute(interaction: discord.Interaction):
    await interaction.response.send_modal(ModerationModal("timeout"))


class WarningReviewView(discord.ui.View):
    def __init__(self, guild_id, user_id):
        super().__init__(timeout=300)  # 5 minutes timeout
        self.guild_id, self.user_id = guild_id, user_id

    async def _allowed(self, interaction):
        if not interaction.user.guild_permissions.kick_members:
            await interaction.response.send_message("❌ Moderator permission required.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Ignore", style=discord.ButtonStyle.secondary)
    async def ignore(self, interaction, button):
        if not await self._allowed(interaction): return
        await interaction.response.send_message("Report marked as ignored.", ephemeral=True)

    @discord.ui.button(label="View mod", style=discord.ButtonStyle.primary)
    async def view_history(self, interaction, button):
        if not await self._allowed(interaction): return
        warnings = list(warnings_collection.find({"guild_id": self.guild_id, "user_id": self.user_id}).sort("created_at", -1).limit(10))
        history = "\n".join(f"• {item['reason']} — <@{item['moderator_id']}>" for item in warnings) or "No warning history found."
        await interaction.response.send_message(history[:1900], ephemeral=True)

    @discord.ui.button(label="Take action", style=discord.ButtonStyle.danger)
    async def take_action(self, interaction, button):
        if not await self._allowed(interaction): return
        member = interaction.guild.get_member(self.user_id)
        if not member:
            await interaction.response.send_message("❌ The member is no longer in the server.", ephemeral=True)
            return
        error = _moderation_target_allowed(interaction.guild, interaction.user, member)
        if error:
            await interaction.response.send_message(f"❌ {error}", ephemeral=True)
            return
        warnings = get_member_warnings(self.guild_id, self.user_id)
        if len(warnings) >= 3:
            await member.kick(reason=f"Third-warning escalation by {interaction.user}")
            await send_mod_log(interaction.guild, "Third-warning kick", f"{member.mention} was kicked after moderator review.", 0xE74C3C,
                [("Moderator", interaction.user.mention, True), ("Reason", "Third-warning escalation", False)])
            await interaction.response.send_message(f"✅ {member.mention} has been kicked.", ephemeral=True)
        elif len(warnings) >= 4:
            await member.ban(reason=f"Fourth-warning escalation by {interaction.user}")
            await send_mod_log(interaction.guild, "Fourth-warning ban", f"{member.mention} was banned after moderator review.", 0xE74C3C,
                [("Moderator", interaction.user.mention, True), ("Reason", "Fourth-warning escalation", False)])
            await interaction.response.send_message(f"✅ {member.mention} has been banned.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ The member does not have enough warnings to take action.", ephemeral=True)


def build_warning_embed(member, warning, number):
    """Create the compact yellow moderation card used for warning logs/history."""
    created_at = warning.get("created_at") or discord.utils.utcnow()
    embed = discord.Embed(
        title=f"Warning Issued {number}",
        description=(
            f"> **User:** {member.mention} (`{member.id}`)\n"
            f"> **Reason:** {warning.get('reason', 'No reason recorded')}\n"
            f"> **Duration:** Permanent\n"
            f"> **Warning:** #{number}"
        ),
        color=0xF1C40F,
        timestamp=created_at,
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=f"Issued by <@{warning.get('moderator_id', 'unknown')}> • Warning #{number}")
    return embed


async def send_warning_log(guild, member, warning, number):
    """Send a warning as a card rather than the generic moderation-log embed."""
    embed = discord.Embed(title="Warning Issued", color=0xE74C3C)
    embed.add_field(name="Member", value=member.mention, inline=True)
    embed.add_field(name="Moderator", value=f"<@{warning['moderator_id']}", inline=True)
    embed.add_field(name="Reason", value=warning['reason'], inline=False)
    embed.add_field(name="Warning Number", value=number, inline=True)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=f"Issued by <@{warning['moderator_id']}> • Warning #{number}")
    await send_mod_log(guild, "Warning Issued", embed=embed)
    try:
        log_channel_id, _ = load_config(guild.id)
        channel = guild.get_channel(int(log_channel_id)) if log_channel_id else None
        if channel:
            await channel.send(embed=build_warning_embed(member, warning, number))
            return True
    except Exception as exc:
        print(f"[ERROR] warning log: {exc}")
    return False


def get_member_warnings(guild_id, user_id):
    warnings = list(
        warnings_collection.find({"guild_id": guild_id, "user_id": user_id}).sort("created_at", 1)
    )
    for i, warning in enumerate(warnings):
        warning['warning_number'] = i + 1
    return warnings


class WarningListView(discord.ui.View):
    PAGE_SIZE = 3
    ERROR_COLOR = 0xE74C3C  # Red
    SUCCESS_COLOR = 0x2ECC71  # Green

    def __init__(self, member, page=0):
        super().__init__(timeout=300)
        self.member = member
        self.page = page
        self.logger = logging.getLogger(__name__)
        self._build_buttons()

    def _page_warnings(self):
        try:
            warnings = get_member_warnings(self.member.guild.id, self.member.id)
            pages = max(1, (len(warnings) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
            self.page = min(self.page, pages - 1)
            start = self.page * self.PAGE_SIZE
            return warnings, warnings[start:start + self.PAGE_SIZE], pages, start
        except Exception as e:
            self.logger.error(f"Error fetching warnings: {e!s}")
            raise

    def _build_buttons(self):
        try:
            warnings, visible, pages, start = self._page_warnings()
            if pages > 1:
                previous = discord.ui.Button(label="Previous", style=discord.ButtonStyle.secondary, disabled=self.page == 0)
                next_page = discord.ui.Button(label="Next", style=discord.ButtonStyle.secondary, disabled=self.page >= pages - 1)

                async def previous_callback(interaction):
                    try:
                        await self._change_page(interaction, self.page - 1)
                    except Exception as e:
                        self.logger.error(f"Error changing to previous page: {e!s}")
                        await interaction.response.send_message(f"❌ Error: {e!s}", ephemeral=True)

                async def next_callback(interaction):
                    try:
                        await self._change_page(interaction, self.page + 1)
                    except Exception as e:
                        self.logger.error(f"Error changing to next page: {e!s}")
                        await interaction.response.send_message(f"❌ Error: {e!s}", ephemeral=True)

                previous.callback = previous_callback
                next_page.callback = next_callback
                self.add_item(previous)
                self.add_item(next_page)

            for offset, warning in enumerate(visible):
                number = start + offset + 1
                button = discord.ui.Button(label=f"Delete #{number}", style=discord.ButtonStyle.danger)

                async def delete_callback(interaction, warning_id=warning["_id"], warning_number=number):
                    try:
                        await self._delete_warning(interaction, warning_id, warning_number)
                    except Exception as e:
                        self.logger.error(f"Error deleting warning: {e!s}")
                        await interaction.response.send_message(f"❌ Error: {e!s}", ephemeral=True)

                button.callback = delete_callback
                self.add_item(button)
        except Exception as e:
            self.logger.error(f"Error building buttons: {e!s}")
            raise

    async def _allowed(self, interaction):
        try:
            if not interaction.user.guild_permissions.kick_members:
                await interaction.response.send_message("❌ Moderator permission is required to delete warnings.", ephemeral=True)
                return False
            return True
        except Exception as e:
            self.logger.error(f"Error checking permissions: {e!s}")
            await interaction.response.send_message(f"❌ Error checking permissions: {e!s}", ephemeral=True)
            return False

    async def _change_page(self, interaction, new_page):
        try:
            if not await self._allowed(interaction): return
            self.page = new_page
            self.clear_items()
            self._build_buttons()
            await interaction.response.edit_message(embed=warning_list_embeds(self.member, self.page), view=self)
        except Exception as e:
            self.logger.error(f"Error changing page: {e!s}")
            await interaction.response.send_message(f"❌ Error changing page: {e!s}", ephemeral=True)

    async def _delete_warning(self, interaction, warning_id, warning_number):
        try:
            if not await self._allowed(interaction): return
            result = warnings_collection.delete_one({"_id": warning_id, "guild_id": self.member.guild.id, "user_id": self.member.id})
            if not result.deleted_count:
                await interaction.response.send_message("❌ That warning was already removed.", ephemeral=True)
                return
            await send_mod_log(
                interaction.guild, "Warning deleted", f"Warning #{warning_number} was removed for {self.member.mention}.", self.SUCCESS_COLOR,
                [("Moderator", interaction.user.mention, True)], self.member.display_avatar.url,
            )
            view = WarningListView(self.member, self.page)
            await interaction.response.edit_message(embeds=warning_list_embeds(self.member, view), view=view)
            await interaction.followup.send(f"✅ Warning #{warning_number} has been successfully deleted.", ephemeral=True)
        except Exception as e:
            self.logger.error(f"Error deleting warning: {e!s}")
            await interaction.response.send_message(f"❌ Error deleting warning: {e!s}", ephemeral=True)



def warning_list_embeds(member, view):
    warnings, visible, pages, start = view._page_warnings()
    if not visible:
        return [discord.Embed(title=f"Warnings for {member.display_name}", description="No active warnings.", color=0x2ECC71)]
    embeds = [build_warning_embed(member, warning, start + offset + 1) for offset, warning in enumerate(visible)]
    embeds[0].set_author(name=f"Warnings for {member} • {len(warnings)} total • Page {view.page + 1}/{pages}")
    return embeds


class WarningModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Warn member")
        self.target = discord.ui.TextInput(label="Discord username or user ID", placeholder="Example: @name, username, or 123456789", max_length=100)
        self.reason = discord.ui.TextInput(label="Reason", placeholder="Required", style=discord.TextStyle.paragraph, max_length=500)
        self.add_item(self.target)
        self.add_item(self.reason)

    async def on_submit(self, interaction):
        try:
            reason = self.reason.value.strip()
            if not reason:
                await interaction.response.send_message("❌ A warning reason is required.", ephemeral=True)
                return

            member = _find_member(interaction.guild, self.target.value)
            if not member:
                await interaction.response.send_message("❌ I could not find that member. Please try again with their exact username, mention, or user ID.", ephemeral=True)
                return

            # Check if the user is trying to warn themselves
            if member.id == interaction.user.id:
                await interaction.response.send_message("❌ You cannot warn yourself.", ephemeral=True)
                return

            # Check if the user is trying to warn a moderator
            if member.guild_permissions.kick_members:
                await interaction.response.send_message("❌ You cannot warn another moderator.", ephemeral=True)
                return

            # Check if the user is trying to warn the bot
            if member.bot:
                await interaction.response.send_message("❌ You cannot warn a bot.", ephemeral=True)
                return

            # Create the warning in the database
            warning = {
                "guild_id": interaction.guild.id,
                "user_id": member.id,
                "moderator_id": interaction.user.id,
                "reason": reason,
                "created_at": datetime.utcnow()
            }
            warnings_collection.insert_one(warning)

            # Get the warning number
            warnings = get_member_warnings(interaction.guild.id, member.id)
            warning_number = len(warnings)

            # Send the warning log
            await send_warning_log(interaction.guild, member, warning, warning_number)

            # Send confirmation message
            await interaction.response.send_message(f"✅ {member.mention} has been warned for: {reason}", ephemeral=True)

            # Check if the user has reached the warning threshold
            if warning_number >= 3:
                await member.kick(reason=f"Third-warning escalation by {interaction.user}")
                await send_mod_log(
                    interaction.guild, "Third-warning kick", f"{member.mention} was kicked after receiving 3 warnings.", 0xE74C3C,
                    [("Moderator", interaction.user.mention, True), ("Reason", "Third-warning escalation", False)]
                )
                await interaction.followup.send(f"✅ {member.mention} has been kicked for reaching 3 warnings.", ephemeral=True)
            elif warning_number >= 4:
                await member.ban(reason=f"Fourth-warning escalation by {interaction.user}")
                await send_mod_log(
                    interaction.guild, "Fourth-warning ban", f"{member.mention} was banned after receiving 4 warnings.", 0xE74C3C,
                    [("Moderator", interaction.user.mention, True), ("Reason", "Fourth-warning escalation", False)]
                )
                await interaction.followup.send(f"✅ {member.mention} has been banned for reaching 4 warnings.", ephemeral=True)

        except Exception as e:
            self.logger.error(f"Error in WarningModal: {e!s}")
            await interaction.response.send_message(f"❌ An error occurred while processing your warning: {e!s}", ephemeral=True)
        error = _moderation_target_allowed(interaction.guild, interaction.user, member)
        if error:
            await interaction.response.send_message(f"❌ {error}", ephemeral=True)
            return
        if not interaction.guild.me.guild_permissions.kick_members:
            await interaction.response.send_message("❌ I need Kick Members permission to manage warning escalations.", ephemeral=True)
            return
        warning = {"guild_id": interaction.guild.id, "user_id": member.id, "moderator_id": interaction.user.id, "reason": reason, "created_at": discord.utils.utcnow()}
        warnings_collection.insert_one(warning)
        count = warnings_collection.count_documents({"guild_id": interaction.guild.id, "user_id": member.id})
        await send_warning_log(interaction.guild, member, warning, count)
        if count == 3:
            await member.kick(reason=f"Automatic kick after 3 warnings: {reason}")
            await _queue_rejoin_invite(interaction.guild, member.id, 5, "Automatic rejoin after three warnings")
            await send_mod_log(interaction.guild, "Automatic warning kick", f"{member.mention} was kicked after three warnings.", 0xE67E22,
                [("Invite delay", "5 days", True)])
        elif count == 4:
            log_channel_id, _ = load_config(interaction.guild.id)
            channel = interaction.guild.get_channel(int(log_channel_id)) if log_channel_id else None
            if channel:
                report = discord.Embed(title="Fourth warning reported", description=f"{member.mention} needs moderator review.", color=0xE74C3C)
                report.add_field(name="Latest reason", value=reason, inline=False)
                await channel.send(embed=report, view=WarningReviewView(interaction.guild.id, member.id))
        await _send_temporary_confirmation(interaction, f"✅ Warning recorded for {member.mention} ({count}/4). This confirmation disappears in 60 seconds.")


@bot.tree.command(name="warn", description="Warn a member using a required reason form")
async def modal_warn(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.kick_members:
        await interaction.response.send_message("❌ Kick Members permission is required to warn members.", ephemeral=True)
        return
    await interaction.response.send_modal(WarningModal())


@bot.tree.command(name="warnings", description="View and manage a member's warnings")
@app_commands.describe(member="Member whose warnings to view")
async def slash_warnings(interaction: discord.Interaction, member: discord.Member):
    if not interaction.user.guild_permissions.kick_members:
        await interaction.response.send_message("❌ Kick Members permission is required to view warnings.", ephemeral=True)
        return
    view = WarningListView(member)
    await interaction.response.send_message(embeds=warning_list_embeds(member, view), view=view, ephemeral=True)


@bot.command(name="warnings", aliases=["warns"])
@commands.has_permissions(kick_members=True)
async def prefix_warnings(ctx, member: discord.Member = None):
    """View and manage a member's warning history."""
    if not member:
        await ctx.send("Usage: `bread warnings @member`")
        return
    view = WarningListView(member)
    await ctx.send(embeds=warning_list_embeds(member, view), view=view)


async def process_scheduled_invites():
    await bot.wait_until_ready()
    change_stream = scheduled_invites_collection.watch([
        {"$match": {
            "operationType": "insert",
            "fullDocument.status": "pending",
            "fullDocument.send_at": {"$lte": discord.utils.utcnow()}
        }}
    ])

    async for change in change_stream:
        item = change["fullDocument"]
        try:
            guild = bot.get_guild(item["guild_id"])
            user = bot.get_user(item["user_id"]) or await bot.fetch_user(item["user_id"])
            channel = next((c for c in guild.text_channels if c.permissions_for(guild.me).create_instant_invite), None) if guild else None
            if not channel:
                raise RuntimeError("No channel is available for creating an invite")
            invite = await channel.create_invite(max_age=604800, max_uses=1, reason="Scheduled moderation rejoin invite")
            await user.send(f"You may rejoin **{guild.name}**: {invite.url}")
            scheduled_invites_collection.update_one({"_id": item["_id"]}, {"$set": {"status": "sent", "sent_at": discord.utils.utcnow()}})
            await send_mod_log(guild, "Rejoin invite sent", f"A scheduled invite was sent to <@{item['user_id']}>.", 0x2ECC71)
        except Exception as exc:
            print(f"[ERROR] scheduled invite: {exc}")
            scheduled_invites_collection.update_one({"_id": item["_id"]}, {"$set": {"status": "failed", "error": str(exc)}})

@bot.event
async def on_member_join(member):
    """Handle new member joining the server"""
    try:
        await member.send(f"Welcome to the server {member.name}")
    except Exception as e:
        print(f"Failed to send DM to {member.name}: {e}")

    _, welcome_channel_id = load_config(member.guild.id)

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


@bot.event
async def on_message(message):
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
        guild_filter_words = load_filter_words(guild_id)
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
                        description=f"{message.author.mention} Dont use that word here!",
                        color=0xFF0000,
                    )
                    embed.set_footer(text="Message deleted by chat filter")
                    await message.channel.send(embed=embed, delete_after=5)

                    # Log all matched words
                    matched_words = "\n".join(f"||{word}||" for word in set(matches))

                    await send_mod_log(
                        guild=message.guild,
                        title="🚫 Message Filtered",
                        description=f"Message from {message.author.mention} was filtered.",
                        color=0xFF0000,
                        fields=[
                            ("User", f"{message.author} ({message.author.id})", True),
                            ("Channel", message.channel.mention, True),
                            ("Filtered Words", matched_words, True),
                        ],
                        thumbnail=(
                            message.author.avatar.url if message.author.avatar else None
                        ),
                    )
                    return
                except discord.Forbidden:
                    print(f"❌ No permission to delete message from {message.author}")
                except Exception as e:
                    print(f"❌ Error deleting message: {e}")

        await bot.process_commands(message)


@bot.event
async def on_command_error(ctx, error):
    """Give users a clear response when they use an unknown bread command."""
    if isinstance(error, commands.CommandNotFound):
        command_name = ctx.message.content.removeprefix("bread ").split(maxsplit=1)[0]
        await ctx.send(
            f"❌ Command `{command_name}` was not found. Use `bread help` to see available commands.",
            delete_after=15,
        )
        return
    print(f"[COMMAND ERROR] {error}")


@bot.tree.command(name="filter", description="Manage the chat filter")
@app_commands.describe(
    action="Action to perform", word="Word to add or remove from filter"
)
@app_commands.choices(
    action=[
        app_commands.Choice(name="add", value="add"),
        app_commands.Choice(name="remove", value="remove"),
        app_commands.Choice(name="list", value="list"),
        app_commands.Choice(name="reset", value="reset"),
        app_commands.Choice(name="status", value="status"),
    ]
)
async def filter_command(
    interaction: discord.Interaction, action: str, word: str = None
):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message(
            "❌ You need Administrator permissions to use this command!", ephemeral=True
        )
        return

    guild_id = interaction.guild_id

    if action == "add":
        if not word:
            await interaction.response.send_message(
                "❌ Please provide a word to add!", ephemeral=True
            )
            return

        word = word.lower()
        current_words = load_filter_words(guild_id)

        if word in current_words:
            await interaction.response.send_message(
                f"❌ `{word}` is already in the filter!", ephemeral=True
            )
            return

        current_words.append(word)
        save_filter_words(guild_id, current_words)

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

    elif action == "remove":
        if not word:
            await interaction.response.send_message(
                "❌ Please provide a word to remove!", ephemeral=True
            )
            return

        word = word.lower()
        current_words = load_filter_words(guild_id)

        if word not in current_words:
            await interaction.response.send_message(
                f"❌ `{word}` is not in the filter!", ephemeral=True
            )
            return

        current_words.remove(word)
        try:
            save_filter_words(guild_id, current_words)

            saved_words = load_filter_words(guild_id)
            if word not in saved_words:
                # Attempt to update the automod rule if one exists
                try:
                    existing_rule_id = load_automod_rule_id(guild_id)
                    log_channel_id, _ = load_config(guild_id)
                    alert_channel = int(log_channel_id) if log_channel_id else (int(LOG_CHANNEL_ID) if LOG_CHANNEL_ID else None)

                    if existing_rule_id:
                        updated = await _update_automod_rule_keywords_via_rest(
                            interaction.guild, existing_rule_id, saved_words, alert_channel
                        )
                        if updated:
                            automod_note = " (AutoMod rule updated)"
                        else:
                            automod_note = " (Failed to update AutoMod rule; check logs)"
                    else:
                        automod_note = ""
                except Exception as e:
                    print(f"[ERROR] updating automod after filter remove (slash): {e}")
                    automod_note = " (Error while attempting to update AutoMod rule)"

                embed = discord.Embed(
                    title="✅ Word Removed from Filter",
                    description=f"Removed `{word}` from the chat filter{automod_note}",
                    color=0xFF9900,
                )
                embed.add_field(
                    name="Total Filtered Words",
                    value=str(len(saved_words)),
                    inline=True,
                )
                embed.set_footer(text=f"Modified by {interaction.user.name}")
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(
                    "❌ Failed to save the word to the filter. Please try again.",
                    ephemeral=True,
                )

        except Exception as e:
            print(f"[ERROR] Error in filter remove: {e!s}")
            await interaction.response.send_message(
                f"❌ An error occurred while removing the word: {e!s}",
                ephemeral=True,
            )

    elif action == "list":
        current_words = load_filter_words(guild_id)

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

            embed = discord.Embed(
                title=f"📋 Filtered Words ({len(current_words)} total)",
                description="These words are being filtered in this server.",
                color=0x0099FF,
            )

            for i, chunk in enumerate(chunks, 1):
                word_list = "\n".join([f"• `{w}`" for w in chunk])
                embed.add_field(
                    name=f"Words {((i-1) * chunk_size) + 1}-{min(i * chunk_size, len(current_words))}",
                    value=word_list,
                    inline=False,
                )

        embed.set_footer(text=f"Requested by {interaction.user.name}")

        try:
            await interaction.user.send(embed=embed)
            await interaction.response.send_message(
                "📋 Filter list sent to your DMs!", ephemeral=True, delete_after=5
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I can't send you DMs! Please enable DMs from server members.",
                ephemeral=True,
            )

    elif action == "reset":
        old_words = load_filter_words(guild_id)
        old_count = len(old_words)

        reset_filter_words(guild_id)
        new_words = load_filter_words(guild_id)
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
        set_filter_enabled(guild_id, True)
        current_words = load_filter_words(guild_id)

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
        embed_disabled.set_footer(text=f"Disabled by {interaction.user.name}")

        # Attempt to update/delete any stored AutoMod rule to reflect the reset
        try:
            existing_rule_id = load_automod_rule_id(guild_id)
            log_channel_id, _ = load_config(guild_id)
            alert_channel = int(log_channel_id) if log_channel_id else (int(LOG_CHANNEL_ID) if LOG_CHANNEL_ID else None)

            if existing_rule_id:
                updated = await _update_automod_rule_keywords_via_rest(interaction.guild, existing_rule_id, current_words, alert_channel)
                if updated:
                    await send_mod_log(
                        guild=interaction.guild,
                        title="✅ AutoMod Updated",
                        description=f"AutoMod rule updated after filter reset; rule now has {len(current_words)} keywords.",
                        color=0x00FF00,
                    )
                else:
                    await send_mod_log(
                        guild=interaction.guild,
                        title="⚠️ AutoMod Update Failed",
                        description="Failed to update AutoMod rule after filter reset. Manual check recommended.",
                        color=0xFF9900,
                    )
        except Exception as e:
            print(f"[ERROR] updating automod after filter reset (slash): {e}")

    elif action == "status":
        current_words = load_filter_words(guild_id)
        enabled = _filter_cache[guild_id][0]
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
                "✅ Yes" if current_words == default_filter_words else "❌ No (Custom)"
            ),
            inline=True,
        )
        embed.set_footer(text=f"Requested by {interaction.user.name}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    else:
        await interaction.response.send_message(
            "❌ Invalid action! Use: `add`, `remove`, `list`, or `reset`",
            ephemeral=True,
        )


@bot.command()
@commands.has_permissions(manage_messages=True)
async def filter(ctx, action=None, *, word=None):
    # MongoDB-backed per-guild filter implementation (see slash /filter command for parity)
    # Ensure this is run in a guild
    if not ctx.guild:
        await ctx.send("❌ Prefix filter commands must be used in a server (not DMs).")
        return

    if not action:
        await ctx.send(
            "❌ Please specify an action: `add`, `remove`, `list`, or `reset`"
        )
        return

    action = action.lower()
    guild_id = ctx.guild.id

    # Load current guild-specific filter words from MongoDB
    current_words = load_filter_words(guild_id)

    if action == "add":
        if not word:
            await ctx.send("❌ Please provide a word to add!")
            return

        word = word.lower()
        if word in current_words:
            await ctx.send(f"❌ `{word}` is already in the filter!")
            return

        current_words.append(word)
        save_filter_words(guild_id, current_words)
        await ctx.send(f"✅ Added `{word}` to the filter!")

        # Log the filter addition
        await send_mod_log(
            guild=ctx.guild,
            title="🚫 Filter Word Added",
            description=f"`{word}` was added to the chat filter.",
            color=0xFF0000,
            fields=[
                ("Word", f"`{word}`", True),
                ("Moderator", ctx.author.mention, True),
                ("Total Words", str(len(current_words)), True),
            ],
        )

    elif action == "remove":
        if not word:
            await ctx.send("❌ Please provide a word to remove!")
            return

        word = word.lower()
        if word not in current_words:
            await ctx.send(f"❌ `{word}` is not in the filter!")
            return

        current_words.remove(word)
        save_filter_words(guild_id, current_words)
        await ctx.send(f"✅ Removed `{word}` from the filter!")

        # Attempt to update automod rule if present
        try:
            existing_rule_id = load_automod_rule_id(guild_id)
            log_channel_id, _ = load_config(guild_id)
            alert_channel = int(log_channel_id) if log_channel_id else (int(LOG_CHANNEL_ID) if LOG_CHANNEL_ID else None)

            if existing_rule_id:
                updated = await _update_automod_rule_keywords_via_rest(ctx.guild, existing_rule_id, current_words, alert_channel)
                if updated:
                    await ctx.send("ℹ️ AutoMod rule was updated to remove the word.")
                    await send_mod_log(
                        guild=ctx.guild,
                        title="✅ AutoMod Updated",
                        description=f"AutoMod rule updated after removing `{word}` from filter.",
                        color=0x00FF00,
                    )
                else:
                    await ctx.send("⚠️ Failed to update AutoMod rule. Check bot logs.")
                    await send_mod_log(
                        guild=ctx.guild,
                        title="⚠️ AutoMod Update Failed",
                        description=f"Failed to update AutoMod rule after removing `{word}` from filter. Manual check recommended.",
                        color=0xFF9900,
                    )
        except Exception as e:
            print(f"[ERROR] updating automod after filter remove (prefix): {e}")

    elif action == "list":
        if not current_words:
            await ctx.send("The filter is currently empty!")
            return

        # Split the list into chunks to avoid hitting embed field value limits
        chunk_size = 20
        chunks = [
            current_words[i : i + chunk_size]
            for i in range(0, len(current_words), chunk_size)
        ]

        embed = discord.Embed(
            title=f"🚫 Filtered Words ({len(current_words)} total)",
            color=0xFF0000,
        )

        for i, chunk in enumerate(chunks, 1):
            filter_list = "\n".join([f"• `{w}`" for w in chunk])
            embed.add_field(
                name=f"Words {((i - 1) * chunk_size) + 1}-{min(i * chunk_size, len(current_words))}",
                value=filter_list,
                inline=False,
            )

        embed.set_footer(text=f"Requested by {ctx.author}")

        try:
            await ctx.author.send(embed=embed)
            await ctx.send("📝 Filter list sent to your DMs!", delete_after=3)
        except discord.Forbidden:
            await ctx.send(
                "❌ I can't send you a DM! Please enable DMs from server members.",
                delete_after=5,
            )

        # Log the filter list view
        await send_mod_log(
            guild=ctx.guild,
            title="📋 Filter List Viewed",
            description=f"{ctx.author.mention} viewed the filter list.",
            color=0x3498DB,
            fields=[
                ("Total Words", str(len(current_words)), True),
                ("Moderator", ctx.author.mention, True),
            ],
        )

    elif action == "reset":
        # Reset filter words in DB and disable filter flag
        old_words = load_filter_words(guild_id)
        old_count = len(old_words)

        reset_filter_words(guild_id)
        new_words = load_filter_words(guild_id)
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

        # Attempt to update/delete any stored AutoMod rule to reflect the reset
        try:
            existing_rule_id = load_automod_rule_id(guild_id)
            log_channel_id, _ = load_config(guild_id)
            alert_channel = int(log_channel_id) if log_channel_id else (int(LOG_CHANNEL_ID) if LOG_CHANNEL_ID else None)

            if existing_rule_id:
                updated = await _update_automod_rule_keywords_via_rest(ctx.guild, existing_rule_id, new_words, alert_channel)
                if updated:
                    await ctx.send("ℹ️ AutoMod rule was updated to reflect the reset.")
                    await send_mod_log(
                        guild=ctx.guild,
                        title="✅ AutoMod Updated",
                        description=f"AutoMod rule updated after filter reset; rule now has {len(new_words)} keywords.",
                        color=0x00FF00,
                    )
                else:
                    await ctx.send("⚠️ Failed to update AutoMod rule after reset. Check bot logs.")
                    await send_mod_log(
                        guild=ctx.guild,
                        title="⚠️ AutoMod Update Failed",
                        description="Failed to update AutoMod rule after filter reset. Manual check recommended.",
                        color=0xFF9900,
                    )
        except Exception as e:
            print(f"[ERROR] updating automod after filter reset (prefix): {e}")

    else:
        await ctx.send("❌ Invalid action! Use: `add`, `remove`, `list`, or `reset`")
        return


@bot.command(
    name="setlog",
    aliases=["setlogchannel"],
    help="Set the log channel for moderation logs",
)
@commands.has_permissions(manage_channels = True)
async def setlog(ctx, channel: discord.TextChannel = None):
    """Set the log channel for moderation logs (prefix command)"""
    if not channel:
        channel = ctx.channel

    try:
        _, current_welcome = load_config(ctx.guild.id)

        save_config(
            guild_id=ctx.guild.id,
            log_channel=channel.id,
            welcome_channel=current_welcome,  # Keep existing welcome channel
        )
        global LOG_CHANNEL_ID
        LOG_CHANNEL_ID = channel.id

        await ctx.send(f"✅ Log channel set to {channel.mention}")

        await send_mod_log(
            guild=ctx.guild,
            title="🔧 Log Channel Set",
            description="Moderation logs will now be sent to this channel.",
            color=0x00FF00,
            fields=[
                ("Set by", ctx.author.mention, True),
                ("Channel", channel.mention, True),
            ],
        )

    except Exception as e:
        await ctx.send(f"❌ Error: {e!s}")


@bot.command(
    name="getchannels", aliases=["channels"], help="Show current channel configuration"
)
async def getchannels(ctx):
    """Show the current channel configuration (prefix command)"""
    try:
        log_channel_id, welcome_channel_id = load_config(ctx.guild.id)

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

        embed.set_footer(
            text=f"Requested by {ctx.author}", icon_url=ctx.author.display_avatar.url
        )

        await ctx.send(embed=embed)

    except Exception as e:
        await ctx.send(f"❌ Error: {e!s}")


@bot.tree.command(name="getchannels", description="Show current channel configuration")
async def get_channels(interaction: discord.Interaction):
    """Show the current channel configuration for this server"""
    try:
        log_channel_id, welcome_channel_id = load_config(interaction.guild_id)

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
        embed.set_footer(
            text=f"Requested by {interaction.user}",
            icon_url=interaction.user.display_avatar.url,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    except Exception as e:
        await interaction.response.send_message(
            f"❌ An error occurred: {e!s}", ephemeral=True
        )


@bot.command()
@commands.has_permissions(manage_messages=True)
async def purge(ctx, limit: int = 10, *, reason="No reason provided"):
    """Purge messages from the current channel (prefix command)"""
    if not ctx.guild.me.guild_permissions.manage_messages:
        await ctx.send("❌ I don't have permission to manage messages!")
        return

    if limit > 100:
        await ctx.send("❌ Maximum purge limit is 100 messages!")
        return

    try:
        deleted = await ctx.channel.purge(limit=limit + 1, before=ctx.message)
        deleted_count = len(deleted) - 1  # Exclude the command message

        message = await ctx.send(f"✅ Purged {deleted_count} messages!", delete_after=5)

        await send_mod_log(
            guild=ctx.guild,
            title="🗑️ Messages Purged",
            description=f"{deleted_count} messages were purged in {ctx.channel.mention}.",
            color=0x3498DB,
            fields=[
                ("Channel", ctx.channel.mention, True),
                ("Moderator", ctx.author.mention, True),
                ("Message Count", str(deleted_count), True),
                ("Reason", reason, False),
            ],
        )

    except discord.Forbidden:
        await ctx.send("❌ I don't have permission to manage messages in this channel!")
    except Exception as e:
        await ctx.send(f"❌ An error occurred: {e}")
        await send_mod_log(
            guild=ctx.guild,
            title="❌ Purge Failed",
            description=f"Failed to purge messages in {ctx.channel.mention}",
            color=0xFF0000,
            fields=[
                ("Error", str(e), False),
                ("Moderator", ctx.author.mention, True),
                ("Channel", ctx.channel.mention, True),
            ],
        )


@bot.command()
async def help(ctx, *, command_name=None):
    """Show help for bot commands"""
    if command_name:
        command = bot.get_command(command_name.lower())
        if not command:
            await ctx.send(
                f"❌ Command `{command_name}` not found! Use `bread help` to see all commands."
            )
            return

        embed = discord.Embed(
            title=f"🍞 Help: bread {command.name}",
            description=command.help or "No description available.",
            color=0x00FF00,
        )

        usage = f"`bread {command.name}`"
        if command.clean_params:
            params = []
            for name, param in command.clean_params.items():
                if param.default == param.empty:
                    params.append(f"<{name}>")
                else:
                    params.append(f"[{name}]")
            usage = f"`bread {command.name} {' '.join(params)}`"

        embed.add_field(name="Usage", value=usage, inline=False)

        # Add common examples
        examples = {
            "ban": "`bread ban @user Breaking rules`\n`bread ban @user 7d Spamming (bans for 7 days)`",
            "mute": "`bread mute @user 30 Spamming`\n`bread mute @user 1h Being rude`",
            "unmute": "`bread unmute @user`\n`bread unmute @user Time served`",
            "kick": "`bread kick @user Breaking rules`\n`bread kick @user Repeated warnings`",
            "purge": "`bread purge 50`\n`bread purge 10 Cleaning up`",
            "lock": "`bread lock #general`\n`bread lock #general Under maintenance`",
            "unlock": "`bread unlock #general`\n`bread unlock #general Maintenance complete`",
            "filter": "`bread filter add word`\n`bread filter remove word`\n`bread filter list`\n`bread filter reset`",
            "setlog": "`bread setlog #mod-logs`\n`bread setlog` (uses current channel)\nAlias: `setlogchannel`",
            "setwelcome": "`bread setwelcome #welcome`\n`bread setwelcome` (uses current channel)",
            "getchannels": "`bread getchannels`\n`bread channels` (alternative)",
            "setchannel": "`bread setchannel #log-channel #welcome-channel`\n`bread setchannel #log-channel` (set only log)\n`bread setchannel` (use current channel for both)",
            "setlogchannel": "Alias for `setlog`",
            "broadcast": "`bread broadcast Hello everyone!`\n`bread broadcast ping Important announcement!`",
        }

        if command.name in examples:
            embed.add_field(name="Examples", value=examples[command.name], inline=False)

        # Add required permissions if any
        if command.checks:
            perms = []
            if commands.has_permissions(administrator=True) in command.checks:
                perms.append("Administrator")
            if commands.has_permissions(manage_messages=True) in command.checks:
                perms.append("Manage Messages")
            if commands.has_permissions(manage_channels=True) in command.checks:
                perms.append("Manage Channels")
            if commands.has_permissions(ban_members=True) in command.checks:
                perms.append("Ban Members")
            if commands.has_permissions(kick_members=True) in command.checks:
                perms.append("Kick Members")
            if commands.has_permissions(moderate_members=True) in command.checks:
                perms.append("Moderate Members")

            if perms:
                embed.add_field(
                    name="Required Permissions", value=", ".join(perms), inline=False
                )

        await ctx.send(embed=embed)
        return

    # Create main help embed
    embed = discord.Embed(
        title="🍞 Bread Bot - Command Reference",
        description="**Available Commands** • Use `bread help <command>` to for detailed info",
        color=0x00FF00,
    )

    # Add bot avatar
    embed.set_thumbnail(url=ctx.bot.user.avatar.url if ctx.bot.user.avatar else None)

    # 🔹 GENERAL COMMANDS (always visible)
    general_commands = [
        ("hello", "Say hello to the bot"),
        ("me", "Show your Discord and server information"),
        ("status", "Display bot status and statistics"),
        ("help [command]", "Show this help or get help for a specific command"),
        ("dm <message>", "Send yourself a DM with the specified message"),
        ("getchannels", "Show current log and welcome channel settings"),
        ("channels", "Alias for getchannels"),
    ]

    general_text = "\n".join(
        [f"`bread {cmd}` - {desc}" for cmd, desc in general_commands]
    )
    embed.add_field(name="🔹 General Commands", value=general_text, inline=False)

    # Check user permissions
    has_mod_perms = any(
        [
            ctx.author.guild_permissions.moderate_members,
            ctx.author.guild_permissions.manage_roles,
            ctx.author.guild_permissions.manage_messages,
            ctx.author.guild_permissions.administrator,
        ]
    )

    # 🔨 MODERATION COMMANDS (for users with mod permissions)
    mod_commands = [
        ("ban @user [reason]", "Ban a user from the server"),
        ("unban user#1234 [reason]", "Unban a user"),
        ("kick @user [reason]", "Kick a user from the server"),
        ("mute @user [duration] [reason]", "Mute a user (default: 10m)"),
        ("unmute @user [reason]", "Unmute a user"),
        ("purge [amount] [reason]", "Delete messages (default: 10, max: 2000)"),
        ("filter <add|remove|list|reset> [word]", "Manage filtered words"),
        ("lock [#channel] [reason]", "Lock a channel (default: current)"),
        ("unlock [#channel] [reason]", "Unlock a channel"),
        ("setlog [#channel]", "Set log channel (default: current)"),
        ("setwelcome [#channel]", "Set welcome channel (default: current)"),
        ("setchannel [#log] [#welcome]", "Set both channels at once"),
    ]

    mod_text = "\n".join([f"`bread {cmd}` - {desc}" for cmd, desc in mod_commands])
    embed.add_field(name="🔨 Moderation Commands", value=mod_text, inline=False)

    # ⚙️ ADMIN COMMANDS (for administrators only)
    if ctx.author.guild_permissions.manage_messages:
        admin_commands = [
            (
                "filter <add/remove/list/reset> [word]",
                "Manage the automatic chat filter",
            ),
            ("setwelcome [#channel]", "Set welcome channel for new members"),
            ("setlogchannel [#channel]", "Set channel for moderation logs"),
            ("broadcast <message>", "Send a message to all text channels"),
        ]

        admin_text = "\n".join(
            [f"`bread {cmd}` - {desc}" for cmd, desc in admin_commands]
        )
        embed.add_field(name="⚙️ Admin Commands", value=admin_text, inline=False)

    # ⚡ SLASH COMMANDS INFO
    slash_info = (
        "**💡 Tip:** Most commands also work as slash commands!\n"
        "• Type `/` to see available slash commands\n"
        "• Example: `bread hello` = `/hello`"
    )
    embed.add_field(name="⚡ Slash Commands", value=slash_info, inline=False)

    # Footer with usage instructions
    permissions_note = ""
    if not has_mod_perms:
        permissions_note = " • 🔒 Some commands hidden (need permissions)"

    embed.set_footer(
        text=f"Use 'bread help <command>' for detailed info{permissions_note}"
    )

    await ctx.send(embed=embed)


@bot.command()
async def me(ctx):
    user = ctx.author
    member = ctx.guild.get_member(user.id)

    embed = discord.Embed(title=f"👤 {user.display_name}'s Info", color=0x00FF00)

    # User avatar
    embed.set_thumbnail(url=user.avatar.url if user.avatar else user.default_avatar.url)

    # Basic info
    embed.add_field(
        name="📋 Basic Info",
        value=f"**Username:** {user.name}\n**Display Name:** {user.display_name}\n**ID:** {user.id}",
        inline=False,
    )

    # Discord join date
    discord_join = user.created_at.strftime("%B %d, %Y at %I:%M %p")
    embed.add_field(name="📅 Discord Account Created", value=discord_join, inline=True)

    # Server join date
    if member and member.joined_at:
        server_join = member.joined_at.strftime("%B %d, %Y at %I:%M %p")
        embed.add_field(name="🏠 Joined This Server", value=server_join, inline=True)

    # Roles
    if member and member.roles:
        roles = [role.mention for role in member.roles if role.name != "@everyone"]
        if roles:
            roles_text = (
                ", ".join(roles)
                if len(roles) <= 10
                else f"{', '.join(roles[:10])}... (+{len(roles) - 10} more)"
            )
            embed.add_field(
                name=f"🎭 Roles ({len(roles)})", value=roles_text, inline=False
            )
        else:
            embed.add_field(name="🎭 Roles", value="No roles", inline=False)

    # Server permissions
    if member:
        perms = []
        if member.guild_permissions.administrator:
            perms.append("Administrator")
        if member.guild_permissions.kick_members:
            perms.append("Kick Members")
        if member.guild_permissions.ban_members:
            perms.append("Ban Members")
        if member.guild_permissions.manage_messages:
            perms.append("Manage Messages")

        if perms:
            embed.add_field(
                name="🔑 Key Permissions", value=", ".join(perms), inline=False
            )

    embed.set_footer(text=f"Requested by {user.name}")
    embed.timestamp = discord.utils.utcnow()

    await ctx.send(embed=embed)


@bot.tree.command(name="help", description="Show bot commands and usage")
@app_commands.describe(command="Specific command to get help for")
async def slash_help(interaction: discord.Interaction, command: str = None):
    admin_commands = [
        "broadcast",
        "kick",
        "ban",
        "mute",
        "unmute",
        "purge",
        "lock",
        "unlock",
        "filter",
        "setwelcome",
        "setlogchannel",
        "setchannel",
    ]

    if command:
        command = command.lower()

        # Permission check
        if command in admin_commands and not (
            interaction.user.guild_permissions.moderate_members
            or interaction.user.guild_permissions.manage_channels
            or interaction.user.guild_permissions.manage_roles
            or interaction.user.guild_permissions.manage_messages
            or interaction.user.guild_permissions.administrator
        ):
            await interaction.response.send_message(
                "❌ You don't have permission to view this command!", ephemeral=True
            )
            return

        # Command examples and descriptions
        command_info = {
            "hello": {
                "description": "Say hello to the bot",
                "usage": "`/hello` or `bread hello`",
                "example": "`/hello`\n`bread hello`",
            },
            "ping": {
                "description": "Check if the bot is responsive",
                "usage": "`/ping`",
                "example": "`/ping`",
            },
            "coin_toss": {
                "description": "Flip a coin",
                "usage": "`/coin_toss`",
                "example": "`/coin_toss`",
            },
            "test": {
                "description": "Test command to verify the bot is working",
                "usage": "`/test`",
                "example": "`/test`",
            },
            "me": {
                "description": "Show your Discord and server information",
                "usage": "`/me` or `bread me`",
                "example": "`/me`",
            },
            "status": {
                "description": "Show bot status and statistics",
                "usage": "`/status` or `bread status`",
                "example": "`/status`",
            },
            "kick": {
                "description": "Kick a member from the server",
                "usage": "`/kick member:<@user> [reason:<text>]` or `bread kick @user [reason]`",
                "example": "`/kick member:@user reason:Breaking rules`\n`bread kick @user Breaking rules`",
            },
            "ban": {
                "description": "Ban a member from the server",
                "usage": "`/ban member:<@user> [duration:<time>] [reason:<text>]` or `bread ban @user [duration] [reason]`",
                "example": "`/ban member:@user duration:7d reason:Breaking rules`\n`bread ban @user 7d Breaking rules`",
            },
            "unban": {
                "description": "Unban a user from the server",
                "usage": "`/unban user:<user_id> [reason:<text>]` or `bread unban userid [reason]`",
                "example": "`/unban user:1234567890 reason:Appealed ban`\n`bread unban 1234567890 Appealed ban`",
            },
            "mute": {
                "description": "Mute a member for a specified duration",
                "usage": "`/mute member:<@user> [duration:<minutes>] [reason:<text>]` or `bread mute @user [duration] [reason]`",
                "example": "`/mute member:@user duration:30 reason:Spamming`\n`bread mute @user 30 Spamming`",
            },
            "unmute": {
                "description": "Unmute a member",
                "usage": "`/unmute member:<@user> [reason:<text>]` or `bread unmute @user [reason]`",
                "example": "`/unmute member:@user reason:Time served`\n`bread unmute @user Time served`",
            },
            "purge": {
                "description": "Delete messages from the current channel",
                "usage": "`/purge [amount:<1-100>] [reason:<text>]` or `bread purge [amount] [reason]`",
                "example": "`/purge amount:50 reason:Cleaning up`\n`bread purge 50 Cleaning up`",
            },
            "lock": {
                "description": "Lock a channel to prevent members from sending messages",
                "usage": "`/lock [channel:<#channel>] [reason:<text>]` or `bread lock [#channel] [reason]`",
                "example": "`/lock channel:#general reason:Under maintenance`\n`bread lock #general Under maintenance`",
            },
            "unlock": {
                "description": "Unlock a previously locked channel",
                "usage": "`/unlock [channel:<#channel>] [reason:<text>]` or `bread unlock [#channel] [reason]`",
                "example": "`/unlock channel:#general reason:Maintenance complete`\n`bread unlock #general Maintenance complete`",
            },
            "filter": {
                "description": "Manage the chat filter (add/remove/list/reset words)",
                "usage": "`/filter action:<add/remove/list/reset> [word:<text>]` or `bread filter <action> [word]`",
                "example": "`/filter action:add word:badword`\n`bread filter add badword`",
            },
            "setwelcome": {
                "description": "Set the welcome channel for new members",
                "usage": "`/setwelcome [channel:<#channel>]` or `bread setwelcome [#channel]`",
                "example": "`/setwelcome channel:#welcome`\n`bread setwelcome #welcome`",
            },
            "setlogchannel": {
                "description": "Set the channel for moderation logs",
                "usage": "`/setlogchannel [channel:<#channel>]` or `bread setlogchannel [#channel]`",
                "example": "`/setlogchannel channel:#mod-logs`\n`bread setlogchannel #mod-logs`",
            },
            "setchannel": {
                "description": "Set both the log and welcome channels at once",
                "usage": "`/setchannel [log_channel:<#channel>] [welcome_channel:<#channel>]`",
                "example": "`/setchannel log_channel:#mod-logs welcome_channel:#welcome`",
            },
            "getchannels": {
                "description": "Show the current log and welcome channel configuration",
                "usage": "`/getchannels` or `bread getchannels`",
                "example": "`/getchannels`\n`bread getchannels`",
            },
            "broadcast": {
                "description": "Send a message to all channels in the server",
                "usage": "`/broadcast message:<text> [ping:<true/false>]` or `bread broadcast [message]`",
                               "example": "`/broadcast message:Server restart in 5 minutes ping:true`\n`bread broadcast ping Server restart in 5 minutes`",
            },
        }.get(command.lower())

        if not command_info:
            await interaction.response.send_message(
                "❌ Command not found!", ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"ℹ️ Help: /{command.lower()}",
            description=command_info["description"],
            color=0x00FF00,
        )

        # Add command usage and examples
        embed.add_field(name="Usage", value=command_info["usage"], inline=False)
        embed.add_field(name="Examples", value=command_info["example"], inline=False)

        # Add required permissions if any
        if command.lower() in ["filter", "setwelcome", "setlogchannel", "broadcast", "setchannel"]:
            embed.add_field(
                name="Required Permissions", value="Administrator", inline=False
            )
        elif command.lower() in [
            "kick",
            "ban",
            "mute",
            "unmute",
            "purge",
            "lock",
            "unlock",
        ]:
            embed.add_field(
                name="Required Permissions",
                value="Moderate Members, Manage Roles, or Manage Messages",
                inline=False,
            )

        await interaction.response.send_message(embed=embed)

        return

    # Main help command (no specific command requested)
    embed = discord.Embed(
        title="🍞 Bread Bot Commands",
        description="Here are all available commands. Use `/help <command>` for more info on a specific command.",
        color=0x00FF00,
    )

    # Add bot avatar
    embed.set_thumbnail(url=interaction.guild.me.avatar.url)

    # General Commands (always visible)
    general_commands = [
        ("/hello | bread hello", "Say hello to the bot"),
        ("/ping", "Check if the bot is responsive"),
        ("/coin_toss", "Flip a coin"),
        ("/me | bread me", "Show your Discord and server info"),
        ("/status | bread status", "Show bot status and statistics"),
        ("/getchannels | bread getchannels", "Show current log/welcome channel settings"),
        (
            "/help [command] | bread help [command]",
            "Show this help or get help for a specific command",
        ),
    ]

    # Format general commands
    general_text = "\n".join([f"`{cmd}` - {desc}" for cmd, desc in general_commands])

    # Add general commands section
    embed.add_field(name="🔹 General Commands", value=general_text, inline=False)

    # Check for mod permissions
    has_mod_perms = any(
        [
            interaction.user.guild_permissions.moderate_members,
            interaction.user.guild_permissions.manage_roles,
            interaction.user.guild_permissions.manage_messages,
            interaction.user.guild_permissions.administrator,
        ]
    )

    if has_mod_perms:
        # Moderation Commands
        mod_commands = [
            (
                "/kick @user [reason] | bread kick @user [reason]",
                "Kick a member from the server",
            ),
            (
                "/ban @user [duration] [reason] | bread ban @user [reason]",
                "Ban a member from the server",
            ),
            (
                "/unban userid [reason] | bread unban userid [reason]",
                "Unban a user by their ID",
            ),
            (
                "/mute @user [duration] [reason] | bread mute @user [duration] [reason]",
                "Mute a member for a specified duration",
            ),
            ("/unmute @user [reason] | bread unmute @user [reason]", "Unmute a member"),
            (
                "/purge [amount] [reason] | bread purge [amount] [reason]",
                "Delete messages (default: 10, max: 2000)",
            ),
            (
                "/lock [#channel] [reason] | bread lock [#channel] [reason]",
                "Lock a channel (default: current)",
            ),
            (
                "/unlock [#channel] [reason] | bread unlock [#channel] [reason]",
                "Unlock a channel",
            ),
        ]

        # Format moderation commands
        mod_text = "\n".join([f"`{cmd}` - {desc}" for cmd, desc in mod_commands])

        # Add moderation commands section
        embed.add_field(name="🔨 Moderation Commands", value=mod_text, inline=False)

    # Admin Commands (for users with admin permissions)
    if interaction.user.guild_permissions.administrator:
        admin_commands = [
            (
                "/filter <action> [word] | bread filter <action> [word]",
                "Manage the chat filter (add/remove/list/reset)",
            ),
            (
                "/setwelcome [#channel] | bread setwelcome [#channel]",
                "Set the welcome channel (current channel if none specified)",
            ),
            (
                "/setlogchannel [#channel] | bread setlogchannel [#channel]",
                "Set the log channel (current channel if none specified)",
            ),
            (
                "/broadcast [message] | bread broadcast [message]",
                "Send a message to all channels",
            ),
            (
                "/setchannel [#log] [#welcome]",
                "Set both log and welcome channels at once",
            ),
        ]

        # Format admin commands
        admin_text = "\n".join([f"`bread {cmd}` - {desc}" for cmd, desc in admin_commands])

        # Add admin commands section
        embed.add_field(name="⚙️ Admin Commands", value=admin_text, inline=False)

    # Add footer with usage instructions
    permissions_note = ""
    if not has_mod_perms:
        permissions_note = "\n🔒 Some commands are hidden. Ask a moderator for access."

    embed.set_footer(
        text=f"Use '/help <command>' or 'bread help <command>' for detailed help about a command.{permissions_note}"
    )

    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.command(name="setwelcome", help="Set the welcome channel")
@commands.has_permissions(manage_channels = True)
async def setwelcome(ctx, channel: discord.TextChannel = None):
    """Set the welcome channel for new members (prefix command)"""
    if not channel:
        channel = ctx.channel

    try:
        # Get current config
        current_log, _ = load_config(ctx.guild.id)

        # Save to MongoDB
        save_config(
            guild_id=ctx.guild.id,
            log_channel=current_log,  # Keep existing log channel
            welcome_channel=channel.id,
        )

        await ctx.send(f"✅ Welcome channel set to {channel.mention}")
    except Exception as e:
        await ctx.send(f"❌ Error: {e!s}")

    global WELCOME_CHANNEL_ID
    WELCOME_CHANNEL_ID = channel.id
    # Log the change to mod logs (non-fatal)
    try:
        await send_mod_log(
            guild=ctx.guild,
            title="🎉 Welcome Channel Set",
            description=f"Welcome channel set to {channel.mention} by {ctx.author.mention}",
            color=0x00FF00,
            fields=[
                ("Channel", channel.mention, True),
                ("Moderator", ctx.author.mention, True),
            ],
        )
    except Exception:
        pass


@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="No reason provided"):
    """Ban a member from the server (prefix command)"""
    await ctx.send("Use `/ban` so the required reason and evidence form is recorded.")
    return
    if not ctx.guild.me.guild_permissions.ban_members:
        await ctx.send("❌ I don't have permission to ban members!")
        return

    # Check if the target user is the command invoker
    if member == ctx.author:
        await ctx.send("❌ You can't ban yourself!")
        return

    # Check if the target user is the server owner
    if member == ctx.guild.owner:
        await ctx.send("❌ You can't ban the server owner!")
        return

    # Check if the target user has a higher role than the bot
    if member.top_role >= ctx.guild.me.top_role:
        await ctx.send("❌ I can't ban someone with a role higher or equal to mine!")
        return

    # Check if the target user has a higher role than the command invoker
    if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
        await ctx.send("❌ You can't ban someone with a role higher or equal to yours!")
        return

    try:
        # Send DM to the user before banning
        try:
            await member.send(
                f"You have been banned from **{ctx.guild.name}**\nReason: {reason}"
            )
        except:
            pass  # User has DMs disabled or blocked the bot

        # Ban the user
        await member.ban(
            reason=f"{reason} (banned by {ctx.author})", delete_message_days=7
        )

        # Send confirmation message
        await ctx.send(f"✅ {member.mention} has been banned!\nReason: {reason}")

        # Log the ban
        await send_mod_log(
            guild=ctx.guild,
            title="🔨 Member Banned",
            description=f"{member.mention} has been banned from the server.",
            color=0xFF0000,
            fields=[
                ("User", f"{member} ({member.id})", False),
                ("Moderator", ctx.author.mention, True),
                ("Reason", reason, True),
                (
                    "Account Created",
                    discord.utils.format_dt(member.created_at, "R"),
                    True,
                ),
            ],
            thumbnail=member.avatar.url if member.avatar else None,
        )
    except discord.Forbidden:
        await ctx.send("❌ I don't have permission to ban this member!")
    except Exception as e:
        await ctx.send(f"❌ An error occurred: {e}")
        # Log the error
        await send_mod_log(
            guild=ctx.guild,
            title="❌ Ban Failed",
            description=f"Failed to ban {member.mention}",
            color=0xFF0000,
            fields=[
                ("Error", str(e), False),
                ("Moderator", ctx.author.mention, True),
                ("Target", f"{member} ({member.id})", True),
            ],
        )


@bot.tree.command(name="status", description="Show bot status and statistics")
async def slash_status(interaction: discord.Interaction):
    """Show bot status and statistics (slash command)"""
    embed = discord.Embed(
        title="🤖 Bot Status Report", color=0x00FF00, timestamp=discord.utils.utcnow()
    )

    # Bot basic info with actual uptime
    uptime_text = (
        discord.utils.format_dt(bot_start_time, "R") if bot_start_time else "Unknown"
    )
    embed.add_field(
        name="🔧 Bot Info",
        value=f"**Status:** Online ✅\n**Latency:** {round(bot.latency * 1000)}ms\n**Online Since:** {uptime_text}",
        inline=False,
    )

    # Server info
    guild_count = len(bot.guilds)
    user_count = sum(guild.member_count for guild in bot.guilds)
    embed.add_field(
        name="📊 Server Stats",
        value=f"**Servers:** {guild_count}\n**Total Users:** {user_count:,}\n**Current Server:** {interaction.guild.name}",
        inline=True,
    )

    # Permissions check
    perms = interaction.guild.me.guild_permissions
    perm_status = (
        "✅"
        if all([perms.kick_members, perms.ban_members, perms.manage_messages])
        else "⚠️"
    )
    embed.add_field(
        name="🔑 Bot Permissions",
        value=f"**Kick Members:** {'✅' if perms.kick_members else '❌'}\n**Ban Members:** {'✅' if perms.ban_members else '❌'}\n**Manage Messages:** {'✅' if perms.manage_messages else '❌'}\n**Status:** {perm_status}",
        inline=False,
    )

    embed.set_footer(text=f"Requested by {interaction.user.name}")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="unmute", description="Unmute a member")
@app_commands.describe(member="The member to unmute", reason="Reason for unmuting")
async def slash_unmute(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str,
):
    """Unmute a member (slash command)"""
    # Check if user has moderate members permissions
    if not interaction.user.guild_permissions.moderate_members:
        await interaction.response.send_message(
            "❌ You need moderate members permissions to use this command!",
            ephemeral=True,
        )
        return

    # Check if bot has moderate members permissions
    if not interaction.guild.me.guild_permissions.moderate_members:
        await interaction.response.send_message(
            "❌ I don't have permission to unmute members!", ephemeral=True
        )
        return

    # Check if member is actually muted
    if not member.is_timed_out():
        await interaction.response.send_message(
            f"❌ {member.mention} is not muted!", ephemeral=True
        )
        return

    try:
        # Send DM to the user before unmuting
        try:
            await member.send(
                f"You have been unmuted in **{interaction.guild.name}**.\nReason: {reason}"
            )
        except:
            pass  # User has DMs disabled or blocked the bot

        # Remove the timeout
        await member.timeout(None, reason=f"{reason} (unmuted by {interaction.user})")

        # Send confirmation message
        await interaction.response.send_message(
            f"✅ {member.mention} has been unmuted!\nReason: {reason}"
        )

        # Log the unmute
        await send_mod_log(
            guild=interaction.guild,
            title="🔊 Member Unmuted",
            description=f"{member.mention} has been unmuted.",
            color=0x00FF00,
            fields=[
                ("User", f"{member} ({member.id})", False),
                ("Moderator", interaction.user.mention, True),
                ("Reason", reason, True),
                (
                    "Account Created",
                    discord.utils.format_dt(member.created_at, "R"),
                    True,
                ),
            ],
            thumbnail=member.avatar.url if member.avatar else None,
        )

    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ I don't have permission to unmute this member!", ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(
            f"❌ An error occurred: {e}", ephemeral=True
        )
        # Log the error
        await send_mod_log(
            guild=interaction.guild,
            title="❌ Unmute Failed",
            description=f"Failed to unmute {member.mention}",
            color=0xFF0000,
            fields=[
                ("Error", str(e), False),
                ("Moderator", interaction.user.mention, True),
                ("Target", f"{member} ({member.id})", True),
            ],
        )


@bot.tree.command(name="me", description="Show your Discord and server information")
async def slash_me(interaction: discord.Interaction):
    user = interaction.user
    member = interaction.guild.get_member(user.id)

    embed = discord.Embed(title=f"👤 {user.display_name}'s Info", color=0x00FF00)

    # User avatar
    embed.set_thumbnail(url=user.avatar.url if user.avatar else user.default_avatar.url)

    # Basic info
    embed.add_field(
        name="📋 Basic Info",
        value=f"**Username:** {user.name}\n**Display Name:** {user.display_name}\n**ID:** {user.id}",
        inline=False,
    )

    # Discord join date
    discord_join = user.created_at.strftime("%B %d, %Y at %I:%M %p")
    embed.add_field(name="📅 Discord Account Created", value=discord_join, inline=True)

    # Server join date
    if member and member.joined_at:
        server_join = member.joined_at.strftime("%B %d, %Y at %I:%M %p")
        embed.add_field(name="🏠 Joined This Server", value=server_join, inline=True)

    # Roles
    if member and member.roles:
        roles = [role.mention for role in member.roles if role.name != "@everyone"]
        if roles:
            roles_text = (
                ", ".join(roles)
                if len(roles) <= 10
                else f"{', '.join(roles[:10])}... (+{len(roles) - 10} more)"
            )
            embed.add_field(
                name=f"🎭 Roles ({len(roles)})", value=roles_text, inline=False
            )
        else:
            embed.add_field(name="🎭 Roles", value="No roles", inline=False)

    # Server permissions
    if member:
        perms = []
        if member.guild_permissions.administrator:
            perms.append("Administrator")
        if member.guild_permissions.kick_members:
            perms.append("Kick Members")
        if member.guild_permissions.ban_members:
            perms.append("Ban Members")
        if member.guild_permissions.manage_messages:
            perms.append("Manage Messages")

        if perms:
            embed.add_field(
                name="🔑 Key Permissions", value=", ".join(perms), inline=False
            )

    embed.set_footer(text=f"Requested by {user.name}")
    embed.timestamp = discord.utils.utcnow()

    await interaction.response.send_message(embed=embed)


@bot.command()
async def status(ctx):
    embed = discord.Embed(
        title="🤖 Bot Status Report", color=0x00FF00, timestamp=discord.utils.utcnow()
    )

    # Bot basic info with actual uptime
    uptime_text = (
        discord.utils.format_dt(bot_start_time, "R") if bot_start_time else "Unknown"
    )
    embed.add_field(
        name="🔧 Bot Info",
        value=f"**Status:** Online ✅\n**Latency:** {round(bot.latency * 1000)}ms\n**Online Since:** {uptime_text}",
        inline=False,
    )

    # Server info
    guild_count = len(bot.guilds)
    member_count = sum(guild.member_count for guild in bot.guilds)
    embed.add_field(
        name="📊 Server Stats",
        value=f"**Servers:** {guild_count}\n**Total Members:** {member_count}\n**Current Server:** {ctx.guild.name}",
        inline=True,
    )

    # Commands status
    slash_commands = len(bot.tree.get_commands())
    prefix_commands = len([cmd for cmd in bot.commands if not cmd.hidden])
    embed.add_field(
        name="⚡ Commands",
        value=f"**Slash Commands:** {slash_commands}\n**Prefix Commands:** {prefix_commands}\n**All Working:** ✅",
        inline=True,
    )

    # Permissions check
    perms = ctx.guild.me.guild_permissions
    perm_status = (
        "✅"
        if all([perms.kick_members, perms.ban_members, perms.manage_messages])
        else "⚠️"
    )
    embed.add_field(
        name="🔑 Bot Permissions",
        value=f"**Kick Members:** {'✅' if perms.kick_members else '❌'}\n**Ban Members:** {'✅' if perms.ban_members else '❌'}\n**Manage Messages:** {'✅' if perms.manage_messages else '❌'}\n**Status:** {perm_status}",
        inline=False,
    )

    embed.set_footer(text=f"Requested by {ctx.author.name}")
    await ctx.send(embed=embed)


@bot.tree.command(
    name="lock", description="Lock a channel to prevent members from sending messages"
)
@app_commands.describe(
    channel="Channel to lock (current channel if not specified)",
    reason="Reason for locking",
)
async def lock(
    interaction: discord.Interaction,
    channel: discord.TextChannel = None,
    reason: str = "No reason provided",
):
    if not interaction.user.guild_permissions.manage_channels:
        await interaction.response.send_message(
            "❌ You need Manage Channels permissions to use this command!",
            ephemeral=True,
        )
        return

    if not interaction.guild.me.guild_permissions.manage_channels:
        await interaction.response.send_message(
            "❌ I don't have permission to manage channels!", ephemeral=True
        )
        return

    # Use current channel if none specified
    target_channel = channel or interaction.channel

    try:
        # Get @everyone role
        everyone_role = interaction.guild.default_role

        # Remove send messages permission for @everyone
        await target_channel.set_permissions(
            everyone_role, send_messages=False, reason=reason
        )

        embed = discord.Embed(
            title="🔒 Channel Locked",
            description=f"{target_channel.mention} has been locked!",
            color=0xFF0000,
        )
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Locked by", value=interaction.user.mention, inline=True)

        await interaction.response.send_message(embed=embed)

        # Log the channel lock to mod logs
        try:
            await send_mod_log(
                guild=interaction.guild,
                title="🔒 Channel Locked",
                description=f"{target_channel.mention} was locked by {interaction.user.mention}",
                color=0xFF0000,
                fields=[
                    ("Channel", target_channel.mention, True),
                    ("Moderator", interaction.user.mention, True),
                    ("Reason", reason or "No reason provided", False),
                ],
            )
        except Exception:
            pass

    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ I don't have permission to modify this channel!", ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(
            f"❌ An error occurred: {e}", ephemeral=True
        )


@bot.tree.command(
    name="unlock", description="Unlock a channel to allow members to send messages"
)
@app_commands.describe(
    channel="Channel to unlock (current channel if not specified)",
    reason="Reason for unlocking",
)
async def unlock(
    interaction: discord.Interaction,
    channel: discord.TextChannel = None,
    reason: str = "No reason provided",
):
    if not interaction.user.guild_permissions.manage_channels:
        await interaction.response.send_message(
            "❌ You need Manage Channels permissions to use this command!",
            ephemeral=True,
        )
        return

    if not interaction.guild.me.guild_permissions.manage_channels:
        await interaction.response.send_message(
            "❌ I don't have permission to manage channels!", ephemeral=True
        )
        return

    # Use current channel if none specified
    target_channel = channel or interaction.channel

    try:
        # Get @everyone role
        everyone_role = interaction.guild.default_role

        # Restore send messages permission for @everyone (set to None = inherit)
        await target_channel.set_permissions(
            everyone_role, send_messages=None, reason=reason
        )

        embed = discord.Embed(
            title="🔓 Channel Unlocked",
            description=f"{target_channel.mention} has been unlocked!",
            color=0x00FF00,
        )
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Unlocked by", value=interaction.user.mention, inline=True)

        await interaction.response.send_message(embed=embed)

    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ I don't have permission to modify this channel!", ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(
            f"❌ An error occurred: {e}", ephemeral=True
        )
        return


@bot.command()
async def dm(ctx, *, message: str = None):
    if not message:
        await ctx.send("❌ Please provide a message to DM yourself!")
        return
    try:
        await ctx.author.send(message)
        await ctx.send("✅ DM sent!", delete_after=3)
    except discord.Forbidden:
        await ctx.send(
            "❌ I can't send you a DM! Please enable DMs from server members.",
            delete_after=5,
        )
        return


@bot.command()
@commands.has_permissions(ban_members=True)
async def unban(ctx, user: discord.User, *, reason="No reason provided"):
    if not ctx.guild.me.guild_permissions.ban_members:
        await ctx.send("❌ I don't have permission to unban members!")
        return

    try:
        await ctx.guild.unban(user, reason=reason)
        await ctx.send(f"✅ {user.mention} has been unbanned!\nReason: {reason}")
        # Log the unban to mod logs
        try:
            await send_mod_log(
                guild=ctx.guild,
                title="🔓 Member Unbanned",
                description=f"{user.mention} was unbanned by {ctx.author.mention}",
                color=0x00FF00,
                fields=[
                    ("User", f"{user} ({user.id})", False),
                    ("Moderator", ctx.author.mention, True),
                    ("Reason", reason, True),
                ],
            )
        except Exception:
            pass
    except discord.NotFound:
        await ctx.send("❌ This user is not banned!")
    except discord.Forbidden:
        await ctx.send("❌ I don't have permission to unban this user!")
    except Exception as e:
        await ctx.send(f"❌ An error occurred: {e}")


@bot.command()
@commands.has_permissions(moderate_members=True)
async def unmute(ctx, member: discord.Member, *, reason="No reason provided"):
    """Unmute a member (prefix command)"""
    if not ctx.guild.me.guild_permissions.moderate_members:
        await ctx.send("❌ I don't have permission to unmute members!")
        return

    # Check if member is actually muted
    if not member.is_timed_out():
        await ctx.send(f"❌ {member.mention} is not muted!")
        return

    try:
        # Send DM to the user before unmuting
        try:
            await member.send(
                f"You have been unmuted in **{ctx.guild.name}**.\nReason: {reason}"
            )
        except:
            pass  # User has DMs disabled or blocked the bot

        # Remove the timeout
        await member.timeout(None, reason=f"{reason} (unmuted by {ctx.author})")

        # Send confirmation message
        await ctx.send(f"✅ {member.mention} has been unmuted!\nReason: {reason}")

        # Log the unmute
        await send_mod_log(
            guild=ctx.guild,
            title="🔊 Member Unmuted",
            description=f"{member.mention} has been unmuted.",
            color=0x00FF00,
            fields=[
                ("User", f"{member} ({member.id})", False),
                ("Moderator", ctx.author.mention, True),
                ("Reason", reason, True),
                (
                    "Account Created",
                    discord.utils.format_dt(member.created_at, "R"),
                    True,
                ),
            ],
            thumbnail=member.avatar.url if member.avatar else None,
        )

    except discord.Forbidden:
        await ctx.send("❌ I don't have permission to unmute this member!")
    except Exception as e:
        await ctx.send(f"❌ An error occurred: {e}")
        # Log the error
        await send_mod_log(
            guild=ctx.guild,
            title="❌ Unmute Failed",
            description=f"Failed to unmute {member.mention}",
            color=0xFF0000,
            fields=[
                ("Error", str(e), False),
                ("Moderator", ctx.author.mention, True),
                ("Target", f"{member} ({member.id})", True),
            ],
        )


@bot.command()
@commands.has_permissions(manage_channels=True)
async def lock(
    ctx, channel: discord.TextChannel = None, *, reason="No reason provided"
):
    """Lock a channel to prevent members from sending messages (prefix command)"""
    if not ctx.guild.me.guild_permissions.manage_channels:
        await ctx.send("❌ I don't have permission to manage channels!")
        return

    target_channel = channel or ctx.channel

    try:
        everyone_role = ctx.guild.default_role
        current_perms = target_channel.overwrites_for(everyone_role)

        if current_perms.send_messages is False:
            await ctx.send(f"❌ {target_channel.mention} is already locked!")
            return

        previous_send_messages = current_perms.send_messages

        await target_channel.set_permissions(
            everyone_role,
            send_messages=False,
            reason=f"{reason} (locked by {ctx.author})",
        )

        embed = discord.Embed(
            title="🔒 Channel Locked",
            description=f"{target_channel.mention} has been locked!",
            color=0xFF0000,
        )
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Locked by", value=ctx.author.mention, inline=True)
        await ctx.send(embed=embed)

        await send_mod_log(
            guild=ctx.guild,
            title="🔒 Channel Locked",
            description=f"{target_channel.mention} has been locked.",
            color=0xFF0000,
            fields=[
                ("Channel", target_channel.mention, True),
                ("Moderator", ctx.author.mention, True),
                ("Reason", reason, False),
                (
                    "Previous Setting",
                    (
                        "Allowed"
                        if previous_send_messages is None
                        else str(previous_send_messages)
                    ),
                    True,
                ),
            ],
        )

    except discord.Forbidden:
        await ctx.send("❌ I don't have permission to modify this channel!")
        await send_mod_log(
            guild=ctx.guild,
            title="❌ Channel Lock Failed",
            description=f"Failed to lock {target_channel.mention}",
            color=0xFF0000,
            fields=[
                ("Error", "Insufficient permissions", False),
                ("Moderator", ctx.author.mention, True),
                ("Channel", target_channel.mention, True),
            ],
        )
    except Exception as e:
        await ctx.send(f"❌ An error occurred: {e}")
        await send_mod_log(
            guild=ctx.guild,
            title="❌ Channel Lock Failed",
            description=f"Failed to lock {target_channel.mention}",
            color=0xFF0000,
            fields=[
                ("Error", str(e), False),
                ("Moderator", ctx.author.mention, True),
                ("Channel", target_channel.mention, True),
            ],
        )


@bot.command()
@commands.has_permissions(manage_channels=True)
async def unlock(
    ctx, channel: discord.TextChannel = None, *, reason="No reason provided"
):
    """Unlock a previously locked channel (prefix command)"""
    if not ctx.guild.me.guild_permissions.manage_channels:
        await ctx.send("❌ I don't have permission to manage channels!")
        return
    target_channel = channel or ctx.channel
    try:
        everyone_role = ctx.guild.default_role
        current_perms = target_channel.overwrites_for(everyone_role)

        if current_perms.send_messages is None or current_perms.send_messages is True:
            await ctx.send(f"ℹ️ {target_channel.mention} is already unlocked!")
            return

        previous_send_messages = current_perms.send_messages

        if current_perms.is_empty():
            await target_channel.set_permissions(
                everyone_role,
                overwrite=None,
                reason=f"{reason} (unlocked by {ctx.author})",
            )
        else:

            await target_channel.set_permissions(
                everyone_role,
                send_messages=None,
                reason=f"{reason} (unlocked by {ctx.author})",
            )


        embed = discord.Embed(
            title="🔓 Channel Unlocked",
            description=f"{target_channel.mention} has been unlocked!",
            color=0x00FF00,
        )
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Unlocked by", value=ctx.author.mention, inline=True)
        await ctx.send(embed=embed)


        await send_mod_log(
            guild=ctx.guild,
            title="🔓 Channel Unlocked",
            description=f"{target_channel.mention} has been unlocked.",
            color=0x00FF00,
            fields=[
                ("Channel", target_channel.mention, True),
                ("Moderator", ctx.author.mention, True),
                ("Reason", reason, False),
                (
                    "Previous Setting",
                    (
                        "Locked"
                        if previous_send_messages is False
                        else str(previous_send_messages)
                    ),
                    True,
                ),
            ],
        )

    except discord.Forbidden:
        await ctx.send("❌ I don't have permission to modify this channel!")
        await send_mod_log(
            guild=ctx.guild,
            title="❌ Channel Unlock Failed",
            description=f"Failed to unlock {target_channel.mention}",
            color=0xFF0000,
            fields=[
                ("Error", "Insufficient permissions", False),
                ("Moderator", ctx.author.mention, True),
                ("Channel", target_channel.mention, True),
            ],
        )
    except Exception as e:
        await ctx.send(f"❌ An error occurred: {e}")
        await send_mod_log(
            guild=ctx.guild,
            title="❌ Channel Unlock Failed",
            description=f"Failed to unlock {target_channel.mention}",
            color=0xFF0000,
            fields=[
                ("Error", str(e), False),
                ("Moderator", ctx.author.mention, True),
                ("Channel", target_channel.mention, True),
            ],
        )


@bot.command()
@commands.is_owner()
async def lalala(ctx):


    await ctx.send(
        "Are you really sure you want to shutdown? Reply with `yes` within 15 seconds. No more tacos :("
    )

    def check(m):
        return (
            m.author == ctx.author
            and m.channel == ctx.channel
            and m.content.lower() == "yes"
        )

    try:
        msg = await bot.wait_for("message", timeout=15.0, check=check)
        await ctx.send("Shutting down...")
        await bot.close()
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except asyncio.TimeoutError:
        await ctx.send("Shutdown cancelled (no confirmation received).")
    except Exception as e:
        await ctx.send(f"❌ Error during shutdown: {e}")


if __name__ == "__main__":
    if not token:
        raise RuntimeError("DISCORD_TOKEN is not set")
    check_mongodb_connection()
    flask_thread = start_flask_thread()
    bot.run(token, log_handler=handler, log_level=logging.INFO)
    print("Hello World")
