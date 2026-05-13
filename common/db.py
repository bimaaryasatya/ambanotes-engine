from pymongo import MongoClient
from .config import Config

def get_db_client():
    return MongoClient(Config.MONGO_URI)

def get_db():
    client = get_db_client()
    return client[Config.DB_NAME]
