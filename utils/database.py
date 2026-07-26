"""
Database utilities using Motor (async MongoDB driver)
"""
import motor.motor_asyncio
from config import MONGO_URI, MONGO_DB

# Initialize async MongoDB client only if URI is provided
if MONGO_URI and MONGO_DB:
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
else:
    # Create dummy objects if no database configured
    print("[WARN] MongoDB not configured - using dummy database objects")
    
    class DummyCollection:
        async def insert_one(self, *args, **kwargs):
            return {"inserted_id": None}
        
        async def find(self, *args, **kwargs):
            class DummyCursor:
                async def to_list(self, *args, **kwargs):
                    return []
            return DummyCursor()
        
        async def delete_one(self, *args, **kwargs):
            return {"deleted_count": 0}
        
        async def delete_many(self, *args, **kwargs):
            return {"deleted_count": 0}
        
        async def update_one(self, *args, **kwargs):
            return {"modified_count": 0}
        
        async def create_index(self, *args, **kwargs):
            return None
    
    class DummyDB:
        def __getitem__(self, name):
            return DummyCollection()
        
        async def list_collection_names(self):
            return []
    
    class DummyClient:
        async def server_info(self):
            return {"version": "dummy"}
        
        def __getitem__(self, name):
            return DummyDB()
    
    client = DummyClient()
    db = DummyDB()
    config_collection = DummyCollection()
    filter_collection = DummyCollection()
    warnings_collection = DummyCollection()
    moderation_cases_collection = DummyCollection()
    scheduled_invites_collection = DummyCollection()
    guild_blacklist_collection = DummyCollection()
    automod_rule_id_collection = DummyCollection()


async def check_mongodb_connection():
    """Check MongoDB connection and print debug info."""
    try:
        if MONGO_URI and MONGO_DB:
            server_info = await client.server_info()
            print(f"\u2705 MongoDB Server Version: {server_info.get('version')}")

            collections = await db.list_collection_names()
            print(f"\u2705 Available collections: {collections}")

            print(f"\u2705 Server configs collection exists: {'server_configs' in collections}")
        else:
            print("[WARN] MongoDB not configured - skipping connection check")
    except Exception as e:
        print(f"\u274c MongoDB connection error: {e}")


async def debug_db():
    """Print debug info about the database."""
    try:
        if MONGO_URI and MONGO_DB:
            # Count documents in each collection
            for collection_name in ["server_configs", "word_filters", "moderation_warnings", "moderation_cases", "scheduled_invites", "guild_blacklists"]:
                count = await db[collection_name].count_documents({})
                print(f"\u2705 {collection_name}: {count} documents")
        else:
            print("[WARN] MongoDB not configured - skipping debug info")
    except Exception as e:
        print(f"\u274c Debug error: {e}")
