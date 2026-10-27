"""
Interview Workflow REST API.

Provides endpoints for creating, managing, and completing AI-driven mock interviews:
- POST /api/interviews           — Create an interview for the authenticated student.
- GET  /api/interviews           — List only the authenticated student's interviews.
- GET  /api/interviews/<id>      — Retrieve an interview owned by the current student.
- POST /api/interviews/<id>/answer — Evaluate and save an answer for the current question.
- POST /api/interviews/<id>/next   — Generate or retrieve the next question.
- POST /api/interviews/<id>/finish — Finish an interview and calculate the final report.
- GET  /api/interviews/<id>/report — Retrieve the completed report.

Security & Integrity:
- Authentication & strict ownership verification on all routes.
- Safe ObjectID parsing (no crashes on invalid IDs; returns 400).
- Category, difficulty, question count, and answer length validation.
- Completed interview immutability (cannot answer or generate for finished interviews).
- Duplicate answer submission prevention on the same question.
- Groq failure isolation: API timeouts, rate limits, or errors do NOT corrupt DB state.
- Server-side score calculation (client scores/IDs are never trusted).
"""
import logging
from datetime import datetime, timezone
from typing import Optional, Tuple, Dict, Any, List
from flask import Blueprint, request, jsonify, session
from bson.objectid import ObjectId
from bson.errors import InvalidId

import app.services.db as db_service
import app.services.interview_service as interview_service
from app.utils.auth import login_required
from app.extensions import limiter
import src.groq_service as groq_service



logger = logging.getLogger(__name__)

interview_api_bp = Blueprint("interview_api", __name__, url_prefix="/api/interviews")


# ==============================================================================
# SERIALIZATION & VERIFICATION HELPERS
# ==============================================================================

def serialize_interview(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Serializes a MongoDB interview document into JSON-safe dictionary.
    Converts ObjectId and datetime instances to standard string representations.
    """
    if not doc:
        return {}
    res = dict(doc)
    if "_id" in res:
        res["id"] = str(res["_id"])
        res["_id"] = str(res["_id"])
    if "user_id" in res:
        res["user_id"] = str(res["user_id"])
    if "created_at" in res and isinstance(res["created_at"], datetime):
        res["created_at"] = res["created_at"].isoformat()
    if "completed_at" in res and isinstance(res["completed_at"], datetime):
        res["completed_at"] = res["completed_at"].isoformat()
    if "questions" in res and isinstance(res["questions"], list):
        clean_qs = []
        for q in res["questions"]:
            q_copy = dict(q)
            if "evaluated_at" in q_copy and isinstance(q_copy["evaluated_at"], datetime):
                q_copy["evaluated_at"] = q_copy["evaluated_at"].isoformat()
            clean_qs.append(q_copy)
        res["questions"] = clean_qs
    return res


def get_verified_interview(
    interview_id: str,
    user_id: str,
    db: Any
) -> Tuple[Optional[Dict[str, Any]], Optional[Tuple[Dict[str, Any], int]]]:
    """
    Validates interview ID format, existence, and ownership.
    Returns:
        (interview_document, None) on success
        (None, (error_dict, status_code)) on verification failure
    """
    if not interview_id or not isinstance(interview_id, str):
        return None, ({"success": False, "error": "Interview ID is required."}, 400)

    try:
        obj_id = ObjectId(interview_id.strip())
    except (InvalidId, TypeError, ValueError):
        return None, ({"success": False, "error": "Invalid interview ID format."}, 400)

    try:
        interview = db.interviews.find_one({"_id": obj_id})
    except Exception as e:
        logger.error(f"Error querying interview from MongoDB: {type(e).__name__}")
        return None, ({"success": False, "error": "Database error retrieving interview."}, 500)

    if not interview:
        return None, ({"success": False, "error": "Interview not found."}, 404)

    # Enforce strict ownership: current user must match the interview's user_id
    if str(interview.get("user_id")) != str(user_id):
        return None, ({"success": False, "error": "You do not have permission to access this interview."}, 403)

    return interview, None


def calculate_performance_summary(
    answered_questions: List[Dict[str, Any]],
    category: str = "Technical",
    job_role: str = ""
) -> Dict[str, Any]:
    """Aggregates scores, strengths, weaknesses, mistakes, concepts, suggestions, and practice topics across all answered questions."""
    return interview_service.calculate_performance_summary(answered_questions, category=category, job_role=job_role)


# ==============================================================================
# 1. POST /api/interviews — Create Interview
# ==============================================================================

@interview_api_bp.route("", methods=["POST"])
@interview_api_bp.route("/", methods=["POST"])
@login_required
@limiter.limit("20 per minute")
def create_interview():
    """
    POST /api/interviews
    Creates a new mock interview session for the authenticated student.
    Validates category, difficulty, question count, and initializes the first question.
    """
    data = request.get_json() or {}
    category_raw = data.get("category", "Technical")
    difficulty_raw = data.get("difficulty", "Intermediate")
    
    # 1. Engineering Branch handling
    branch = (data.get("branch") or "CSE").strip()[:100]
    custom_branch = (data.get("custom_branch") or "").strip()[:100]
    if branch.lower() in ["other", "others"] and custom_branch:
        branch = custom_branch

    # 2. Target Job Role handling
    job_role = (data.get("job_role") or "Software Developer").strip()[:100]
    custom_role = (data.get("custom_role") or "").strip()[:100]
    if job_role.lower() in ["custom", "other", "others", "custom role"] and custom_role:
        job_role = custom_role

    # 3. Experience Level handling
    exp_raw = (data.get("experience_level") or "Fresher").strip()
    exp_map = {"fresher": "Fresher", "internship": "Internship", "experienced": "Experienced"}
    experience_level = exp_map.get(exp_raw.lower(), "Fresher")

    topic = (data.get("topic") or "").strip()[:100]
    total_q_raw = data.get("total_questions", 3)
    duration_raw = data.get("duration_minutes") or data.get("duration", 15)

    # 4. Duration validation
    try:
        duration_minutes = int(duration_raw)
        if not (5 <= duration_minutes <= 180):
            duration_minutes = 15
    except (ValueError, TypeError):
        duration_minutes = 15

    # 5. Validate Category
    try:
        norm_category = groq_service.normalize_category(category_raw)
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "supported_categories": list(groq_service.SUPPORTED_CATEGORIES)
        }), 400

    # 6. Validate Difficulty
    try:
        norm_difficulty = groq_service.normalize_difficulty(difficulty_raw)
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "supported_difficulties": list(groq_service.SUPPORTED_DIFFICULTIES)
        }), 400

    # 7. Validate Total Questions
    try:
        total_questions = int(total_q_raw)
        if not (1 <= total_questions <= 10):
            return jsonify({"success": False, "error": "Total questions must be an integer between 1 and 10."}), 400
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "Invalid total_questions value; must be an integer between 1 and 10."}), 400

    db = db_service.get_db()
    if db is None:
        return jsonify({"success": False, "error": "Database service is currently unavailable."}), 503

    user_id = session["user"]["id"]

    # 8. Generate Question 1 via Groq AI
    try:
        first_q_data = groq_service.generate_interview_question(
            category=norm_category,
            difficulty=norm_difficulty,
            job_role=job_role,
            previous_questions=[],
            branch=branch,
            experience_level=experience_level,
            topic=topic
        )
    except (groq_service.GroqAPIError, groq_service.GroqConfigurationError, groq_service.GroqValidationError) as e:
        logger.error(f"Groq question generation failed during interview creation: {type(e).__name__}")
        return jsonify({
            "success": False,
            "error": "AI question generation service is currently unavailable. Please try again."
        }), 503
    except Exception as e:
        logger.error(f"Unexpected error generating first question: {type(e).__name__}")
        return jsonify({"success": False, "error": "Failed to initialize interview question."}), 500

    first_question = {
        "question_number": 1,
        "question": first_q_data["question"],
        "category": first_q_data.get("category", norm_category),
        "difficulty": first_q_data.get("difficulty", norm_difficulty),
        "topic": first_q_data.get("topic", topic or norm_category),
        "expected_aspects": first_q_data.get("expected_aspects", []),
        "user_answer": None,
        "answered": False,
        "score": None,
        "evaluation": None
    }

    # 9. Persist Interview to MongoDB
    interview_doc = {
        "user_id": ObjectId(user_id),
        "branch": branch,
        "job_role": job_role,
        "experience_level": experience_level,
        "category": norm_category,
        "difficulty": norm_difficulty,
        "duration_minutes": duration_minutes,
        "topic": topic,
        "total_questions": total_questions,
        "completed_questions": 0,
        "overall_score": 0,
        "status": "in_progress",
        "questions": [first_question],
        "created_at": datetime.now(timezone.utc),
        "completed_at": None,
        "report": None
    }

    try:
        insert_res = db.interviews.insert_one(interview_doc)
        interview_doc["_id"] = insert_res.inserted_id
        serialized = serialize_interview(interview_doc)
        return jsonify({
            "success": True,
            "message": "Interview session created successfully.",
            "interview": serialized
        }), 201
    except Exception as e:
        logger.error(f"Failed to persist interview: {type(e).__name__}")
        return jsonify({"success": False, "error": "Database error creating interview."}), 500


# ==============================================================================
# 2. GET /api/interviews — List Authenticated Student's Interviews
# ==============================================================================

@interview_api_bp.route("", methods=["GET"])
@interview_api_bp.route("/", methods=["GET"])
@login_required
def list_interviews():
    """
    GET /api/interviews
    Returns only the authenticated student's interviews, sorted newest first.
    """
    db = db_service.get_db()
    if db is None:
        return jsonify({"success": False, "error": "Database service is currently unavailable."}), 503

    user_id = session["user"]["id"]

    try:
        cursor = db.interviews.find({"user_id": ObjectId(user_id)}).sort("created_at", -1)
        interviews = [serialize_interview(doc) for doc in cursor]
        return jsonify({
            "success": True,
            "count": len(interviews),
            "interviews": interviews
        }), 200
    except Exception as e:
        logger.error(f"Error querying interviews for user {user_id}: {type(e).__name__}")
        return jsonify({"success": False, "error": "Database error retrieving interview list."}), 500


# ==============================================================================
# 3. GET /api/interviews/<id> — Retrieve Single Interview
# ==============================================================================

@interview_api_bp.route("/<interview_id>", methods=["GET"])
@login_required
def get_interview(interview_id):
    """
    GET /api/interviews/<id>
    Retrieves an interview owned by the authenticated student.
    Enforces strict ownership check (returns 403 if owned by another student).
    """
    db = db_service.get_db()
    if db is None:
        return jsonify({"success": False, "error": "Database service is currently unavailable."}), 503

    user_id = session["user"]["id"]
    interview, err = get_verified_interview(interview_id, user_id, db)
    if err:
        return jsonify(err[0]), err[1]

    return jsonify({
        "success": True,
        "interview": serialize_interview(interview)
    }), 200


# ==============================================================================
# 4. POST /api/interviews/<id>/next — Generate or Retrieve Next Question
# ==============================================================================

@interview_api_bp.route("/<interview_id>/next", methods=["POST"])
@login_required
@limiter.limit("25 per minute")
def get_or_generate_next_question(interview_id):
    """
    POST /api/interviews/<id>/next
    Generates or retrieves the next interview question.
    - If there is an existing unanswered question, returns it without creating a duplicate.
    - If all questions completed, prompts client to finish.
    - If Groq fails, returns a recoverable 503 without corrupting the saved interview state.
    """
    db = db_service.get_db()
    if db is None:
        return jsonify({"success": False, "error": "Database service is currently unavailable."}), 503

    user_id = session["user"]["id"]
    interview, err = get_verified_interview(interview_id, user_id, db)
    if err:
        return jsonify(err[0]), err[1]

    if interview.get("status") == "completed":
        return jsonify({"success": False, "error": "This interview has already been completed."}), 400

    questions = interview.get("questions", [])
    total_questions = interview.get("total_questions", 3)

    # 1. Check if there is an active unanswered question
    for q in questions:
        if not q.get("answered", False):
            return jsonify({
                "success": True,
                "question": q,
                "question_number": q["question_number"],
                "total_questions": total_questions,
                "is_new": False
            }), 200

    # 2. Check if total question limit has already been reached
    if len(questions) >= total_questions:
        return jsonify({
            "success": True,
            "completed": True,
            "message": "All interview questions have been answered. Please finish the interview to view your final report."
        }), 200

    # 3. Generate Next Question with Groq AI
    next_q_num = len(questions) + 1
    previous_texts = [q.get("question", "") for q in questions if q.get("question")]
    previous_answers = [
        {"question": q.get("question", ""), "user_answer": q.get("user_answer", "")}
        for q in questions if q.get("answered") and q.get("user_answer")
    ]

    try:
        q_data = groq_service.generate_interview_question(
            category=interview["category"],
            difficulty=interview["difficulty"],
            job_role=interview.get("job_role"),
            previous_questions=previous_texts,
            branch=interview.get("branch"),
            experience_level=interview.get("experience_level"),
            topic=interview.get("topic"),
            previous_answers=previous_answers
        )
    except (groq_service.GroqAPIError, groq_service.GroqConfigurationError, groq_service.GroqValidationError) as e:
        logger.error(f"Groq error generating next question: {type(e).__name__}")
        # State in MongoDB is NOT modified on Groq failure!
        return jsonify({
            "success": False,
            "error": "AI question generation service is currently unavailable. Please try again."
        }), 503
    except Exception as e:
        logger.error(f"Unexpected question generation error: {type(e).__name__}")
        return jsonify({"success": False, "error": "Failed to generate next interview question."}), 500

    new_question = {
        "question_number": next_q_num,
        "question": q_data["question"],
        "category": q_data.get("category", interview["category"]),
        "difficulty": q_data.get("difficulty", interview["difficulty"]),
        "topic": q_data.get("topic", interview.get("topic", "")),
        "expected_aspects": q_data.get("expected_aspects", []),
        "user_answer": None,
        "answered": False,
        "score": None,
        "evaluation": None
    }

    try:
        db.interviews.update_one(
            {"_id": interview["_id"]},
            {"$push": {"questions": new_question}}
        )
        return jsonify({
            "success": True,
            "question": new_question,
            "question_number": next_q_num,
            "total_questions": total_questions,
            "is_new": True
        }), 200
    except Exception as e:
        logger.error(f"Failed to append next question: {type(e).__name__}")
        return jsonify({"success": False, "error": "Database error saving next question."}), 500


# ==============================================================================
# 5. POST /api/interviews/<id>/answer — Submit & Evaluate Answer
# ==============================================================================

@interview_api_bp.route("/<interview_id>/answer", methods=["POST"])
@login_required
@limiter.limit("20 per minute")
def submit_answer(interview_id):
    """
    POST /api/interviews/<id>/answer
    Evaluates and saves candidate's answer for the current or specified question.
    - Validates answer length (5 to 5000 characters).
    - Prevents answering completed interviews or duplicate submissions on the same question.
    - Evaluates via Groq AI; if Groq fails, leaves interview state uncorrupted.
    """
    db = db_service.get_db()
    if db is None:
        return jsonify({"success": False, "error": "Database service is currently unavailable."}), 503

    user_id = session["user"]["id"]
    interview, err = get_verified_interview(interview_id, user_id, db)
    if err:
        return jsonify(err[0]), err[1]

    if interview.get("status") == "completed":
        return jsonify({"success": False, "error": "This interview has already been completed."}), 400

    data = request.get_json() or {}
    answer_raw = data.get("answer")

    # Validate answer text
    if not answer_raw or not isinstance(answer_raw, str) or not answer_raw.strip():
        return jsonify({"success": False, "error": "Answer text is required and cannot be empty."}), 400

    clean_answer = answer_raw.strip()
    if len(clean_answer) < 5:
        return jsonify({"success": False, "error": "Answer must be at least 5 characters long."}), 400
    if len(clean_answer) > 5000:
        return jsonify({"success": False, "error": "Answer cannot exceed 5000 characters."}), 400

    # Locate target question
    questions = interview.get("questions", [])
    target_q_num = data.get("question_number")

    target_question = None
    if target_q_num is not None:
        try:
            target_q_num = int(target_q_num)
            for q in questions:
                if q.get("question_number") == target_q_num:
                    target_question = q
                    break
        except (ValueError, TypeError):
            return jsonify({"success": False, "error": "Invalid question_number provided."}), 400
    else:
        # Default to first unanswered question
        for q in questions:
            if not q.get("answered", False):
                target_question = q
                target_q_num = q["question_number"]
                break

    if not target_question:
        return jsonify({"success": False, "error": "Specified or active question not found."}), 404

    # Prevent duplicate submissions on already answered questions
    if target_question.get("answered", False):
        return jsonify({
            "success": False,
            "error": "This question has already been answered. Duplicate submissions are not allowed."
        }), 400

    # Evaluate Answer with Groq AI
    try:
        eval_result = groq_service.evaluate_interview_answer(
            question_text=target_question["question"],
            user_answer=clean_answer,
            category=interview["category"],
            difficulty=interview["difficulty"],
            job_role=interview.get("job_role"),
            branch=interview.get("branch"),
            experience_level=interview.get("experience_level")
        )
    except (groq_service.GroqAPIError, groq_service.GroqConfigurationError, groq_service.GroqValidationError) as e:
        logger.error(f"Groq API evaluation failed: {type(e).__name__}")
        # State in MongoDB is NOT modified on Groq failure!
        return jsonify({
            "success": False,
            "error": "AI evaluation service is temporarily unavailable. Please try submitting your answer again."
        }), 503
    except Exception as e:
        logger.error(f"Unexpected evaluation error: {type(e).__name__}")
        return jsonify({"success": False, "error": "Failed to evaluate candidate answer."}), 500

    # Update question state in MongoDB
    try:
        db.interviews.update_one(
            {"_id": interview["_id"], "questions.question_number": target_q_num},
            {
                "$set": {
                    "questions.$.user_answer": clean_answer,
                    "questions.$.answered": True,
                    "questions.$.score": eval_result["score"],
                    "questions.$.classification": eval_result.get("classification"),
                    "questions.$.evaluation": eval_result,
                    "questions.$.evaluated_at": datetime.now(timezone.utc)
                },
                "$inc": {"completed_questions": 1}
            }
        )

        completed_count = interview.get("completed_questions", 0) + 1
        total_questions = interview.get("total_questions", 3)
        is_all_complete = completed_count >= total_questions

        return jsonify({
            "success": True,
            "message": "Answer evaluated and saved successfully.",
            "question_number": target_q_num,
            "score": eval_result["score"],
            "classification": eval_result.get("classification"),
            "evaluation": eval_result,
            "is_all_complete": is_all_complete,
            "completed_questions": completed_count,
            "total_questions": total_questions
        }), 200

    except Exception as e:
        logger.error(f"Failed to save evaluated answer to MongoDB: {type(e).__name__}")
        return jsonify({"success": False, "error": "Database error saving answer evaluation."}), 500


# ==============================================================================
# 6. POST /api/interviews/<id>/finish — Complete Interview & Generate Report
# ==============================================================================

@interview_api_bp.route("/<interview_id>/finish", methods=["POST"])
@login_required
def finish_interview(interview_id):
    """
    POST /api/interviews/<id>/finish
    Marks interview as completed, calculates average score and final performance report.
    Idempotent: if already completed, returns existing report.
    """
    db = db_service.get_db()
    if db is None:
        return jsonify({"success": False, "error": "Database service is currently unavailable."}), 503

    user_id = session["user"]["id"]
    interview, err = get_verified_interview(interview_id, user_id, db)
    if err:
        return jsonify(err[0]), err[1]

    # If already finished, return the stored report
    if interview.get("status") == "completed" and interview.get("report"):
        return jsonify({
            "success": True,
            "message": "Interview was already completed.",
            "report": interview["report"]
        }), 200

    questions = interview.get("questions", [])
    answered_qs = [q for q in questions if q.get("answered")]
    overall_score = interview_service.calculate_overall_score(answered_qs)
    summary = calculate_performance_summary(
        answered_qs,
        category=interview.get("category", "Technical"),
        job_role=interview.get("job_role", "Software Engineer")
    )

    now_utc = datetime.now(timezone.utc)

    report_payload = {
        "interview_id": str(interview["_id"]),
        "branch": interview.get("branch", "CSE"),
        "job_role": interview.get("job_role", "Software Engineer"),
        "experience_level": interview.get("experience_level", "Fresher"),
        "category": interview["category"],
        "difficulty": interview["difficulty"],
        "duration_minutes": interview.get("duration_minutes", 15),
        "total_questions": interview.get("total_questions", len(questions)),
        "completed_questions": len(answered_qs),
        "overall_score": overall_score,
        "summary": summary,
        "completed_at": now_utc.isoformat(),
        "questions": [
            {
                "question_number": q["question_number"],
                "question": q["question"],
                "score": q.get("score", 0),
                "classification": q.get("classification") or (q.get("evaluation") or {}).get("classification"),
                "user_answer": q.get("user_answer", ""),
                "evaluation": q.get("evaluation")
            }
            for q in answered_qs
        ]
    }

    try:
        db.interviews.update_one(
            {"_id": interview["_id"]},
            {
                "$set": {
                    "status": "completed",
                    "overall_score": overall_score,
                    "completed_questions": len(answered_qs),
                    "completed_at": now_utc,
                    "report": report_payload
                }
            }
        )

        return jsonify({
            "success": True,
            "message": "Interview finished successfully.",
            "report": report_payload
        }), 200

    except Exception as e:
        logger.error(f"Error finishing interview: {type(e).__name__}")
        return jsonify({"success": False, "error": "Database error finalizing interview."}), 500


# ==============================================================================
# 7. GET /api/interviews/<id>/report — Retrieve Completed Report
# ==============================================================================

@interview_api_bp.route("/<interview_id>/report", methods=["GET"])
@login_required
def get_interview_report(interview_id):
    """
    GET /api/interviews/<id>/report
    Retrieves the completed performance report for an interview.
    Returns 400 if interview is still in progress.
    """
    db = db_service.get_db()
    if db is None:
        return jsonify({"success": False, "error": "Database service is currently unavailable."}), 503

    user_id = session["user"]["id"]
    interview, err = get_verified_interview(interview_id, user_id, db)
    if err:
        return jsonify(err[0]), err[1]

    if interview.get("status") != "completed":
        return jsonify({
            "success": False,
            "error": "Interview is still in progress. Please finish the interview to view the completed report."
        }), 400

    report = interview.get("report")
    if not report:
        # Re-compute if status was marked completed without stored report
        answered_qs = [q for q in interview.get("questions", []) if q.get("answered")]
        overall_score = interview_service.calculate_overall_score(answered_qs)
        summary = calculate_performance_summary(
            answered_qs,
            category=interview.get("category", "Technical"),
            job_role=interview.get("job_role", "Software Engineer")
        )

        report = {
            "interview_id": str(interview["_id"]),
            "category": interview["category"],
            "difficulty": interview["difficulty"],
            "job_role": interview.get("job_role", "Software Engineer"),
            "total_questions": interview.get("total_questions", len(interview.get("questions", []))),
            "completed_questions": len(answered_qs),
            "overall_score": overall_score,
            "summary": summary,
            "completed_at": (interview.get("completed_at") or datetime.now(timezone.utc)).isoformat() if isinstance(interview.get("completed_at"), datetime) else str(interview.get("completed_at")),
            "questions": answered_qs
        }

    return jsonify({
        "success": True,
        "report": report
    }), 200
