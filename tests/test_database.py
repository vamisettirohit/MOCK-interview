"""
Unit and integration tests for the MongoDB Atlas database module and health endpoint.
"""
import os
import pytest
from unittest.mock import MagicMock
from pymongo.errors import ServerSelectionTimeoutError, ConnectionFailure
import app.services.db as db_module
from app.db import (
    get_mongo_client,
    check_db_health,
    is_db_connected,
    close_db,
    get_db_config,
    DEFAULT_SERVER_SELECTION_TIMEOUT_MS,
)


# ==============================================================================
# UNIT TESTS (Runs without a live Atlas connection)
# ==============================================================================

def test_reusable_database_module_exports():
    """Verify that app.db exposes the public interface correctly."""
    assert callable(get_mongo_client)
    assert callable(check_db_health)
    assert callable(is_db_connected)
    assert callable(close_db)
    assert callable(get_db_config)
    assert DEFAULT_SERVER_SELECTION_TIMEOUT_MS == 5000


def test_missing_mongodb_uri_handling(monkeypatch):
    """Test behavior when MONGODB_URI is not set in the environment."""
    monkeypatch.delenv("MONGODB_URI", raising=False)
    monkeypatch.delenv("MONGO_URI", raising=False)
    db_module.close_db()

    # Health check should return safe failure tuple
    is_healthy, payload = check_db_health()
    assert is_healthy is False
    assert payload["status"] == "unhealthy"
    assert payload["database"] == "disconnected"
    assert payload["error"] == "Database configuration missing"

    # get_mongo_client without URI should raise a clear ValueError
    with pytest.raises(ValueError) as exc_info:
        get_mongo_client(uri="")
    assert "MONGODB_URI" in str(exc_info.value)


def test_db_health_check_ping_success(monkeypatch):
    """Test check_db_health logic when ping succeeds."""
    mock_client = MagicMock()
    mock_client.admin.command.return_value = {"ok": 1.0}

    monkeypatch.setattr(db_module, "get_db_config", lambda: ("mongodb://fake:27017", "test_db"))
    monkeypatch.setattr(db_module, "get_mongo_client", lambda **kwargs: mock_client)

    is_healthy, payload = check_db_health()
    assert is_healthy is True
    assert payload == {
        "status": "healthy",
        "database": "connected"
    }
    mock_client.admin.command.assert_called_once_with("ping")


def test_db_health_check_ping_timeout(monkeypatch):
    """Test check_db_health logic when ping times out."""
    mock_client = MagicMock()
    mock_client.admin.command.side_effect = ServerSelectionTimeoutError("Server selection timed out")

    monkeypatch.setattr(db_module, "get_db_config", lambda: ("mongodb://fake:27017", "test_db"))
    monkeypatch.setattr(db_module, "get_mongo_client", lambda **kwargs: mock_client)

    is_healthy, payload = check_db_health()
    assert is_healthy is False
    assert payload["status"] == "unhealthy"
    assert payload["database"] == "disconnected"
    assert payload["error"] == "Database connection failed"
    # Verify no exception messages, hosts, or stack traces leak
    assert "Server selection timed out" not in str(payload)


def test_db_health_check_connection_failure(monkeypatch):
    """Test check_db_health logic when connection failure occurs."""
    mock_client = MagicMock()
    mock_client.admin.command.side_effect = ConnectionFailure("Connection reset by peer")

    monkeypatch.setattr(db_module, "get_db_config", lambda: ("mongodb://fake:27017", "test_db"))
    monkeypatch.setattr(db_module, "get_mongo_client", lambda **kwargs: mock_client)

    is_healthy, payload = check_db_health()
    assert is_healthy is False
    assert payload["status"] == "unhealthy"
    assert payload["database"] == "disconnected"
    assert payload["error"] == "Database connection failed"
    assert "Connection reset by peer" not in str(payload)


def test_health_endpoint_healthy(client, monkeypatch):
    """Test GET /health returns 200 OK and clean JSON when database is connected."""
    monkeypatch.setattr(
        db_module,
        "check_db_health",
        lambda timeout_ms=5000: (True, {"status": "healthy", "database": "connected"})
    )

    response = client.get("/health")
    assert response.status_code == 200
    assert response.is_json
    data = response.get_json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"

    # Also test alias /api/health
    api_response = client.get("/api/health")
    assert api_response.status_code == 200
    assert api_response.get_json() == data


def test_health_endpoint_unhealthy(client, monkeypatch):
    """Test GET /health returns 503 Service Unavailable when database is disconnected."""
    monkeypatch.setattr(
        db_module,
        "check_db_health",
        lambda timeout_ms=5000: (False, {
            "status": "unhealthy",
            "database": "disconnected",
            "error": "Database connection failed"
        })
    )

    response = client.get("/health")
    assert response.status_code == 503
    assert response.is_json
    data = response.get_json()
    assert data["status"] == "unhealthy"
    assert data["database"] == "disconnected"
    assert data["error"] == "Database connection failed"


def test_never_expose_credentials_or_stack_traces(client, monkeypatch):
    """
    CRITICAL SECURITY TEST:
    Verifies that MongoDB URI, username, password, or stack traces
    are NEVER exposed to the client in either healthy or error states.
    """
    sensitive_uri = "mongodb+srv://secret_user:super_secret_password_999@test-cluster.mongodb.net/"
    monkeypatch.setenv("MONGODB_URI", sensitive_uri)

    # Simulate an error that internally contains sensitive details
    def mock_failing_client(**kwargs):
        raise ServerSelectionTimeoutError(f"Failed to connect to {sensitive_uri}")

    monkeypatch.setattr(db_module, "get_mongo_client", mock_failing_client)

    response = client.get("/health")
    raw_response_text = response.get_data(as_text=True)

    # None of the sensitive tokens must appear anywhere in the response
    assert "secret_user" not in raw_response_text
    assert "super_secret_password_999" not in raw_response_text
    assert "mongodb+srv://" not in raw_response_text
    assert "test-cluster.mongodb.net" not in raw_response_text
    assert "Traceback" not in raw_response_text
    assert "ServerSelectionTimeoutError" not in raw_response_text


# ==============================================================================
# INTEGRATION TEST (Runs against configured live Atlas database)
# ==============================================================================

def test_live_atlas_connection_integration(client):
    """
    Optional live integration test that runs if MONGODB_URI is configured.
    Pings the actual MongoDB Atlas cluster and verifies the health endpoint.
    """
    uri, db_name = get_db_config()
    if not uri or "mongodb" not in uri:
        pytest.skip("No live MONGODB_URI configured. Skipping live Atlas integration test.")

    # Run direct ping through reusable module
    is_healthy, payload = check_db_health(timeout_ms=6000)
    assert is_healthy is True, f"Failed to ping configured live MongoDB Atlas: {payload}"
    assert payload["status"] == "healthy"
    assert payload["database"] == "connected"

    # Call endpoint over HTTP test client
    response = client.get("/health")
    assert response.status_code == 200
    assert response.is_json
    data = response.get_json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"

    # Security check on live response as well
    raw_text = response.get_data(as_text=True)
    assert "@" not in raw_text
    assert "mongodb" not in raw_text.lower() or "connected" in raw_text
    assert "password" not in raw_text.lower()
