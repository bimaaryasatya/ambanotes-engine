from pymongo import MongoClient
from config import MONGO_URI, DB_NAME, COLLECTION_NAME
import pandas as pd

def get_dataframe():
    client = MongoClient(MONGO_URI)

    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]

    data = list(collection.find())

    client.close()

    return pd.DataFrame(data)