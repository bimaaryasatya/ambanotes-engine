import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    DB_NAME = os.getenv("DB_NAME", "ambanotes")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key")
