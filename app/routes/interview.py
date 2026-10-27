from datetime import datetime, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from bson.objectid import ObjectId
from app.services.db import get_db
from app.services.groq_service import (
    generate_interview_question,
    evaluate_interview_answer,
    GroqAPIError,
    GroqConfigurationError,
    GroqValidationError
)
from app.utils.auth import login_required
from app.utils.validators import (
    validate_interview_setup,
    VALID_CATEGORIES,
    VALID_DIFFICULTIES,
    VALID_BRANCHES,
    VALID_EXPERIENCE_LEVELS,
    VALID_ROLES,
    VALID_DURATIONS
)
from app.extensions import limiter
import app.services.interview_service as interview_service

interview_bp = Blueprint("interview", __name__)


@interview_bp.route("/setup", methods=["GET", "POST"])
@login_required
def setup():
    """Renders setup wizard to configure branch, role, experience, category, difficulty, duration, and question count."""
    if request.method == "POST":
        branch = request.form.get("branch", "CSE").strip()
        custom_branch = request.form.get("custom_branch", "").strip()
        if branch.lower() in ["other", "others"] and custom_branch:
            branch = custom_branch

        job_role = request.form.get("job_role", "Software Developer").strip()
        custom_role = request.form.get("custom_role", "").strip()
        if job_role.lower() in ["custom", "other", "others", "custom role"] and custom_role:
            job_role = custom_role

        experience_level = request.form.get("experience_level", "Fresher").strip()
        category = request.form.get("category", "Technical").strip()
        difficulty = request.form.get("difficulty", "Intermediate").strip()
        topic = request.form.get("topic", "").strip()
        num_questions = request.form.get("num_questions", "3")
        duration = request.form.get("duration", "15")

        is_valid, error_msg = validate_interview_setup(
            category=category,
            difficulty=difficulty,
            num_questions=num_questions,
            branch=branch,
            experience_level=experience_level,
            duration=duration
        )
        if not is_valid:
            flash(error_msg, "danger")
            return render_template(
                "interview/setup.html",
                branches=VALID_BRANCHES,
                job_roles=VALID_ROLES,
                experience_levels=VALID_EXPERIENCE_LEVELS,
                categories=VALID_CATEGORIES,
                difficulties=VALID_DIFFICULTIES,
                durations=VALID_DURATIONS,
                selected_branch=branch,
                selected_role=job_role,
                selected_exp=experience_level,
                selected_category=category,
                selected_difficulty=difficulty,
                selected_topic=topic,
                selected_count=num_questions,
                selected_duration=duration
            )

        db = get_db()
        if db is None:
            flash("Database connection unavailable. Cannot start interview session.", "danger")
            return redirect(url_for("dashboard.index"))

        user_id = session["user"]["id"]
        total_q = int(num_questions)
        duration_mins = int(duration) if str(duration).isdigit() else 15

        interview_doc = {
            "user_id": ObjectId(user_id),
            "branch": branch,
            "job_role": job_role,
            "experience_level": experience_level,
            "category": category,
            "difficulty": difficulty,
            "duration_minutes": duration_mins,
            "topic": topic,
            "total_questions": total_q,
            "completed_questions": 0,
            "overall_score": 0,
            "status": "in_progress",
            "questions": [],
            "created_at": datetime.now(timezone.utc),
            "completed_at": None
        }

        result = db.interviews.insert_one(interview_doc)
        return redirect(url_for("interview.session_view", interview_id=str(result.inserted_id)))

    user_default_role = session.get("user", {}).get("target_role", "Software Developer")
    return render_template(
        "interview/setup.html",
        branches=VALID_BRANCHES,
        job_roles=VALID_ROLES,
        experience_levels=VALID_EXPERIENCE_LEVELS,
        categories=VALID_CATEGORIES,
        difficulties=VALID_DIFFICULTIES,
        durations=VALID_DURATIONS,
        selected_branch="CSE",
        selected_role=user_default_role,
        selected_exp="Fresher",
        selected_category="Technical",
        selected_difficulty="Intermediate",
        selected_count="3",
        selected_duration="15"
    )

@interview_bp.route("/session/<interview_id>")
@login_required
def session_view(interview_id):
    """Renders the live interview room interface."""
    db = get_db()
    if db is None:
        flash("Database unavailable.", "danger")
        return redirect(url_for("dashboard.index"))

    try:
        interview = db.interviews.find_one({
            "_id": ObjectId(interview_id),
            "user_id": ObjectId(session["user"]["id"])
        })
    except Exception:
        flash("Invalid interview session ID.", "danger")
        return redirect(url_for("dashboard.index"))

    if not interview:
        flash("Interview session not found.", "danger")
        return redirect(url_for("dashboard.index"))

    if interview.get("status") == "completed":
        return redirect(url_for("interview.report_view", interview_id=interview_id))

    return render_template("interview/session.html", interview=interview, interview_id=interview_id)

@interview_bp.route("/api/get-question/<interview_id>", methods=["GET"])
@login_required
@limiter.limit("30 per minute")
def api_get_question(interview_id):
    """
    Returns the current active question or invokes Groq AI to generate the next question.
    """
    db = get_db()
    if db is None:
        return jsonify({"success": False, "error": "Database unavailable"}), 500

    try:
        interview = db.interviews.find_one({
            "_id": ObjectId(interview_id),
            "user_id": ObjectId(session["user"]["id"])
        })
    except Exception as e:
        return jsonify({"success": False, "error": f"Invalid ID: {str(e)}"}), 400

    if not interview:
        return jsonify({"success": False, "error": "Interview session not found"}), 404

    questions = interview.get("questions", [])
    total_q = interview.get("total_questions", 3)

    # Check if there is an existing unanswered question
    for q in questions:
        if not q.get("answered", False):
            return jsonify({
                "success": True,
                "question": q,
                "current_index": q["question_number"],
                "total_questions": total_q
            })

    # If all questions completed
    if len(questions) >= total_q:
        return jsonify({
            "success": True,
            "completed": True,
            "message": "All interview questions have been answered."
        })

    # Generate next question via Groq AI
    next_num = len(questions) + 1
    previous_texts = [q.get("question_text") or q.get("question", "") for q in questions if q.get("question_text") or q.get("question")]
    previous_answers = [
        {"question": q.get("question_text") or q.get("question", ""), "user_answer": q.get("user_answer", "")}
        for q in questions if q.get("answered") and q.get("user_answer")
    ]

    try:
        ai_data = generate_interview_question(
            category=interview["category"],
            difficulty=interview["difficulty"],
            job_role=interview.get("job_role"),
            branch=interview.get("branch"),
            experience_level=interview.get("experience_level"),
            topic=interview.get("topic", ""),
            previous_questions=previous_texts,
            previous_answers=previous_answers
        )
    except (GroqAPIError, GroqConfigurationError, GroqValidationError):
        return jsonify({"success": False, "error": "AI question generation service is currently unavailable. Please try again."}), 503
    except Exception:
        return jsonify({"success": False, "error": "Failed to generate next interview question."}), 500

    new_question = {
        "question_number": next_num,
        "question_text": ai_data.get("question", "Describe your experience with this technology."),
        "context_hint": ai_data.get("context_hint", "Be thorough and provide concrete examples."),
        "key_points": ai_data.get("key_points", ai_data.get("expected_aspects", [])),
        "expected_aspects": ai_data.get("expected_aspects", []),
        "user_answer": "",
        "answered": False,
        "score": None,
        "feedback": None
    }

    db.interviews.update_one(
        {"_id": ObjectId(interview_id)},
        {"$push": {"questions": new_question}}
    )

    return jsonify({
        "success": True,
        "question": new_question,
        "current_index": next_num,
        "total_questions": total_q
    })

@interview_bp.route("/api/submit-answer/<interview_id>", methods=["POST"])
@login_required
@limiter.limit("30 per minute")
def api_submit_answer(interview_id):
    """
    Accepts candidate's answer, runs Groq AI evaluation, updates interview document,
    and returns feedback.
    """
    db = get_db()
    if db is None:
        return jsonify({"success": False, "error": "Database unavailable"}), 500

    data = request.get_json() or {}
    question_number = data.get("question_number")
    user_answer = data.get("answer", "").strip()

    if not question_number or not user_answer:
        return jsonify({"success": False, "error": "Question number and answer text are required."}), 400

    try:
        interview = db.interviews.find_one({
            "_id": ObjectId(interview_id),
            "user_id": ObjectId(session["user"]["id"])
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

    if not interview:
        return jsonify({"success": False, "error": "Interview not found"}), 404

    # Locate question
    question_doc = None
    for q in interview.get("questions", []):
        if q["question_number"] == question_number:
            question_doc = q
            break

    if not question_doc:
        return jsonify({"success": False, "error": "Specified question does not exist"}), 404

    # Evaluate answer with Groq AI
    try:
        eval_result = evaluate_interview_answer(
            question_text=question_doc.get("question_text") or question_doc.get("question", ""),
            user_answer=user_answer,
            category=interview["category"],
            difficulty=interview["difficulty"],
            job_role=interview.get("job_role"),
            branch=interview.get("branch"),
            experience_level=interview.get("experience_level")
        )
    except (GroqAPIError, GroqConfigurationError, GroqValidationError):
        return jsonify({"success": False, "error": "AI evaluation service is temporarily unavailable. Please try submitting your answer again."}), 503
    except Exception:
        return jsonify({"success": False, "error": "Failed to evaluate candidate answer."}), 500

    score = eval_result["score"]

    # Update question in DB
    db.interviews.update_one(
        {"_id": ObjectId(interview_id), "questions.question_number": question_number},
        {
            "$set": {
                "questions.$.user_answer": user_answer,
                "questions.$.answered": True,
                "questions.$.score": score,
                "questions.$.classification": eval_result.get("classification"),
                "questions.$.feedback": eval_result,
                "questions.$.evaluation": eval_result,
                "questions.$.evaluated_at": datetime.now(timezone.utc)
            },
            "$inc": {"completed_questions": 1}
        }
    )

    # Re-fetch updated interview to compute overall stats
    updated_interview = db.interviews.find_one({"_id": ObjectId(interview_id)})
    answered_qs = [q for q in updated_interview.get("questions", []) if q.get("answered")]
    total_q = updated_interview.get("total_questions", 3)

    is_all_complete = len(answered_qs) >= total_q
    if is_all_complete:
        scores = [q.get("score", 0) for q in answered_qs if q.get("score") is not None]
        avg_score = round(sum(scores) / len(scores), 1) if scores else 0
        db.interviews.update_one(
            {"_id": ObjectId(interview_id)},
            {
                "$set": {
                    "overall_score": avg_score,
                    "status": "completed",
                    "completed_at": datetime.now(timezone.utc)
                }
            }
        )

    return jsonify({
        "success": True,
        "evaluation": eval_result,
        "is_all_complete": is_all_complete,
        "report_url": url_for("interview.report_view", interview_id=interview_id)
    })

@interview_bp.route("/report/<interview_id>")
@login_required
def report_view(interview_id):
    """Renders comprehensive performance report for an interview session."""
    db = get_db()
    if db is None:
        flash("Database unavailable. Please check MongoDB Atlas connection.", "danger")
        return redirect(url_for("dashboard.index"))

    try:
        obj_id = ObjectId(interview_id.strip())
    except Exception:
        flash("Invalid interview session ID format.", "danger")
        return redirect(url_for("dashboard.index"))

    try:
        interview = db.interviews.find_one({"_id": obj_id})
    except Exception:
        flash("Error retrieving interview record from database.", "danger")
        return redirect(url_for("dashboard.index"))

    if not interview:
        flash("Interview report not found.", "danger")
        return redirect(url_for("dashboard.index"))

    # Strict server-side ownership protection: current student must own the interview
    if str(interview.get("user_id")) != str(session["user"]["id"]):
        flash("You do not have permission to view this interview report.", "danger")
        return redirect(url_for("dashboard.index"))

    questions = interview.get("questions", [])
    answered_qs = [q for q in questions if q.get("answered")]
    is_in_progress = interview.get("status") != "completed"

    # If in progress and not a single question answered, redirect to active session
    if is_in_progress and not answered_qs:
        flash("This interview has not been started yet. Please complete questions to generate a scorecard.", "info")
        return redirect(url_for("interview.session_view", interview_id=interview_id))

    # Calculate overall score consistently from valid evaluations
    overall_score = interview_service.calculate_overall_score(answered_qs)
    interview["overall_score"] = overall_score

    # Ensure report summary exists
    if not interview.get("report") or not interview["report"].get("summary"):
        category = interview.get("category", "Technical")
        job_role = interview.get("job_role", "Software Engineer")
        summary = interview_service.calculate_performance_summary(
            answered_qs,
            category=category,
            job_role=job_role
        )
        if not interview.get("report"):
            interview["report"] = {}
        interview["report"]["summary"] = summary

    score_rating, score_badge = interview_service.get_score_rating(overall_score)

    return render_template(
        "interview/report.html",
        interview=interview,
        is_in_progress=is_in_progress,
        score_rating=score_rating,
        score_badge=score_badge
    )


@interview_bp.route("/history")
@login_required
def history_redirect():
    """Redirects to the centralized student interview history view."""
    return redirect(url_for("dashboard.history"))
