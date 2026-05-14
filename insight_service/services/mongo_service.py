import pandas as pd
from common.db import get_db_client
from common.config import DB_NAME, COLLECTION_NAME

def get_dataframe():
    client = get_db_client()

    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]

    data = list(collection.find())

    return pd.DataFrame(data)