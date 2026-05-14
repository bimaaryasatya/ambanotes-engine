from pymongo import MongoClient
from common.config import Config

def get_db_client():
    return MongoClient(Config.MONGO_URI)

client = get_db_client()
db = client[Config.DB_NAME]

users_col = db["users"]
docs_col = db["documents"]
orgs_col = db["organizations"]
logs_col = db["logs"]
invitations_col = db["invitations"]