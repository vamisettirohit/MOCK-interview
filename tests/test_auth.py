"""
Unit and integration tests for student registration, login, logout, and protected routes.
"""
import pytest
from bson.objectid import ObjectId
from pymongo.errors import DuplicateKeyError
import app.services.db as db_module
from app.utils.auth import hash_password, verify_password
from app.utils.validators import validate_registration, normalize_email


class MockCollection:
    """In-memory mock for MongoDB collection to run deterministic tests offline."""
    def __init__(self, name="collection"):
        self.name = name
        self.docs = []
        self.unique_keys = set()
        if name == "users":
            self.unique_keys.add("email")

    def create_index(self, keys, unique=False):
        if unique:
            for k, _ in keys:
                self.unique_keys.add(k)

    def find_one(self, query):
        for doc in self.docs:
            match = True
            for k, v in query.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                return dict(doc)
        return None

    def insert_one(self, doc):
        for key in self.unique_keys:
            if key in doc:
                for existing in self.docs:
                    if existing.get(key) == doc.get(key):
                        raise DuplicateKeyError(f"Duplicate key on {key}: {doc[key]}")
        new_doc = dict(doc)
        if "_id" not in new_doc:
            new_doc["_id"] = ObjectId()
        self.docs.append(new_doc)

        class Result:
            inserted_id = new_doc["_id"]
        return Result()

    def count_documents(self, query):
        count = 0
        for doc in self.docs:
            match = True
            for k, v in query.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                count += 1
        return count


class MockDatabase:
    """In-memory mock for MongoDB database."""
    def __init__(self):
        self.users = MockCollection("users")
        self.interviews = MockCollection("interviews")


@pytest.fixture
def mock_db(monkeypatch):
    """Fixture providing an isolated in-memory mock database for auth tests."""
    mock_database = MockDatabase()
    monkeypatch.setattr(db_module, "get_db", lambda db_name=None: mock_database)
    return mock_database


# ==============================================================================
# PASSWORD HASHING TESTS
# ==============================================================================

def test_password_hashing_utilities():
    """Verify that passwords are securely hashed with Werkzeug and raw text is never stored."""
    raw_password = "SuperSecurePassword2026!"
    hashed = hash_password(raw_password)

    # Hash must not be plain text or contain the password
    assert hashed != raw_password
    assert raw_password not in hashed
    assert hashed.startswith("scrypt:") or hashed.startswith("pbkdf2:")

    # Verification must succeed for correct password
    assert verify_password(hashed, raw_password) is True

    # Verification must fail for incorrect password
    assert verify_password(hashed, "WrongPassword!") is False
    assert verify_password(hashed, "") is False
    assert verify_password("", raw_password) is False


# ==============================================================================
# REGISTRATION TESTS
# ==============================================================================

def test_valid_registration_form_flow(client, mock_db):
    """Test valid student registration via web form redirecting to dashboard."""
    response = client.post(
        "/auth/register",
        data={
            "name": "Jane Doe",
            "email": "JANE.DOE@example.com",  # Should be normalized to lowercase
            "password": "Password123!",
            "confirm_password": "Password123!",
            "target_role": "Backend Engineer"
        },
        follow_redirects=False
    )

    # Should redirect to dashboard on successful registration
    assert response.status_code == 302
    assert "/dashboard" in response.headers.get("Location", "")

    # Verify user saved in database with normalized email and hashed password
    user = mock_db.users.find_one({"email": "jane.doe@example.com"})
    assert user is not None
    assert user["name"] == "Jane Doe"
    assert user["target_role"] == "Backend Engineer"
    assert "password" not in user  # Raw password must NEVER be saved
    assert verify_password(user["password_hash"], "Password123!") is True

    # Verify session established
    with client.session_transaction() as sess:
        assert sess.get("user") is not None
        assert sess["user"]["email"] == "jane.doe@example.com"
        assert sess["user"]["name"] == "Jane Doe"


def test_valid_registration_json_flow(client, mock_db):
    """Test valid student registration via JSON API."""
    response = client.post(
        "/auth/register",
        json={
            "name": "Bob Smith",
            "email": "bob@university.edu",
            "password": "SecurePassword456!",
            "confirm_password": "SecurePassword456!",
            "target_role": "Frontend Engineer"
        }
    )

    assert response.status_code == 201
    assert response.is_json
    data = response.get_json()
    assert data["success"] is True
    assert data["user"]["email"] == "bob@university.edu"

    # User exists in DB
    user = mock_db.users.find_one({"email": "bob@university.edu"})
    assert user is not None
    assert verify_password(user["password_hash"], "SecurePassword456!") is True


def test_duplicate_email_registration_rejected(client, mock_db):
    """Test that attempting to register an existing email (case-insensitive) is rejected."""
    # Register first account
    client.post(
        "/auth/register",
        json={
            "name": "First User",
            "email": "student@college.edu",
            "password": "Password123!",
            "confirm_password": "Password123!"
        }
    )

    # Log out first so we are not already logged in
    client.get("/auth/logout")

    # Attempt to register with exact same email in uppercase
    response = client.post(
        "/auth/register",
        json={
            "name": "Second User",
            "email": "STUDENT@COLLEGE.EDU",
            "password": "DifferentPassword123!",
            "confirm_password": "DifferentPassword123!"
        }
    )

    # Must return 409 Conflict
    assert response.status_code == 409
    data = response.get_json()
    assert data["success"] is False
    assert "already exists" in data["error"].lower()

    # Ensure only 1 user exists in database
    assert mock_db.users.count_documents({"email": "student@college.edu"}) == 1


@pytest.mark.parametrize("invalid_payload, expected_err", [
    ({"name": "A", "email": "test@example.com", "password": "Password123!", "confirm_password": "Password123!"}, "at least 2 characters"),
    ({"name": "Valid Name", "email": "not-an-email", "password": "Password123!", "confirm_password": "Password123!"}, "valid email"),
    ({"name": "Valid Name", "email": "test@example.com", "password": "123", "confirm_password": "123"}, "at least 6 characters"),
    ({"name": "Valid Name", "email": "test@example.com", "password": "Password123!", "confirm_password": "MismatchPassword123!"}, "do not match"),
])
def test_invalid_registration_inputs(client, mock_db, invalid_payload, expected_err):
    """Test backend validation rejects improperly formatted registration inputs."""
    response = client.post("/auth/register", json=invalid_payload)
    assert response.status_code == 400
    data = response.get_json()
    assert data["success"] is False
    assert expected_err.lower() in data["error"].lower()


# ==============================================================================
# LOGIN & LOGOUT TESTS
# ==============================================================================

def test_login_success(client, mock_db):
    """Test successful student login with correct credentials."""
    # Pre-register user
    client.post(
        "/auth/register",
        json={
            "name": "Alex Mercer",
            "email": "alex@example.com",
            "password": "Password2026!"
        }
    )
    # Log out
    client.get("/auth/logout")

    # Login with case-insensitive email
    response = client.post(
        "/auth/login",
        data={
            "email": "ALEX@EXAMPLE.COM",
            "password": "Password2026!"
        },
        follow_redirects=False
    )

    assert response.status_code == 302
    assert "/dashboard" in response.headers.get("Location", "")

    # Session active
    with client.session_transaction() as sess:
        assert sess.get("user") is not None
        assert sess["user"]["email"] == "alex@example.com"
        assert sess["user"]["name"] == "Alex Mercer"


def test_login_incorrect_password(client, mock_db):
    """Test login failure with incorrect password returns safe error message."""
    client.post(
        "/auth/register",
        json={
            "name": "Alex Mercer",
            "email": "alex@example.com",
            "password": "Password2026!"
        }
    )
    client.get("/auth/logout")

    response = client.post(
        "/auth/login",
        json={
            "email": "alex@example.com",
            "password": "WrongPassword999!"
        }
    )

    assert response.status_code == 401
    data = response.get_json()
    assert data["success"] is False
    assert "invalid email or password" in data["error"].lower()

    # Session should remain empty
    with client.session_transaction() as sess:
        assert sess.get("user") is None


def test_login_nonexistent_account(client, mock_db):
    """Test login failure with unregistered email returns generic safe message."""
    response = client.post(
        "/auth/login",
        json={
            "email": "unregistered@example.com",
            "password": "SomePassword123!"
        }
    )

    assert response.status_code == 401
    data = response.get_json()
    assert data["success"] is False
    # Prevents account enumeration by using the exact same error message
    assert "invalid email or password" in data["error"].lower()


def test_logout_clears_session(client, mock_db):
    """Test that logging out completely clears session data."""
    # Register and establish session
    client.post(
        "/auth/register",
        json={
            "name": "Test User",
            "email": "user@example.com",
            "password": "Password123!"
        }
    )

    with client.session_transaction() as sess:
        assert sess.get("user") is not None

    # Call logout
    response = client.get("/auth/logout", follow_redirects=False)
    assert response.status_code in [301, 302]

    # Session must be completely empty
    with client.session_transaction() as sess:
        assert sess.get("user") is None


# ==============================================================================
# PROTECTED ROUTE TESTS
# ==============================================================================

def test_protected_routes_unauthenticated_redirect(client):
    """Verify that logged-out users cannot access dashboard or interview pages."""
    protected_urls = [
        "/dashboard/",
        "/interview/setup",
        f"/dashboard/details/{ObjectId()}",
        f"/interview/session/{ObjectId()}",
        f"/interview/report/{ObjectId()}"
    ]

    for url in protected_urls:
        response = client.get(url, follow_redirects=False)
        assert response.status_code in [301, 302], f"URL {url} was not protected!"
        location = response.headers.get("Location", "")
        assert "/auth/login" in location, f"URL {url} did not redirect to login!"


def test_protected_api_routes_unauthenticated(client):
    """Verify that logged-out users receive 401 Unauthorized on protected APIs."""
    api_urls = [
        f"/interview/api/get-question/{ObjectId()}",
    ]

    for url in api_urls:
        response = client.get(url)
        assert response.status_code == 401
        data = response.get_json()
        assert data["success"] is False
        assert "authentication required" in data["error"].lower()


def test_protected_routes_accessible_when_authenticated(client, mock_db):
    """Verify that authenticated users can access protected routes."""
    # Authenticate user via session
    with client.session_transaction() as sess:
        sess["user"] = {
            "id": str(ObjectId()),
            "name": "Authenticated Student",
            "email": "student@college.edu",
            "target_role": "Full Stack Developer"
        }

    # Protected HTML pages should now return 200 OK
    dash_res = client.get("/dashboard/")
    assert dash_res.status_code == 200

    setup_res = client.get("/interview/setup")
    assert setup_res.status_code == 200


# ==============================================================================
# LIVE ATLAS INTEGRATION TEST FOR AUTH
# ==============================================================================

def test_live_atlas_auth_flow(client):
    """
    Live integration test that registers, authenticates, and tests live DB session
    against the configured Atlas database.
    """
    uri, db_name = db_module.get_db_config()
    if not uri or "mongodb" not in uri:
        pytest.skip("No live MONGODB_URI configured. Skipping live Atlas auth test.")

    db = db_module.get_db()
    test_email = "test_live_atlas_user_2026@test.com"

    try:
        # Cleanup pre-existing test document if any
        db.users.delete_many({"email": test_email})

        # 1. Register
        reg_res = client.post(
            "/auth/register",
            json={
                "name": "Live Atlas Tester",
                "email": test_email,
                "password": "LivePassword2026!"
            }
        )
        assert reg_res.status_code == 201

        # Verify in live Atlas DB
        user_in_db = db.users.find_one({"email": test_email})
        assert user_in_db is not None
        assert "password" not in user_in_db
        assert verify_password(user_in_db["password_hash"], "LivePassword2026!") is True

        # Log out first so we are not already logged in
        client.get("/auth/logout")

        # 2. Duplicate registration rejected on live DB
        dup_res = client.post(
            "/auth/register",
            json={
                "name": "Duplicate Tester",
                "email": test_email.upper(),
                "password": "OtherPassword2026!"
            }
        )
        assert dup_res.status_code == 409

        # 3. Logout
        client.get("/auth/logout")

        # 4. Login with wrong password rejected
        fail_login = client.post(
            "/auth/login",
            json={"email": test_email, "password": "WrongPassword!"}
        )
        assert fail_login.status_code == 401

        # 5. Login with correct password
        success_login = client.post(
            "/auth/login",
            json={"email": test_email, "password": "LivePassword2026!"}
        )
        assert success_login.status_code == 200

        # 6. Access protected dashboard
        dash_res = client.get("/dashboard/")
        assert dash_res.status_code == 200

    finally:
        # Clean up test user
        db.users.delete_many({"email": test_email})
