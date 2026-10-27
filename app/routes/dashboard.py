from flask import Blueprint, render_template, redirect, url_for, flash, session
from bson.objectid import ObjectId
from app.services.db import get_db
from app.utils.auth import login_required

dashboard_bp = Blueprint("dashboard", __name__)

@dashboard_bp.route("/")
@login_required
def index():
    """Renders student dashboard with aggregated statistics and past interviews."""
    db = get_db()
    user_id = session["user"]["id"]

    if db is None:
        return render_template(
            "dashboard/index.html",
            interviews=[],
            stats={"total": 0, "completed": 0, "avg_score": 0, "best_score": 0},
            category_stats={},
            db_error=True
        )

    try:
        interviews_cursor = db.interviews.find(
            {"user_id": ObjectId(user_id)}
        ).sort("created_at", -1)
        interviews = list(interviews_cursor)

        completed_interviews = [i for i in interviews if i.get("status") == "completed"]
        scores = [
            float(i["overall_score"]) for i in completed_interviews
            if i.get("overall_score") is not None and isinstance(i.get("overall_score"), (int, float))
        ]

        stats = {
            "total": len(interviews),
            "completed": len(completed_interviews),
            "avg_score": round(sum(scores) / len(scores), 1) if scores else 0.0,
            "best_score": round(max(scores), 1) if scores else 0.0
        }


        # Category performance breakdown
        category_stats = {}
        for item in completed_interviews:
            cat = item.get("category", "General")
            if cat not in category_stats:
                category_stats[cat] = {"count": 0, "total_score": 0}
            category_stats[cat]["count"] += 1
            category_stats[cat]["total_score"] += item.get("overall_score", 0)

        for cat, data in category_stats.items():
            data["avg"] = round(data["total_score"] / data["count"], 1)

        return render_template(
            "dashboard/index.html",
            interviews=interviews,
            stats=stats,
            category_stats=category_stats,
            db_error=False
        )
    except Exception as e:
        flash("Error loading dashboard data. Please try again later.", "danger")
        return render_template(
            "dashboard/index.html",
            interviews=[],
            stats={"total": 0, "completed": 0, "avg_score": 0, "best_score": 0},
            category_stats={},
            db_error=False
        )

@dashboard_bp.route("/history")
@login_required
def history():
    """Renders comprehensive interview history with filtering and search."""
    db = get_db()
    user_id = session["user"]["id"]

    if db is None:
        return render_template(
            "dashboard/history.html",
            interviews=[],
            stats={"total": 0, "completed": 0, "avg_score": 0},
            db_error=True
        )

    try:
        interviews_cursor = db.interviews.find(
            {"user_id": ObjectId(user_id)}
        ).sort("created_at", -1)
        interviews = list(interviews_cursor)

        completed = [i for i in interviews if i.get("status") == "completed"]
        scores = [
            float(i["overall_score"]) for i in completed
            if i.get("overall_score") is not None and isinstance(i.get("overall_score"), (int, float))
        ]

        stats = {
            "total": len(interviews),
            "completed": len(completed),
            "avg_score": round(sum(scores) / len(scores), 1) if scores else 0.0
        }


        return render_template(
            "dashboard/history.html",
            interviews=interviews,
            stats=stats,
            db_error=False
        )
    except Exception as e:
        flash("Error loading interview history. Please try again.", "danger")
        return render_template(
            "dashboard/history.html",
            interviews=[],
            stats={"total": 0, "completed": 0, "avg_score": 0},
            db_error=False
        )

@dashboard_bp.route("/details/<interview_id>")
@login_required
def details(interview_id):
    """Detailed view for a specific historical interview."""
    return redirect(url_for("interview.report_view", interview_id=interview_id))

