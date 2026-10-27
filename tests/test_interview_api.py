"""
Unit and integration tests for the Interview Workflow REST API:
- POST /api/interviews
- GET  /api/interviews
- GET  /api/interviews/<id>
- POST /api/interviews/<id>/answer
- POST /api/interviews/<id>/next
- POST /api/interviews/<id>/finish
- GET  /api/interviews/<id>/report
"""
import pytest
from unittest.mock import MagicMock
from bson.objectid import ObjectId

import app.services.db as db_module
import src.groq_service as groq_service
from src.groq_service import GroqAPIError, GroqConfigurationError


# ==============================================================================
# TEST FIXTURES & HELPERS
# ==============================================================================

@pytest.fixture
def auth_user_a(client):
    """Logs in as Student A."""
    user_id = str(ObjectId())
    user_data = {
        "id": user_id,
        "name": "Student A",
        "email": "student.a@example.com",
        "target_role": "Backend Engineer"
    }
    with client.session_transaction() as sess:
        sess["user"] = user_data
    return user_data


@pytest.fixture
def auth_user_b(client):
    """Logs in as Student B (different user for ownership testing)."""
    user_id = str(ObjectId())
    user_data = {
        "id": user_id,
        "name": "Student B",
        "email": "student.b@example.com",
        "target_role": "Frontend Engineer"
    }
    return user_data


def mock_groq_question(q_num=1):
    return {
        "question": f"Question {q_num}: How do database indexes optimize search performance?",
        "category": "Technical",
        "difficulty": "Medium",
        "topic": "Database Indexing",
        "expected_aspects": ["B-Tree structures", "Lookup complexity", "Write overhead trade-offs"]
    }


def mock_groq_evaluation(score=85):
    classification = "correct" if score >= 75 else ("partially_correct" if score >= 50 else "incorrect")
    return {
        "score": score,
        "classification": classification,
        "correct_concepts": ["Clear explanation of logarithmic search", "Highlighted write latency impact"],
        "mistakes": ["Could mention covering indexes"],
        "missing_concepts": ["Composite indexes and index-only scans"],
        "explanation": "B-Trees reduce lookup time to O(log n), but each index adds write overhead during inserts and updates.",
        "improved_answer": "Indexes use balanced tree structures (B-Trees) to provide logarithmic search times instead of full table scans.",
        "suggestions": ["Explore composite indexes for multi-column queries"],
        "communication_feedback": "Well-articulated and structured response.",
        "follow_up_question": "How would you handle index maintenance in a high-throughput write environment?",
        "feedback": "Comprehensive answer explaining B-Trees, search complexity, and insertion trade-offs.",
        "strengths": ["Clear explanation of logarithmic search", "Highlighted write latency impact"],
        "weaknesses": ["Could mention covering indexes"]
    }


# ==============================================================================
# 1. UNAUTHENTICATED REQUESTS BLOCKED (HTTP 401)
# ==============================================================================

def test_unauthenticated_api_requests_blocked(client):
    """Verify that unauthenticated requests to all /api/interviews endpoints return 401."""
    fake_id = str(ObjectId())
    endpoints = [
        ("POST", "/api/interviews", {"category": "Technical", "difficulty": "Easy"}),
        ("GET", "/api/interviews", None),
        ("GET", f"/api/interviews/{fake_id}", None),
        ("POST", f"/api/interviews/{fake_id}/next", None),
        ("POST", f"/api/interviews/{fake_id}/answer", {"answer": "Valid test answer here"}),
        ("POST", f"/api/interviews/{fake_id}/finish", None),
        ("GET", f"/api/interviews/{fake_id}/report", None),
    ]

    for method, url, payload in endpoints:
        if method == "POST":
            res = client.post(url, json=payload or {})
        else:
            res = client.get(url)

        assert res.status_code == 401, f"{method} {url} was not blocked for unauthenticated client!"
        data = res.get_json()
        assert data["success"] is False
        assert "authentication required" in data["error"].lower()


# ==============================================================================
# 2. OWNERSHIP & ID VALIDATION (HTTP 400, 403, 404)
# ==============================================================================

def test_invalid_interview_id_format(client, auth_user_a):
    """Test that malformed interview IDs return HTTP 400 Bad Request."""
    invalid_ids = ["not-an-id", "12345", "xyz-abc-12345"]
    for bad_id in invalid_ids:
        res = client.get(f"/api/interviews/{bad_id}")
        assert res.status_code == 400
        assert "invalid interview id" in res.get_json()["error"].lower()

        res_post = client.post(f"/api/interviews/{bad_id}/next")
        assert res_post.status_code == 400


def test_nonexistent_interview_returns_404(client, auth_user_a):
    """Test that a valid ObjectId that does not exist returns HTTP 404."""
    non_existent = str(ObjectId())
    res = client.get(f"/api/interviews/{non_existent}")
    assert res.status_code == 404
    assert "not found" in res.get_json()["error"].lower()


def test_ownership_protection_returns_403(client, auth_user_a, auth_user_b, monkeypatch):
    """
    STRICT SECURITY TEST:
    Verify that Student B cannot access, answer, or modify Student A's interview.
    """
    monkeypatch.setattr(
        groq_service,
        "generate_interview_question",
        lambda **kwargs: mock_groq_question(1)
    )

    # Student A creates interview
    create_res = client.post(
        "/api/interviews",
        json={"category": "Technical", "difficulty": "Medium", "total_questions": 3}
    )
    assert create_res.status_code == 201
    interview_id = create_res.get_json()["interview"]["id"]

    # Switch session to Student B
    with client.session_transaction() as sess:
        sess["user"] = auth_user_b

    # Student B attempts to access Student A's interview
    get_res = client.get(f"/api/interviews/{interview_id}")
    assert get_res.status_code == 403
    assert "permission" in get_res.get_json()["error"].lower()

    # Student B attempts to answer Student A's question
    ans_res = client.post(
        f"/api/interviews/{interview_id}/answer",
        json={"answer": "Hacker attempt to answer someone else's question."}
    )
    assert ans_res.status_code == 403

    # Student B attempts to call next on Student A's interview
    next_res = client.post(f"/api/interviews/{interview_id}/next")
    assert next_res.status_code == 403

    # Student B attempts to finish Student A's interview
    finish_res = client.post(f"/api/interviews/{interview_id}/finish")
    assert finish_res.status_code == 403

    # Student B attempts to get report
    report_res = client.get(f"/api/interviews/{interview_id}/report")
    assert report_res.status_code == 403


# ==============================================================================
# 3. INPUT VALIDATION TESTS (HTTP 400)
# ==============================================================================

def test_create_interview_input_validation(client, auth_user_a):
    """Verify category, difficulty, and question count validation."""
    # Invalid category
    res = client.post(
        "/api/interviews",
        json={"category": "Dancing", "difficulty": "Medium", "total_questions": 3}
    )
    assert res.status_code == 400
    assert "unsupported category" in res.get_json()["error"].lower()

    # Invalid difficulty
    res = client.post(
        "/api/interviews",
        json={"category": "Technical", "difficulty": "SuperHard", "total_questions": 3}
    )
    assert res.status_code == 400
    assert "unsupported difficulty" in res.get_json()["error"].lower()

    # Total questions out of range
    res = client.post(
        "/api/interviews",
        json={"category": "Technical", "difficulty": "Medium", "total_questions": 20}
    )
    assert res.status_code == 400
    assert "between 1 and 10" in res.get_json()["error"].lower()


def test_create_interview_with_extended_configuration(client, auth_user_a, monkeypatch):
    """Verify creating interview with branch, role, experience level, Mixed category, Beginner difficulty, duration."""
    captured_kwargs = {}

    def mock_gen_q(**kwargs):
        captured_kwargs.update(kwargs)
        return {
            "question": "What is Kirchhoff's Current Law in circuit theory?",
            "category": kwargs.get("category", "Mixed"),
            "difficulty": kwargs.get("difficulty", "Beginner"),
            "topic": "Circuit Analysis",
            "expected_aspects": ["Conservation of charge", "Node analysis"]
        }

    monkeypatch.setattr(groq_service, "generate_interview_question", mock_gen_q)

    payload = {
        "branch": "ECE",
        "job_role": "Custom",
        "custom_role": "Embedded Systems Engineer",
        "experience_level": "Internship",
        "category": "Mixed",
        "difficulty": "Beginner",
        "total_questions": 5,
        "duration_minutes": 20,
        "topic": "Microcontrollers"
    }

    res = client.post("/api/interviews", json=payload)
    assert res.status_code == 201
    data = res.get_json()
    assert data["success"] is True

    interview = data["interview"]
    assert interview["branch"] == "ECE"
    assert interview["job_role"] == "Embedded Systems Engineer"
    assert interview["experience_level"] == "Internship"
    assert interview["category"] == "Mixed"
    assert interview["difficulty"] == "Beginner"
    assert interview["duration_minutes"] == 20
    assert interview["topic"] == "Microcontrollers"
    assert interview["total_questions"] == 5

    # Verify kwargs were passed to Groq generator
    assert captured_kwargs["branch"] == "ECE"
    assert captured_kwargs["experience_level"] == "Internship"
    assert captured_kwargs["job_role"] == "Embedded Systems Engineer"
    assert captured_kwargs["category"] == "Mixed"


def test_answer_input_validation(client, auth_user_a, monkeypatch):

    """Verify answer text length constraints (min 5, max 5000 chars)."""
    monkeypatch.setattr(
        groq_service,
        "generate_interview_question",
        lambda **kwargs: mock_groq_question(1)
    )

    create_res = client.post(
        "/api/interviews",
        json={"category": "Technical", "difficulty": "Easy", "total_questions": 2}
    )
    interview_id = create_res.get_json()["interview"]["id"]

    # Empty answer
    res = client.post(f"/api/interviews/{interview_id}/answer", json={"answer": "   "})
    assert res.status_code == 400
    assert "required" in res.get_json()["error"].lower()

    # Answer too short (< 5 chars)
    res = client.post(f"/api/interviews/{interview_id}/answer", json={"answer": "abc"})
    assert res.status_code == 400
    assert "at least 5 characters" in res.get_json()["error"].lower()

    # Answer too long (> 5000 chars)
    res = client.post(f"/api/interviews/{interview_id}/answer", json={"answer": "A" * 5001})
    assert res.status_code == 400
    assert "cannot exceed 5000" in res.get_json()["error"].lower()


# ==============================================================================
# 4. FULL SUCCESSFUL INTERVIEW WORKFLOW
# ==============================================================================

def test_full_successful_interview_workflow(client, auth_user_a, monkeypatch):
    """
    Tests the complete end-to-end interview workflow:
    1. POST /api/interviews — creates interview with Question 1
    2. GET  /api/interviews/<id> — inspect active session
    3. POST /api/interviews/<id>/answer — answer Question 1
    4. POST /api/interviews/<id>/next — generate Question 2
    5. POST /api/interviews/<id>/answer — answer Question 2
    6. POST /api/interviews/<id>/finish — finish session and calculate final report
    7. GET  /api/interviews/<id>/report — verify completed report
    8. GET  /api/interviews — verify interview appears in student list
    """
    call_count = {"q": 0}

    def mock_generate(**kwargs):
        call_count["q"] += 1
        return mock_groq_question(call_count["q"])

    monkeypatch.setattr(groq_service, "generate_interview_question", mock_generate)
    monkeypatch.setattr(groq_service, "evaluate_interview_answer", lambda **kwargs: mock_groq_evaluation(90))

    # 1. Create 2-question interview
    create_res = client.post(
        "/api/interviews",
        json={
            "category": "Technical",
            "difficulty": "Medium",
            "job_role": "Backend Engineer",
            "total_questions": 2
        }
    )
    assert create_res.status_code == 201
    int_data = create_res.get_json()["interview"]
    interview_id = int_data["id"]
    assert len(int_data["questions"]) == 1
    assert int_data["status"] == "in_progress"

    # 2. Retrieve session
    get_res = client.get(f"/api/interviews/{interview_id}")
    assert get_res.status_code == 200
    assert get_res.get_json()["interview"]["id"] == interview_id

    # 3. Answer Question 1
    ans1_res = client.post(
        f"/api/interviews/{interview_id}/answer",
        json={"answer": "Indexes use B-trees to provide O(log n) lookup times instead of full table scans."}
    )
    assert ans1_res.status_code == 200
    ans1_data = ans1_res.get_json()
    assert ans1_data["score"] == 90
    assert ans1_data["is_all_complete"] is False

    # 4. Generate Question 2
    next_res = client.post(f"/api/interviews/{interview_id}/next")
    assert next_res.status_code == 200
    next_data = next_res.get_json()
    assert next_data["question_number"] == 2
    assert next_data["is_new"] is True

    # 5. Answer Question 2
    ans2_res = client.post(
        f"/api/interviews/{interview_id}/answer",
        json={"answer": "Sharding distributes database write load horizontally across nodes."}
    )
    assert ans2_res.status_code == 200
    ans2_data = ans2_res.get_json()
    assert ans2_data["is_all_complete"] is True

    # 6. Finish Interview
    finish_res = client.post(f"/api/interviews/{interview_id}/finish")
    assert finish_res.status_code == 200
    report = finish_res.get_json()["report"]
    assert report["overall_score"] == 90.0
    assert report["completed_questions"] == 2
    assert len(report["summary"]["strengths"]) > 0

    # 7. Get Report
    report_res = client.get(f"/api/interviews/{interview_id}/report")
    assert report_res.status_code == 200
    assert report_res.get_json()["report"]["overall_score"] == 90.0

    # 8. List student's interviews
    list_res = client.get("/api/interviews")
    assert list_res.status_code == 200
    list_data = list_res.get_json()
    assert list_data["count"] >= 1
    matching = [i for i in list_data["interviews"] if i["id"] == interview_id]
    assert len(matching) == 1
    assert matching[0]["status"] == "completed"
    assert matching[0]["overall_score"] == 90.0


# ==============================================================================
# 5. COMPLETED IMMUTABILITY & DUPLICATE SUBMISSION PREVENTION
# ==============================================================================

def test_duplicate_submission_prevented(client, auth_user_a, monkeypatch):
    """Verify that submitting an answer to an already answered question returns HTTP 400."""
    monkeypatch.setattr(groq_service, "generate_interview_question", lambda **kwargs: mock_groq_question(1))
    monkeypatch.setattr(groq_service, "evaluate_interview_answer", lambda **kwargs: mock_groq_evaluation(75))

    create_res = client.post(
        "/api/interviews",
        json={"category": "Technical", "difficulty": "Easy", "total_questions": 2}
    )
    interview_id = create_res.get_json()["interview"]["id"]

    # Submit first answer
    ans_res = client.post(
        f"/api/interviews/{interview_id}/answer",
        json={"answer": "This is the initial legitimate student answer."}
    )
    assert ans_res.status_code == 200

    # Attempt to submit answer again for the exact same question
    dup_res = client.post(
        f"/api/interviews/{interview_id}/answer",
        json={"question_number": 1, "answer": "Attempting to change my answer after seeing feedback."}
    )
    assert dup_res.status_code == 400
    assert "already been answered" in dup_res.get_json()["error"].lower()


def test_cannot_answer_or_advance_completed_interview(client, auth_user_a, monkeypatch):
    """Verify that once an interview is finished, answer and next calls return HTTP 400."""
    monkeypatch.setattr(groq_service, "generate_interview_question", lambda **kwargs: mock_groq_question(1))
    monkeypatch.setattr(groq_service, "evaluate_interview_answer", lambda **kwargs: mock_groq_evaluation(80))

    create_res = client.post(
        "/api/interviews",
        json={"category": "Technical", "difficulty": "Easy", "total_questions": 1}
    )
    interview_id = create_res.get_json()["interview"]["id"]

    client.post(
        f"/api/interviews/{interview_id}/answer",
        json={"answer": "Answering question 1 of 1."}
    )
    client.post(f"/api/interviews/{interview_id}/finish")

    # Calling answer on completed interview
    ans_res = client.post(
        f"/api/interviews/{interview_id}/answer",
        json={"answer": "Late answer submission."}
    )
    assert ans_res.status_code == 400
    assert "already been completed" in ans_res.get_json()["error"].lower()

    # Calling next on completed interview
    next_res = client.post(f"/api/interviews/{interview_id}/next")
    assert next_res.status_code == 400
    assert "already been completed" in next_res.get_json()["error"].lower()


def test_report_unavailable_for_in_progress_interview(client, auth_user_a, monkeypatch):
    """Verify that GET report returns 400 while interview is still in progress."""
    monkeypatch.setattr(groq_service, "generate_interview_question", lambda **kwargs: mock_groq_question(1))

    create_res = client.post(
        "/api/interviews",
        json={"category": "Technical", "difficulty": "Easy", "total_questions": 3}
    )
    interview_id = create_res.get_json()["interview"]["id"]

    report_res = client.get(f"/api/interviews/{interview_id}/report")
    assert report_res.status_code == 400
    assert "in progress" in report_res.get_json()["error"].lower()


# ==============================================================================
# 6. GROQ FAILURE HANDLING (STATE PRESERVATION)
# ==============================================================================

def test_failed_groq_evaluation_preserves_interview_state(client, auth_user_a, monkeypatch):
    """
    CRITICAL RELIABILITY TEST:
    If Groq AI evaluation fails (rate limit, timeout), the question is NOT marked as answered
    and NO fabricated score is saved to MongoDB. The student can retry.
    """
    monkeypatch.setattr(groq_service, "generate_interview_question", lambda **kwargs: mock_groq_question(1))

    # Mock Groq evaluation failing with rate limit
    def mock_failing_evaluation(**kwargs):
        raise GroqAPIError("Groq service rate limit exceeded.")

    monkeypatch.setattr(groq_service, "evaluate_interview_answer", mock_failing_evaluation)

    create_res = client.post(
        "/api/interviews",
        json={"category": "Technical", "difficulty": "Medium", "total_questions": 2}
    )
    interview_id = create_res.get_json()["interview"]["id"]

    # Student submits answer while AI service fails
    fail_res = client.post(
        f"/api/interviews/{interview_id}/answer",
        json={"answer": "A solid student answer that fails due to Groq outage."}
    )

    # Must return 503 Service Unavailable
    assert fail_res.status_code == 503
    assert "temporarily unavailable" in fail_res.get_json()["error"].lower()

    # Verify interview document in database was NOT corrupted or marked answered
    db = db_module.get_db()
    interview_in_db = db.interviews.find_one({"_id": ObjectId(interview_id)})
    q1 = interview_in_db["questions"][0]
    assert q1["answered"] is False
    assert q1["score"] is None
    assert q1["evaluation"] is None
    assert interview_in_db["completed_questions"] == 0

    # Student retries when AI recovers
    monkeypatch.setattr(groq_service, "evaluate_interview_answer", lambda **kwargs: mock_groq_evaluation(88))
    retry_res = client.post(
        f"/api/interviews/{interview_id}/answer",
        json={"answer": "Retrying after AI recovered."}
    )
    assert retry_res.status_code == 200
    assert retry_res.get_json()["score"] == 88


def test_failed_groq_next_question_preserves_state(client, auth_user_a, monkeypatch):
    """
    If Groq fails when generating next question, no corrupted question is added.
    """
    monkeypatch.setattr(groq_service, "generate_interview_question", lambda **kwargs: mock_groq_question(1))
    monkeypatch.setattr(groq_service, "evaluate_interview_answer", lambda **kwargs: mock_groq_evaluation(80))

    create_res = client.post(
        "/api/interviews",
        json={"category": "Technical", "difficulty": "Medium", "total_questions": 3}
    )
    interview_id = create_res.get_json()["interview"]["id"]

    # Answer question 1
    client.post(f"/api/interviews/{interview_id}/answer", json={"answer": "Answer to question 1."})

    # Groq fails on next question
    def mock_failing_question(**kwargs):
        raise GroqAPIError("Groq timeout generating question.")

    monkeypatch.setattr(groq_service, "generate_interview_question", mock_failing_question)

    fail_next = client.post(f"/api/interviews/{interview_id}/next")
    assert fail_next.status_code == 503

    # State in DB must still have only 1 question
    db = db_module.get_db()
    interview_in_db = db.interviews.find_one({"_id": ObjectId(interview_id)})
    assert len(interview_in_db["questions"]) == 1


# ==============================================================================
# 8. PHASE 2: EVALUATION SCHEMA PERSISTENCE & CONTEXTUAL FOLLOW-UPS
# ==============================================================================

def test_answer_submission_saves_rich_evaluation_schema(client, auth_user_a, monkeypatch):
    """
    Verify that submit_answer returns and persists the complete Phase 2 evaluation schema:
    score, classification, correct_concepts, mistakes, missing_concepts, explanation,
    improved_answer, suggestions, communication_feedback, and follow_up_question.
    """
    monkeypatch.setattr(groq_service, "generate_interview_question", lambda **kwargs: mock_groq_question(1))
    monkeypatch.setattr(groq_service, "evaluate_interview_answer", lambda **kwargs: mock_groq_evaluation(85))

    create_res = client.post(
        "/api/interviews",
        json={
            "branch": "CSE",
            "job_role": "Full Stack Developer",
            "experience_level": "Fresher",
            "category": "Technical",
            "difficulty": "Intermediate",
            "total_questions": 2
        }
    )
    assert create_res.status_code == 201
    interview_id = create_res.get_json()["interview"]["id"]

    ans_res = client.post(
        f"/api/interviews/{interview_id}/answer",
        json={"answer": "Database indexes structure records as balanced B-Trees to expedite lookups."}
    )
    assert ans_res.status_code == 200
    data = ans_res.get_json()

    # Check API response
    assert data["score"] == 85
    assert data["classification"] == "correct"
    eval_dict = data["evaluation"]
    assert eval_dict["classification"] == "correct"
    assert len(eval_dict["correct_concepts"]) > 0
    assert len(eval_dict["mistakes"]) > 0
    assert len(eval_dict["missing_concepts"]) > 0
    assert "explanation" in eval_dict
    assert "improved_answer" in eval_dict
    assert "suggestions" in eval_dict
    assert "communication_feedback" in eval_dict
    assert "follow_up_question" in eval_dict

    # Check MongoDB persistence
    db = db_module.get_db()
    interview_doc = db.interviews.find_one({"_id": ObjectId(interview_id)})
    q1 = interview_doc["questions"][0]
    assert q1["answered"] is True
    assert q1["score"] == 85
    assert q1["classification"] == "correct"
    assert q1["evaluation"]["improved_answer"] == eval_dict["improved_answer"]


def test_next_question_passes_previous_answers_for_followup(client, auth_user_a, monkeypatch):
    """
    Verify that get_or_generate_next_question collects answered Q&A and passes
    them to groq_service.generate_interview_question as previous_answers.
    """
    monkeypatch.setattr(groq_service, "generate_interview_question", lambda **kwargs: mock_groq_question(1))
    monkeypatch.setattr(groq_service, "evaluate_interview_answer", lambda **kwargs: mock_groq_evaluation(80))

    create_res = client.post(
        "/api/interviews",
        json={
            "branch": "ECE",
            "job_role": "IoT Engineer",
            "experience_level": "Fresher",
            "category": "Technical",
            "difficulty": "Intermediate",
            "total_questions": 3
        }
    )
    interview_id = create_res.get_json()["interview"]["id"]

    # Submit answer for Question 1
    sample_answer = "MQTT is a lightweight publish-subscribe protocol ideal for low-bandwidth IoT devices."
    client.post(
        f"/api/interviews/{interview_id}/answer",
        json={"answer": sample_answer}
    )

    # Spy on generate_interview_question for Question 2
    captured_kwargs = {}

    def spy_generate(**kwargs):
        captured_kwargs.update(kwargs)
        return mock_groq_question(2)

    monkeypatch.setattr(groq_service, "generate_interview_question", spy_generate)

    next_res = client.post(f"/api/interviews/{interview_id}/next")
    assert next_res.status_code == 200

    # Verify captured args
    assert captured_kwargs["branch"] == "ECE"
    assert captured_kwargs["job_role"] == "IoT Engineer"
    assert captured_kwargs["experience_level"] == "Fresher"
    assert "previous_answers" in captured_kwargs
    prev_ans = captured_kwargs["previous_answers"]
    assert len(prev_ans) == 1
    assert prev_ans[0]["user_answer"] == sample_answer


def test_report_contains_rich_performance_summary_and_metadata(client, auth_user_a, monkeypatch):
    """
    Verify final performance report contains branch, role, experience level, duration,
    and performance summary with correct_concepts, mistakes, and missing_concepts.
    """
    monkeypatch.setattr(groq_service, "generate_interview_question", lambda **kwargs: mock_groq_question(1))
    monkeypatch.setattr(groq_service, "evaluate_interview_answer", lambda **kwargs: mock_groq_evaluation(88))

    create_res = client.post(
        "/api/interviews",
        json={
            "branch": "IT",
            "job_role": "DevOps Engineer",
            "experience_level": "Internship",
            "category": "Technical",
            "difficulty": "Intermediate",
            "duration_minutes": 20,
            "total_questions": 1
        }
    )
    interview_id = create_res.get_json()["interview"]["id"]

    client.post(
        f"/api/interviews/{interview_id}/answer",
        json={"answer": "Docker containers package an application and its dependencies into a standard unit."}
    )

    finish_res = client.post(f"/api/interviews/{interview_id}/finish")
    assert finish_res.status_code == 200
    report = finish_res.get_json()["report"]

    assert report["branch"] == "IT"
    assert report["job_role"] == "DevOps Engineer"
    assert report["experience_level"] == "Internship"
    assert report["duration_minutes"] == 20
    assert report["overall_score"] == 88.0

    summary = report["summary"]
    assert "strengths" in summary
    assert "weaknesses" in summary
    assert "suggestions" in summary
    assert "correct_concepts" in summary
    assert "mistakes" in summary
    assert "missing_concepts" in summary

    assert len(report["questions"]) == 1
    assert report["questions"][0]["classification"] == "correct"

