"""
Configuration and environment variables for Bread Bot
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# MongoDB Configuration
MONGO_USER = os.getenv("MONGO_USER")
MONGO_PASS = os.getenv("MONGO_PASS")
MONGO_DB = os.getenv("MONGO_DB")
MONGO_HOST = os.getenv("MONGO_HOST")

# Construct MongoDB URI
MONGO_URI = f"mongodb+srv://{MONGO_USER}:{MONGO_PASS}@{MONGO_HOST}/{MONGO_DB}?retryWrites=true&w=majority"

# Discord Configuration
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
BOT_OWNER_ID = os.getenv("BOT_OWNER_ID")
DISCORD_GUILD_ID = os.getenv("DISCORD_GUILD_ID")

# Channel IDs
LOG_CHANNEL_ID = os.getenv("LOG_CHANNEL_ID")
WELCOME_CHANNEL_ID = os.getenv("WELCOME_CHANNEL_ID")
TIME_ID = int(os.getenv("TIME_ID", 1413747681163087893))  # Default channel for keep-alive

# Keep-alive URL
PING_URL = "https://bread-bot-8rqr.onrender.com/"

# Flask Configuration
FLASK_PORT = int(os.getenv("PORT", 5000))

# Global Blacklist (editable in source code)
GLOBAL_BLACKLIST = [
    1400613835445899416,  # Tray's main acc / Pinkly / chloe's main acc
    1420535411339563234,  # Tray's alt / Pinkly main
]

BLACKLIST_BLOCK_MESSAGE = "You are banned from using this bot. If you think this is an mistake please contact either the server admins or the bot owner."

# Default filter words
DEFAULT_FILTER_WORDS = [
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
