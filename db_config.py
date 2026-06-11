import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

# CORRECT: Use os.getenv to pull from your .env file
# Make sure the key matches exactly what is inside your .env file
MONGO_URI = os.getenv("MONGODB_URI") 

_db_cache = None

def get_db_connection():
    global _db_cache
    if _db_cache is not None:
        return _db_cache
    
    # This check now actually works because MONGO_URI has a value
    if not MONGO_URI:
        raise RuntimeError("MongoDB URI missing. Ensure MONGODB_URI is in your .env file.")
    
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=8000)
    client.admin.command("ping")
    _db_cache = client["SupplyShieldDB"]
    return _db_cache


class _LazyDB:
    """Proxy so Flask can boot before the first database call."""
    def __getattr__(self, name):
        return getattr(get_db_connection(), name)


# Export a lazy db proxy used throughout the app.
db = _LazyDB()