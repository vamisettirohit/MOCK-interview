import os
import secrets
from datetime import timedelta
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Base application configuration."""
    SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_hex(32)
    MONGODB_URI = os.getenv("MONGODB_URI") or os.getenv("MONGO_URI") or "mongodb://localhost:27017/"
    MONGO_URI = MONGODB_URI
    DATABASE_NAME = os.getenv("DATABASE_NAME") or os.getenv("MONGO_DB_NAME") or "mock_interview_db"
    MONGO_DB_NAME = DATABASE_NAME
    
    # Session Security Settings
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("FLASK_ENV") == "production"
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)

    # Groq Cloud API
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    
    # Flask Environment
    DEBUG = os.getenv("FLASK_ENV", "development") == "development"
    TESTING = False
