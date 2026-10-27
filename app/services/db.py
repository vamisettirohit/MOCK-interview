"""
Reusable MongoDB Atlas Database Module.
Handles client lifecycle, connection pooling, health checks, and error isolation.
"""
import os
import logging
from typing import Optional, Tuple, Dict, Any
from dotenv import load_dotenv
from pymongo import MongoClient, ASCENDING
from pymongo.database import Database
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError, PyMongoError, DuplicateKeyError

# Ensure environment variables are loaded
load_dotenv()

logger = logging.getLogger(__name__)

# Module-level singletons
_mongo_client: Optional[MongoClient] = None
_db: Optional[Database] = None

# Sensible default timeouts (in milliseconds)
DEFAULT_SERVER_SELECTION_TIMEOUT_MS = 5000
DEFAULT_CONNECT_TIMEOUT_MS = 5000
DEFAULT_SOCKET_TIMEOUT_MS = 10000


def get_db_config() -> Tuple[Optional[str], str]:
    """
    Loads MONGODB_URI and DATABASE_NAME from environment variables.
    
    Returns:
        Tuple of (mongodb_uri, database_name)
    """
    uri = os.getenv("MONGODB_URI") or os.getenv("MONGO_URI")
    db_name = os.getenv("DATABASE_NAME") or os.getenv("MONGO_DB_NAME") or "mock_interview_db"
    return uri, db_name


def get_mongo_client(
    uri: Optional[str] = None,
    timeout_ms: int = DEFAULT_SERVER_SELECTION_TIMEOUT_MS,
    force_reconnect: bool = False
) -> MongoClient:
    """
    Initializes or returns a cached PyMongo MongoClient with a sensible timeout.
    
    Args:
        uri: Optional MongoDB connection string. If omitted, loaded from environment.
        timeout_ms: Server selection timeout in milliseconds.
        force_reconnect: If True, closes any existing client and creates a new one.
        
    Returns:
        MongoClient instance
        
    Raises:
        ValueError: If MONGODB_URI is missing or empty.
    """
    global _mongo_client
    
    if force_reconnect and _mongo_client is not None:
        close_db()
        
    if _mongo_client is not None:
        return _mongo_client

    mongo_uri = uri or get_db_config()[0]
    if not mongo_uri or not mongo_uri.strip():
        logger.error("Database connection failed: MONGODB_URI is not configured.")
        raise ValueError("MONGODB_URI environment variable is missing or empty.")

    try:
        _mongo_client = MongoClient(
            mongo_uri,
            serverSelectionTimeoutMS=timeout_ms,
            connectTimeoutMS=DEFAULT_CONNECT_TIMEOUT_MS,
            socketTimeoutMS=DEFAULT_SOCKET_TIMEOUT_MS,
            appname="mock_interview_ai"
        )
        return _mongo_client
    except Exception as e:
        logger.error(f"Failed to instantiate MongoClient: {type(e).__name__}")
        raise


def get_db(db_name: Optional[str] = None) -> Database:
    """
    Returns the MongoDB database instance.
    
    Args:
        db_name: Optional database name override.
        
    Returns:
        Database instance.
    """
    global _db
    if _db is not None and db_name is None:
        return _db
        
    client = get_mongo_client()
    target_db_name = db_name or get_db_config()[1]
    _db = client[target_db_name]
    return _db


def check_db_health(timeout_ms: int = DEFAULT_SERVER_SELECTION_TIMEOUT_MS) -> Tuple[bool, Dict[str, Any]]:
    """
    Pings the MongoDB server to verify connectivity.
    
    Guarantees that sensitive credentials, connection URIs, or stack traces
    are NEVER returned in the status dictionary.
    
    Returns:
        Tuple of (is_healthy: bool, response_dict: dict)
    """
    mongo_uri, db_name = get_db_config()
    if not mongo_uri or not mongo_uri.strip():
        logger.warning("Health check failed: MONGODB_URI is not configured.")
        return False, {
            "status": "unhealthy",
            "database": "disconnected",
            "error": "Database configuration missing"
        }

    try:
        client = get_mongo_client(uri=mongo_uri, timeout_ms=timeout_ms)
        # Execute ping command against the admin database
        client.admin.command("ping")
        return True, {
            "status": "healthy",
            "database": "connected"
        }
    except (ServerSelectionTimeoutError, ConnectionFailure) as e:
        logger.warning(f"Database health check failed (Connection/Timeout): {type(e).__name__}")
        return False, {
            "status": "unhealthy",
            "database": "disconnected",
            "error": "Database connection failed"
        }
    except PyMongoError as e:
        logger.warning(f"Database health check failed (PyMongoError): {type(e).__name__}")
        return False, {
            "status": "unhealthy",
            "database": "disconnected",
            "error": "Database connection failed"
        }
    except Exception as e:
        logger.error(f"Database health check encountered unexpected error: {type(e).__name__}")
        return False, {
            "status": "unhealthy",
            "database": "disconnected",
            "error": "Database service unavailable"
        }


def is_db_connected() -> bool:
    """Convenience helper to check database status."""
    healthy, _ = check_db_health(timeout_ms=2000)
    return healthy


def close_db():
    """Closes MongoClient connection and cleans up references."""
    global _mongo_client, _db
    if _mongo_client is not None:
        try:
            _mongo_client.close()
        except Exception as e:
            logger.warning(f"Error closing MongoDB client: {type(e).__name__}")
        finally:
            _mongo_client = None
            _db = None


def ensure_indexes():
    """Ensures critical collection indexes exist in MongoDB."""
    try:
        db = get_db()
        db.users.create_index([("email", ASCENDING)], unique=True)
        logger.info("MongoDB unique index on users.email verified.")
    except Exception as e:
        logger.warning(f"Could not verify MongoDB indexes: {type(e).__name__}")


def init_db(app=None):
    """
    Initializes database for Flask app context.
    Safely tests ping and logs status without halting startup.
    """
    try:
        healthy, _ = check_db_health(timeout_ms=DEFAULT_SERVER_SELECTION_TIMEOUT_MS)
        if healthy:
            logger.info("Successfully connected to MongoDB Atlas.")
            ensure_indexes()
        else:
            logger.warning("MongoDB connection could not be established during startup.")
    except Exception as e:
        logger.warning(f"MongoDB startup verification failed: {type(e).__name__}")
