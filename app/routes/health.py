from flask import Blueprint, jsonify
import app.services.db as db_service
from app.extensions import limiter

health_bp = Blueprint("health", __name__)

@health_bp.route("/health", methods=["GET"])
@health_bp.route("/api/health", methods=["GET"])
@limiter.exempt
def health_check():
    """
    Database health check endpoint.
    Verifies MongoDB connection with ping and returns a safe JSON status.
    Never exposes MongoDB URIs, usernames, passwords, or stack traces.
    """
    is_healthy, payload = db_service.check_db_health()
    status_code = 200 if is_healthy else 503
    return jsonify(payload), status_code
