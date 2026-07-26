"""
Bread Bot - Main initialization file
"""
import discord
from discord.ext import commands
import logging
import os
import sys
import threading
from flask import Flask
import aiohttp
import asyncio

from config import DISCORD_TOKEN, BOT_OWNER_ID, FLASK_PORT

# Initialize Flask app
app = Flask(__name__)


def run_flask():
    """Run Flask server for health checks"""
    port = int(os.environ.get("PORT", FLASK_PORT))
    # Try to find an available port if the default is in use
    if port == 5000:
        import socket
        test_port = 5000
        while test_port < 5100:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(('0.0.0.0', test_port))
                    port = test_port
                    break
            except OSError:
                test_port += 1
                continue
            break
    app.run(host="0.0.0.0", port=port, use_reloader=False)


def start_flask_thread():
    """Start Flask server in a background thread"""
    thread = threading.Thread(target=run_flask, daemon=True, name="flask-health-server")
    thread.start()
    return thread


@app.route("/")
def home():
    return "Bread Bot is running! \ud83c\udf5e"


@app.route("/health")
def health():
    return {"status": "healthy", "bot": "online"}


# Set up logging
handler = logging.FileHandler(filename="discord.log", encoding="utf-8", mode="a")

# Set up bot intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True


class BreadBot(commands.Bot):
    """Custom bot class with setup hook"""
    
    async def setup_hook(self):
        """Setup hook for bot initialization"""
        from events.events import (
            on_message, on_member_join,
            setup_hook as events_setup_hook
        )
        
        # Call events setup_hook
        await events_setup_hook(self)
        
        # Register event listeners
        self.add_listener(on_message, "on_message")
        self.add_listener(on_member_join, "on_member_join")
        
        print("Bot setup complete!")


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
async def load_cogs():
    """Load all cogs"""
    cog_files = [
        "cogs.utilities",
        "cogs.admin",
        "cogs.moderation",
        "cogs.nasa",
    ]
    
    for cog in cog_files:
        try:
            await bot.load_extension(cog)
            print(f"\u2705 Loaded cog: {cog}")
        except Exception as e:
            print(f"\u274c Failed to load cog {cog}: {e}")


# Ready event
@bot.event
async def on_ready():
    """Called when the bot is ready"""
    global bot_start_time
    if bot_start_time is None:
        bot_start_time = discord.utils.utcnow()

    print(f"We are ready to go in, {bot.user.name}")
    print(f"Bot ID: {bot.user.id}")
    
    # Start background tasks after bot is ready
    from events.events import keep_alive_task, process_scheduled_invites
    bot.background_task = asyncio.create_task(keep_alive_task(bot))
    bot.scheduled_invite_task = asyncio.create_task(process_scheduled_invites(bot))
    
    try:
        from utils.database import check_mongodb_connection, debug_db
        await check_mongodb_connection()
        await debug_db()
    except Exception as e:
        print(f"\u274c Database check failed: {e}")


# Guild remove event
@bot.event
async def on_guild_remove(guild):
    """Clean up when bot leaves a guild"""
    from events.events import on_guild_remove as events_on_guild_remove
    await events_on_guild_remove(guild)


# Start the bot
if __name__ == "__main__":
    # Check if token is set
    if not DISCORD_TOKEN or DISCORD_TOKEN == "None":
        print("\u274c ERROR: DISCORD_TOKEN is not set!")
        print("Please create a .env file with your Discord bot token.")
        print("Example:")
        print("  DISCORD_TOKEN=your_bot_token_here")
        print("\nYou can copy .env.example to .env and fill in the values.")
        sys.exit(1)
    
    # Start Flask thread
    start_flask_thread()
    
    # Run async main
    async def main():
        await load_cogs()
        try:
            await bot.start(DISCORD_TOKEN)
        except KeyboardInterrupt:
            print("\nBot shutting down...")
            sys.exit(0)
        except Exception as e:
            print(f"\u274c Error running bot: {e}")
            sys.exit(1)
    
    asyncio.run(main())
