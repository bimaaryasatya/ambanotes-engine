from pymongo import MongoClient
from config import Config

client = MongoClient(Config.MONGO_URI)
db = client["document_ai"]

users_col = db["users"]
docs_col = db["documents"]
orgs_col = db["organizations"]
logs_col = db["logs"]