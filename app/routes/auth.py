import logging
from datetime import datetime, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from bson.objectid import ObjectId
from pymongo.errors import DuplicateKeyError
import app.services.db as db_service
from app.utils.auth import hash_password, verify_password
from app.utils.validators import validate_registration, normalize_email
from app.extensions import limiter

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)


def is_safe_redirect_url(target: str) -> bool:
    """Ensures redirect target is safe and relative to prevent open-redirect vulnerabilities."""
    if not target:
        return False
    return target.startswith("/") and not target.startswith("//")


@auth_bp.route("/register", methods=["GET", "POST"])
@limiter.limit("20 per minute", methods=["POST"])
def register():
    """
    Handles student registration.
    Normalizes email, enforces uniqueness, hashes passwords securely,
    and returns safe user-facing error messages without exposing internals.
    """
    if not request.is_json and session.get("user"):
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        # Support both Form submissions and JSON payloads
        if request.is_json:
            data = request.get_json() or {}
        else:
            data = request.form

        name = (data.get("name") or "").strip()
        email = normalize_email(data.get("email") or "")
        password = data.get("password") or ""
        confirm_password = data.get("confirm_password") or (password if request.is_json else "")
        target_role = (data.get("target_role") or "Software Engineer").strip()

        # Validate incoming data on the backend
        is_valid, error_msg = validate_registration(name, email, password, confirm_password)
        if not is_valid:
            if request.is_json:
                return jsonify({"success": False, "error": error_msg}), 400
            flash(error_msg, "danger")
            return render_template("auth/register.html", name=name, email=email, target_role=target_role), 400

        db = db_service.get_db()
        if db is None:
            safe_err = "Database service is currently unavailable. Please try again shortly."
            if request.is_json:
                return jsonify({"success": False, "error": safe_err}), 503
            flash(safe_err, "danger")
            return render_template("auth/register.html", name=name, email=email, target_role=target_role), 503

        try:
            # Check for existing email account
            existing_user = db.users.find_one({"email": email})
            if existing_user:
                duplicate_msg = "An account with this email address already exists. Please log in."
                if request.is_json:
                    return jsonify({"success": False, "error": duplicate_msg}), 409
                flash(duplicate_msg, "warning")
                return redirect(url_for("auth.login"))

            # Create user record with hashed password
            user_doc = {
                "name": name,
                "email": email,
                "password_hash": hash_password(password),
                "target_role": target_role,
                "created_at": datetime.now(timezone.utc)
            }
            result = db.users.insert_one(user_doc)

            # Establish session securely
            session.clear()
            session["user"] = {
                "id": str(result.inserted_id),
                "name": name,
                "email": email,
                "target_role": target_role
            }
            session.permanent = True

            if request.is_json:
                return jsonify({
                    "success": True,
                    "message": "Account created successfully.",
                    "user": {"name": name, "email": email, "target_role": target_role}
                }), 201

            flash(f"Welcome, {name}! Your account has been created successfully.", "success")
            return redirect(url_for("dashboard.index"))

        except DuplicateKeyError:
            duplicate_msg = "An account with this email address already exists. Please log in."
            if request.is_json:
                return jsonify({"success": False, "error": duplicate_msg}), 409
            flash(duplicate_msg, "warning")
            return redirect(url_for("auth.login"))

        except Exception as e:
            logger.error(f"Unexpected error during registration: {type(e).__name__}")
            safe_err = "Registration failed due to a system error. Please try again."
            if request.is_json:
                return jsonify({"success": False, "error": safe_err}), 500
            flash(safe_err, "danger")
            return render_template("auth/register.html", name=name, email=email, target_role=target_role), 500

    return render_template("auth/register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("20 per minute", methods=["POST"])
def login():
    """
    Handles student authentication with email and password verification.
    Uses safe error messages to prevent credential and exception leakage.
    """
    if not request.is_json and session.get("user"):
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        if request.is_json:
            data = request.get_json() or {}
        else:
            data = request.form

        email = normalize_email(data.get("email") or "")
        password = data.get("password") or ""
        raw_next = request.args.get("next") or (data.get("next") if not request.is_json else None)
        next_url = raw_next if is_safe_redirect_url(raw_next) else url_for("dashboard.index")

        if not email or not password:
            err_msg = "Please provide both email and password."
            if request.is_json:
                return jsonify({"success": False, "error": err_msg}), 400
            flash(err_msg, "danger")
            return render_template("auth/login.html", email=email), 400

        db = db_service.get_db()
        if db is None:
            safe_err = "Database service is currently unavailable. Please try again shortly."
            if request.is_json:
                return jsonify({"success": False, "error": safe_err}), 503
            flash(safe_err, "danger")
            return render_template("auth/login.html", email=email), 503

        try:
            user = db.users.find_one({"email": email})
            if not user or not verify_password(user.get("password_hash", ""), password):
                err_msg = "Invalid email or password. Please try again."
                if request.is_json:
                    return jsonify({"success": False, "error": err_msg}), 401
                flash(err_msg, "danger")
                return render_template("auth/login.html", email=email), 401

            # Establish session
            session.clear()
            session["user"] = {
                "id": str(user["_id"]),
                "name": user.get("name", "Student"),
                "email": user["email"],
                "target_role": user.get("target_role", "Software Engineer")
            }
            session.permanent = True

            if request.is_json:
                return jsonify({
                    "success": True,
                    "message": "Login successful.",
                    "user": session["user"]
                }), 200

            flash(f"Welcome back, {session['user']['name']}!", "success")
            return redirect(next_url)

        except Exception as e:
            logger.error(f"Unexpected error during login: {type(e).__name__}")
            safe_err = "Login failed due to a system error. Please try again."
            if request.is_json:
                return jsonify({"success": False, "error": safe_err}), 500
            flash(safe_err, "danger")
            return render_template("auth/login.html", email=email), 500

    return render_template("auth/login.html")


@auth_bp.route("/logout", methods=["GET", "POST"])
def logout():
    """Clears user session completely and logs out."""
    session.clear()
    if request.is_json:
        return jsonify({"success": True, "message": "Logged out successfully."}), 200
    flash("You have been logged out successfully.", "info")
    return redirect(url_for("main.index"))
