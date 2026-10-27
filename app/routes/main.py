from flask import Blueprint, render_template

main_bp = Blueprint("main", __name__)

@main_bp.route("/")
def index():
    """Landing page showcasing Mock Interview AI features."""
    return render_template("index.html")

@main_bp.route("/about")
def about():
    """Information about the AI mock interview platform."""
    return render_template("about.html")
