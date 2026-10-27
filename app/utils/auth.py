from functools import wraps
from flask import session, redirect, url_for, flash, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

def hash_password(password: str) -> str:
    """Hashes a raw password securely using Werkzeug's default algorithm (scrypt/pbkdf2)."""
    if not password:
        raise ValueError("Password cannot be empty.")
    return generate_password_hash(password)

def verify_password(stored_hash: str, provided_password: str) -> bool:
    """Verifies a plain password against the stored hash securely in constant time."""
    if not stored_hash or not provided_password:
        return False
    try:
        return check_password_hash(stored_hash, provided_password)
    except Exception:
        return False

def login_required(view_func):
    """
    Decorator ensuring that user is logged in before accessing a view.
    Redirects HTML requests to login page with relative 'next' parameter.
    Returns HTTP 401 Unauthorized for JSON / API requests.
    """
    @wraps(view_func)
    def decorated_function(*args, **kwargs):
        if "user" not in session or not session.get("user"):
            if request.is_json or request.path.startswith("/api/") or "/api/" in request.path:
                return jsonify({"success": False, "error": "Authentication required."}), 401
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("auth.login", next=request.path))
        return view_func(*args, **kwargs)
    return decorated_function
