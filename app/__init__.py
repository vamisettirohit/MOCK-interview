from flask import Flask, render_template, session, jsonify, request
from config import Config
from app.extensions import cors, limiter
from app.services.db import init_db

def create_app(config_class=Config):
    """Flask Application Factory."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize Extensions
    cors.init_app(app)
    limiter.init_app(app)

    # Initialize Database Connection
    init_db(app)

    # Context processor to expose user session data to all Jinja templates
    @app.context_processor
    def inject_user():
        user = session.get("user")
        return {"current_user": user}

    # Register Blueprints
    from app.routes.main import main_bp
    from app.routes.health import health_bp
    from app.routes.auth import auth_bp
    from app.routes.interview import interview_bp
    from app.routes.interview_api import interview_api_bp
    from app.routes.dashboard import dashboard_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(interview_bp, url_prefix="/interview")
    app.register_blueprint(interview_api_bp)
    app.register_blueprint(dashboard_bp, url_prefix="/dashboard")

    # Error Handlers
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template("404.html"), 404

    @app.errorhandler(429)
    def ratelimit_handler(error):
        if request.is_json or request.path.startswith("/api/") or request.path.startswith("/interview/api"):
            return jsonify({
                "success": False,
                "error": "Rate limit exceeded. Please wait a moment before trying again."
            }), 429
        return render_template("500.html"), 429

    @app.errorhandler(500)
    def internal_error(error):
        return render_template("500.html"), 500

    return app
