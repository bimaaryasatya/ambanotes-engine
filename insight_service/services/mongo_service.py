import pandas as pd
from common.db import get_db_client
from common.config import Config

def get_dataframe():
    client = get_db_client()

    db = client[Config.DB_NAME]
    collection = db[Config.COLLECTION_NAME]

    data = list(collection.find())

    return pd.DataFrame(data)