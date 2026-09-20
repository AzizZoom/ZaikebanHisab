import os
from pymongo import MongoClient

# Fetch the connection string from your local .env or cloud environment variables
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)

# 🌟 CRITICAL CHANGE: This ensures complete isolation from OpsAgentDB
db = client["ZaikebanHisabDB"] 
users_collection = db["users"]

def get_user_by_phone(phone: str):
    """Fetches the user document by phone number."""
    return users_collection.find_one({"phone": phone})

def update_user_tokens(phone: str, tokens: dict):
    """Updates or creates a user document with new Google OAuth tokens."""
    users_collection.update_one(
        {"phone": phone}, 
        {"$set": tokens}, 
        upsert=True
    )