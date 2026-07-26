"""
Configuration management utilities
"""
from utils.database import config_collection, filter_collection, automod_rule_id_collection
from config import DEFAULT_FILTER_WORDS
import datetime
from datetime import timezone

# Cache for filter words to avoid repeated DB queries
_filter_cache: dict[int, tuple[bool, tuple[str, ...]]] = {}


async def save_config(guild_id, log_channel=None, welcome_channel=None):
    """Save server configuration to MongoDB"""
    update_data = {}
    if log_channel is not None:
        update_data["log_channel"] = log_channel
    if welcome_channel is not None:
        update_data["welcome_channel"] = welcome_channel

    if update_data:
        await config_collection.update_one(
            {"guild_id": guild_id}, {"$set": update_data}, upsert=True
        )


async def load_config(guild_id):
    """Load server configuration from MongoDB"""
    data = await config_collection.find_one({"guild_id": guild_id})
    if data:
        return data.get("log_channel"), data.get("welcome_channel")
    return None, None


async def save_automod_rule_id(guild_id: int, rule_id: str | None):
    """Save AutoMod rule ID for a guild"""
    try:
        await automod_rule_id_collection.update_one(
            {"guild_id": int(guild_id)}, {"$set": {"automod_rule_id": rule_id}}, upsert=True
        )
        return True
    except Exception as e:
        print(f"[ERROR] save_automod_rule_id: {e}")
        return False


async def load_automod_rule_id(guild_id: int):
    """Load AutoMod rule ID for a guild"""
    try:
        doc = await automod_rule_id_collection.find_one({"guild_id": int(guild_id)})
        if doc:
            return doc.get("automod_rule_id")
        return None
    except Exception as e:
        print(f"[ERROR] load_automod_rule_id: {e}")
        return None


async def save_filter_words(guild_id, words):
    """Save filter words for a specific guild to MongoDB"""
    try:
        guild_id = int(guild_id)
        words = [str(w).lower() for w in words] if words else []

        result = await filter_collection.update_one(
            {"guild_id": guild_id},
            {"$set": {"filter_words": words, "updated_at": datetime.datetime.now(timezone.utc)}},
            upsert=True,
        )
        if result.acknowledged:
            previous = _filter_cache.get(guild_id)
            if previous is None:
                existing = await filter_collection.find_one(
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


async def load_filter_words(guild_id):
    """Load filter words for a specific guild from MongoDB"""
    try:
        guild_id = int(guild_id)
        cached = _filter_cache.get(guild_id)
        if cached is not None:
            return list(cached[1])
        doc = await filter_collection.find_one({"guild_id": guild_id})
        words = [str(w).lower() for w in doc.get("filter_words", DEFAULT_FILTER_WORDS)] if doc else list(DEFAULT_FILTER_WORDS)
        enabled = bool(doc.get("enabled", True)) if doc else True
        _filter_cache[guild_id] = (enabled, tuple(words))
        return list(words)
    except Exception as e:
        print(f"[ERROR] load_filter_words: {e}")
        return list(DEFAULT_FILTER_WORDS)


async def reset_filter_words(guild_id):
    """Reset a guild's filter words back to defaults"""
    try:
        guild_id = int(guild_id)
        await filter_collection.update_one(
            {"guild_id": guild_id},
            {
                "$set": {
                    "filter_words": list(DEFAULT_FILTER_WORDS),
                    "updated_at": datetime.datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )
        _filter_cache[guild_id] = (True, tuple(DEFAULT_FILTER_WORDS))
        return list(DEFAULT_FILTER_WORDS)
    except Exception as e:
        print(f"[ERROR] reset_filter_words: {e}")
        return list(DEFAULT_FILTER_WORDS)


async def set_filter_enabled(guild_id, enabled: bool):
    """Enable or disable the filter for a guild"""
    try:
        guild_id = int(guild_id)
        await filter_collection.update_one(
            {"guild_id": guild_id},
            {"$set": {"enabled": bool(enabled), "updated_at": datetime.datetime.now(timezone.utc)}},
            upsert=True,
        )
        cached = _filter_cache.get(guild_id)
        words = cached[1] if cached else tuple(await load_filter_words(guild_id))
        _filter_cache[guild_id] = (bool(enabled), words)
        return True
    except Exception as e:
        print(f"[ERROR] set_filter_enabled: {e}")
        return False


def get_filter_cache():
    """Get the filter cache dictionary"""
    return _filter_cache
