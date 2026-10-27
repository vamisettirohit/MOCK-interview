"""
Convenience entrypoint for the reusable database module.
"""
from app.services.db import (
    get_db,
    get_mongo_client,
    check_db_health,
    is_db_connected,
    close_db,
    init_db,
    ensure_indexes,
    get_db_config,
    DEFAULT_SERVER_SELECTION_TIMEOUT_MS
)

__all__ = [
    "get_db",
    "get_mongo_client",
    "check_db_health",
    "is_db_connected",
    "close_db",
    "init_db",
    "ensure_indexes",
    "get_db_config",
    "DEFAULT_SERVER_SELECTION_TIMEOUT_MS",
]
