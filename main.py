"""
Bread Bot - Main initialization file
"""
import discord
from discord.ext import commands
import logging
import os
import sys
import threading
import asyncio
from flask import Flask
import aiohttp

from config import DISCORD_TOKEN, BOT_OWNER_ID, FLASK_PORT

# Initialize Flask app
app = Flask(__name__)


class BreadBot(commands.Bot):
    """Custom bot class with setup_hook"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aiohttp_session = None
        self.background_task = None
        self.scheduled_invite_task = None
    
    async def setup_hook(self):
        """Setup hook for bot initialization"""
        from events.events import (
            keep_alive_task, process_scheduled_invites, on_message, on_member_join,
            setup_hook as events_setup_hook
        )
        
        # Set up aiohttp session
        self.aiohttp_session = aiohttp.ClientSession()
        
        # Start background tasks
        self.background_task = asyncio.create_task(keep_alive_task(self))
        self.scheduled_invite_task = asyncio.create_task(process_scheduled_invites(self))
        
        # Register event listeners
        self.add_listener(on_message, "on_message")
        self.add_listener(on_member_join, "on_member_join")
        
        # Call events setup_hook
        await events_setup_hook(self)
        
        print("Syncing application commands...")
        await self.tree.sync()


def run_flask():
    """Run Flask server for health checks"""
    port = int(os.environ.get("PORT", FLASK_PORT))
    app.run(host="0.0.0.0", port=port, use_reloader=False)


def start_flask_thread():
    """Start Flask server in a background thread"""
    thread = threading.Thread(target=run_flask, daemon=True, name="flask-health-server")
    thread.start()
    return thread


@app.route("/")
def home():
    return "Bread Bot is running! 🍞"


@app.route("/health")
def health():
    return {"status": "healthy", "bot": "online"}


# Set up logging
handler = logging.FileHandler(filename="discord.log", encoding="utf-8", mode="a")

# Set up bot intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# Initialize bot
bot = BreadBot(command_prefix="bread ", intents=intents, help_command=None)

# Set bot owner ID if configured
try:
    if BOT_OWNER_ID:
        bot.owner_id = int(BOT_OWNER_ID)
except Exception:
    pass

# Global variables for channel IDs (will be set by commands)
LOG_CHANNEL_ID = None
WELCOME_CHANNEL_ID = None
bot_start_time = None


# Load cogs
def load_cogs():
    """Load all cogs"""
    cog_files = [
        "cogs.utilities",
        "cogs.admin",
        "cogs.moderation",
        "cogs.nasa",
    ]
    
    for cog in cog_files:
        try:
            bot.load_extension(cog)
            print(f"✅ Loaded cog: {cog}")
        except Exception as e:
            print(f"❌ Failed to load cog {cog}: {e}")


# Ready event
@bot.event
async def on_ready():
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


# Guild remove event
@bot.event
async def on_guild_remove(guild):
    """Clean up when bot leaves a guild"""
    from events.events import on_guild_remove as events_on_guild_remove
    await events_on_guild_remove(guild)


# Start the bot
if __name__ == "__main__":
    # Start Flask thread
    start_flask_thread()
    
    # Load cogs
    load_cogs()
    
    # Run bot
    try:
        bot.run(DISCORD_TOKEN)
    except KeyboardInterrupt:
        print("\nBot shutting down...")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Error running bot: {e}")
        sys.exit(1)
