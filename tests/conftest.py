import pytest
from app import create_app
from config import Config

class TestConfig(Config):
    TESTING = True
    DEBUG = False
    SECRET_KEY = "test_secret_key"
    MONGO_URI = "mongodb://localhost:27017/"
    MONGO_DB_NAME = "mock_interview_test_db"
    GROQ_API_KEY = ""

@pytest.fixture
def app():
    """Create and configure a new app instance for each test."""
    app = create_app(TestConfig)
    return app

@pytest.fixture
def client(app):
    """A test client for the app."""
    return app.test_client()

@pytest.fixture
def runner(app):
    """A test CLI runner for the app."""
    return app.test_cli_runner()
