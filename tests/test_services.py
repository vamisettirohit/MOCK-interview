import pytest
from unittest.mock import MagicMock
import json
from src.groq_service import generate_interview_question, evaluate_interview_answer
from app.utils.validators import validate_registration, validate_interview_setup

def test_registration_validation():
    """Test validation rules for registration form."""
    # Valid data
    valid, msg = validate_registration("John Doe", "john@example.com", "Password123!", "Password123!")
    assert valid is True
    assert not msg

    # Passwords do not match
    valid, msg = validate_registration("John Doe", "john@example.com", "Password123!", "Mismatch123!")
    assert valid is False
    assert "match" in msg.lower()

    # Short password
    valid, msg = validate_registration("John Doe", "john@example.com", "123", "123")
    assert valid is False
    assert "characters" in msg.lower()

def test_interview_setup_validation():
    """Test interview setup wizard inputs."""
    # Existing legacy category & difficulty compatibility
    valid, msg = validate_interview_setup("Full Stack Web Development", "Medium", "3")
    assert valid is True

    valid, msg = validate_interview_setup("Invalid Category", "Medium", "3")
    assert valid is False

    # Extended options: Mixed track, Beginner difficulty, Branch, Experience level, Duration
    valid, msg = validate_interview_setup(
        category="Mixed",
        difficulty="Beginner",
        num_questions="5",
        branch="ECE",
        experience_level="Fresher",
        duration="20"
    )
    assert valid is True
    assert not msg

    # Intermediate / Advanced
    valid, msg = validate_interview_setup(
        category="Technical",
        difficulty="Advanced",
        num_questions="7",
        branch="Mechanical",
        experience_level="Experienced",
        duration="45"
    )
    assert valid is True

    # Invalid branch
    valid, msg = validate_interview_setup(
        category="Technical",
        difficulty="Intermediate",
        num_questions="3",
        branch="   "
    )
    assert valid is False
    assert "branch" in msg.lower()

    # Invalid experience level
    valid, msg = validate_interview_setup(
        category="Technical",
        difficulty="Intermediate",
        num_questions="3",
        experience_level="Wizard"
    )
    assert valid is False
    assert "experience" in msg.lower()

    # Invalid duration
    valid, msg = validate_interview_setup(
        category="Technical",
        difficulty="Intermediate",
        num_questions="3",
        duration="999"
    )
    assert valid is False
    assert "duration" in msg.lower()

def test_groq_service_mocked_execution():
    """Test groq_service question generation and answer evaluation using mocked client."""
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps({
        "question": "Explain closure in JavaScript.",
        "category": "Technical",
        "difficulty": "Medium",
        "topic": "JavaScript",
        "expected_aspects": ["Lexical scope", "Function returning function"]
    })
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])

    result = generate_interview_question("Technical", "Medium", "JavaScript", [], client=mock_client, model="test-model")
    assert "question" in result
    assert result["category"] == "Technical"

    # Mock answer evaluation
    mock_eval_choice = MagicMock()
    mock_eval_choice.message.content = json.dumps({
        "score": 85,
        "feedback": "Clear explanation of closures with lexical scope examples.",
        "strengths": ["Clear explanation", "Good terminology"],
        "weaknesses": ["Could mention memory leaks"],
        "suggestions": ["Include practical garbage collection notes"]
    })
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_eval_choice])

    eval_res = evaluate_interview_answer("Explain closure in JS", "A closure gives you access to an outer function's scope.", "Technical", "Medium", client=mock_client, model="test-model")
    assert eval_res["score"] == 85
    assert "feedback" in eval_res
    assert isinstance(eval_res["strengths"], list)


# ==============================================================================
# PHASE 5: INTERVIEW SERVICE & SCORECARD UNIT TESTS
# ==============================================================================

def test_calculate_overall_score_accuracy():
    """Verify arithmetic average calculation, empty cases, and non-numeric safety."""
    from app.services.interview_service import calculate_overall_score

    # Standard valid evaluations
    questions = [
        {"score": 80, "answered": True},
        {"score": 90, "answered": True},
        {"score": 85, "answered": True}
    ]
    assert calculate_overall_score(questions) == 85.0

    # Incomplete or mixed scores
    mixed = [
        {"score": 70, "answered": True},
        {"score": None, "answered": False},
        {"score": "invalid", "answered": True},
        {"score": 90, "answered": True}
    ]
    assert calculate_overall_score(mixed) == 80.0

    # Fallback to nested evaluation dict score if top-level missing
    nested = [
        {"evaluation": {"score": 95}, "answered": True},
        {"score": 85, "answered": True}
    ]
    assert calculate_overall_score(nested) == 90.0

    # Empty list or None
    assert calculate_overall_score([]) == 0.0
    assert calculate_overall_score(None) == 0.0

    # Clamping out-of-range scores
    clamped = [
        {"score": 150, "answered": True},
        {"score": -10, "answered": True}
    ]
    assert calculate_overall_score(clamped) == 50.0  # (100 + 0) / 2


def test_calculate_performance_summary_aggregation():
    """Verify aggregation of strengths, weaknesses, mistakes, missing concepts, and practice topics."""
    from app.services.interview_service import calculate_performance_summary

    answered_questions = [
        {
            "topic": "Relational Databases",
            "score": 65,
            "classification": "partially_correct",
            "evaluation": {
                "score": 65,
                "strengths": ["Understands ACID transactions"],
                "weaknesses": ["Omitted foreign key constraints"],
                "mistakes": ["Confused optimistic with pessimistic locking"],
                "missing_concepts": ["Isolation levels (Repeatable Read)"],
                "suggestions": ["Study concurrency controls in PostgreSQL"]
            }
        },
        {
            "topic": "RESTful API Design",
            "score": 90,
            "classification": "correct",
            "evaluation": {
                "score": 90,
                "strengths": ["Clean idempotent HTTP verbs"],
                "weaknesses": ["Could mention HATEOAS"],
                "mistakes": [],
                "missing_concepts": ["API rate-limiting headers"],
                "suggestions": ["Explore OpenAPI 3.0 specifications"]
            }
        }
    ]

    summary = calculate_performance_summary(answered_questions, category="Technical", job_role="Backend Developer")

    # Verify lists are populated
    assert "Understands ACID transactions" in summary["strengths"]
    assert "Clean idempotent HTTP verbs" in summary["strengths"]
    assert any("pessimistic" in m for m in summary["mistakes"])
    assert any("Isolation" in mc for mc in summary["missing_concepts"])
    assert len(summary["suggestions"]) >= 2

    # Verify recommended practice topics prioritize weaker topics and missing concepts
    assert "recommended_topics" in summary
    assert len(summary["recommended_topics"]) > 0
    # Lower scoring topic "Relational Databases" should be prioritized
    assert any("Relational" in t or "Isolation" in t for t in summary["recommended_topics"])


def test_build_performance_report_structure():
    """Verify build_performance_report constructs valid scorecard payload."""
    from app.services.interview_service import build_performance_report

    interview_doc = {
        "_id": "507f1f77bcf86cd799439011",
        "category": "Technical",
        "difficulty": "Medium",
        "branch": "CSE",
        "job_role": "Full Stack Engineer",
        "experience_level": "Fresher",
        "duration_minutes": 15,
        "total_questions": 2,
        "status": "completed",
        "questions": [
            {
                "question_number": 1,
                "question": "What is the Virtual DOM in React?",
                "answered": True,
                "score": 85,
                "classification": "correct",
                "user_answer": "In-memory representation of real DOM elements.",
                "evaluation": {
                    "score": 85,
                    "strengths": ["Clear definition of in-memory tree diffing"],
                    "weaknesses": ["Could explain reconciliation algorithm"],
                    "suggestions": ["Study Fiber reconciler"]
                }
            }
        ]
    }

    report = build_performance_report(interview_doc)
    assert report["interview_id"] == "507f1f77bcf86cd799439011"
    assert report["category"] == "Technical"
    assert report["overall_score"] == 85.0
    assert report["completed_questions"] == 1
    assert "summary" in report
    assert len(report["questions"]) == 1
    assert report["questions"][0]["score"] == 85


def test_interview_service_score_ratings():
    """Verify score rating labels and badges."""
    from app.services.interview_service import get_score_rating

    rating, badge = get_score_rating(95)
    assert rating == "Outstanding"
    assert badge == "badge-easy"

    rating, badge = get_score_rating(72)
    assert rating == "Proficient"
    assert badge == "badge-medium"

    rating, badge = get_score_rating(45)
    assert rating == "Needs Practice"
    assert badge == "badge-hard"

