"""
Database utilities using Motor (async MongoDB driver)
"""
import motor.motor_asyncio
from config import MONGO_URI, MONGO_DB

# Initialize async MongoDB client
client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=5_000)
db = client[MONGO_DB]

# Collection references
config_collection = db["server_configs"]
filter_collection = db["word_filters"]
warnings_collection = db["moderation_warnings"]
moderation_cases_collection = db["moderation_cases"]
scheduled_invites_collection = db["scheduled_invites"]
guild_blacklist_collection = db["guild_blacklists"]
automod_rule_id_collection = db["automod_rule_ids"]


async def check_mongodb_connection():
    """Check MongoDB connection and print debug info."""
    try:
        server_info = await client.server_info()
        print(f"✅ MongoDB Server Version: {server_info.get('version')}")

        collections = await db.list_collection_names()
        print(f"✅ Available collections: {collections}")

        print(f"✅ Server configs collection exists: {'server_configs' in collections}")
        print(f"✅ Word filters collection exists: {'word_filters' in collections}")

        if "word_filters" in collections:
            count = await db.word_filters.count_documents({})
            print(f"✅ Word filters collection has {count} documents")
            if count > 0:
                sample = await db.word_filters.find_one()
                print("✅ Sample document:", sample)

        return True
    except Exception as e:
        print(f"❌ MongoDB Connection Error: {e!s}")
        return False


async def debug_filter_db():
    """Debug function to print all filter documents"""
    print("\n=== DEBUG: MongoDB Filter Collection ===")
    cursor = filter_collection.find()
    async for doc in cursor:
        print(
            f"Guild {doc.get('guild_id')}: {len(doc.get('filter_words', []))} words, enabled: {doc.get('enabled', True)}"
        )
    print("=== End of Filter Debug ===\n")


async def debug_db():
    """Debug function to print all documents in the config collection"""
    print("\n=== DEBUG: MongoDB Config Collection ===")
    cursor = config_collection.find()
    async for doc in cursor:
        print(f"Document: {doc}")
    print("=== End of MongoDB Debug ===\n")
