"""
Unit and integration tests for src/groq_service.py.
All unit tests use a mocked Groq client to guarantee zero API request consumption.
"""
import os
import json
import pytest
from unittest.mock import MagicMock
from groq import (
    APITimeoutError,
    RateLimitError,
    NotFoundError,
    AuthenticationError,
    APIConnectionError,
    APIError,
)

import src.groq_service as groq_service
from src.groq_service import (
    generate_interview_question,
    evaluate_interview_answer,
    normalize_category,
    normalize_difficulty,
    safe_parse_json,
    validate_evaluation_payload,
    get_groq_config,
    SUPPORTED_CATEGORIES,
    SUPPORTED_DIFFICULTIES,
    GroqServiceError,
    GroqConfigurationError,
    GroqAPIError,
    GroqValidationError,
)


# ==============================================================================
# 1. GROQ_MODEL & CONFIGURATION TESTS
# ==============================================================================

def test_missing_groq_model_env_var(monkeypatch):
    """Test that missing GROQ_MODEL raises GroqConfigurationError without assuming a model."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_mock_key_12345")
    monkeypatch.delenv("GROQ_MODEL", raising=False)

    with pytest.raises(GroqConfigurationError) as exc_info:
        get_groq_config()
    assert "GROQ_MODEL" in str(exc_info.value)


def test_missing_groq_api_key_env_var(monkeypatch):
    """Test that missing GROQ_API_KEY raises GroqConfigurationError."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_MODEL", "qwen/qwen3.8-27b")

    with pytest.raises(GroqConfigurationError) as exc_info:
        get_groq_config()
    assert "GROQ_API_KEY" in str(exc_info.value)


def test_custom_model_loaded_from_env(monkeypatch):
    """Verify that the model ID is dynamically read from GROQ_MODEL."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_mock_key_12345")
    monkeypatch.setenv("GROQ_MODEL", "custom-org/future-model-v2")

    api_key, model = get_groq_config()
    assert api_key == "gsk_test_mock_key_12345"
    assert model == "custom-org/future-model-v2"


# ==============================================================================
# 2. CATEGORY & DIFFICULTY NORMALIZATION TESTS
# ==============================================================================

def test_supported_categories():
    """Verify Technical, HR, Aptitude, and Communication are supported."""
    for cat in ["Technical", "HR", "Aptitude", "Communication"]:
        assert normalize_category(cat) == cat
        assert normalize_category(cat.lower()) == cat
        assert normalize_category(cat.upper()) == cat

    # Partial/contextual matching
    assert normalize_category("Technical - Full Stack") == "Technical"
    assert normalize_category("General HR Interview") == "HR"
    assert normalize_category("Quantitative Aptitude") == "Aptitude"
    assert normalize_category("Communication Skills") == "Communication"

    with pytest.raises(ValueError):
        normalize_category("InvalidRandomCategory")


def test_supported_difficulties():
    """Verify Easy, Medium, and Hard are properly validated."""
    for diff in ["Easy", "Medium", "Hard"]:
        assert normalize_difficulty(diff) == diff
        assert normalize_difficulty(diff.lower()) == diff

    with pytest.raises(ValueError):
        normalize_difficulty("Impossible")


# ==============================================================================
# 3. MOCKED QUESTION GENERATION TESTS (Zero API Consumption)
# ==============================================================================

def build_mock_completion(content_dict: dict):
    """Helper to build a mock Groq ChatCompletion structure."""
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps(content_dict)
    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]
    return mock_completion


def test_generate_question_mocked(monkeypatch):
    """Test question generation with mocked Groq client without giving away answer."""
    mock_payload = {
        "question": "How does virtual DOM reconciliation work in React?",
        "category": "Technical",
        "difficulty": "Medium",
        "topic": "React Architecture",
        "expected_aspects": ["Diffing algorithm", "Key prop usage", "Batching updates"]
    }

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = build_mock_completion(mock_payload)

    result = generate_interview_question(
        category="Technical",
        difficulty="Medium",
        job_role="Frontend Engineer",
        client=mock_client,
        model="mock-test-model"
    )

    assert result["question"] == mock_payload["question"]
    assert result["category"] == "Technical"
    assert result["difficulty"] == "Medium"
    assert result["topic"] == "React Architecture"
    assert len(result["expected_aspects"]) == 3

    # Verify model and prompt passed to client
    mock_client.chat.completions.create.assert_called_once()
    kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "mock-test-model"
    assert kwargs["response_format"] == {"type": "json_object"}
    # Ensure instructions forbid giving away answers
    user_prompt = kwargs["messages"][1]["content"]
    assert "NOT include the answer" in user_prompt or "without revealing" in user_prompt or "NOT contain or reveal" in user_prompt


# ==============================================================================
# 4. MOCKED ANSWER EVALUATION TESTS (Zero API Consumption)
# ==============================================================================

def test_evaluate_answer_mocked(monkeypatch):
    """Test comprehensive answer evaluation with mocked Groq client."""
    mock_payload = {
        "score": 88,
        "feedback": "Strong answer demonstrating relevance, conceptual accuracy, and clear communication.",
        "strengths": ["Accurately explained diffing algorithm", "Mentioned performance implications"],
        "weaknesses": ["Did not mention heuristic assumptions of O(n) complexity"],
        "suggestions": ["Include time complexity trade-offs in your next response"]
    }

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = build_mock_completion(mock_payload)

    result = evaluate_interview_answer(
        question_text="How does virtual DOM reconciliation work in React?",
        user_answer="React creates a virtual representation of the DOM. On state change, it diffs the old and new trees.",
        category="Technical",
        difficulty="Medium",
        client=mock_client,
        model="mock-test-model"
    )

    assert result["score"] == 88
    assert "feedback" in result
    assert len(result["strengths"]) == 2
    assert len(result["weaknesses"]) == 1
    assert len(result["suggestions"]) == 1

    # Verify evaluation criteria are present in prompt
    kwargs = mock_client.chat.completions.create.call_args.kwargs
    prompt = kwargs["messages"][1]["content"]
    assert "Relevance" in prompt
    assert "Correctness" in prompt
    assert "Clarity" in prompt
    assert "Completeness" in prompt


def test_empty_user_answer_scores_zero():
    """Verify that an empty or whitespace answer returns 0 score without calling API."""
    mock_client = MagicMock()
    result = evaluate_interview_answer(
        question_text="What is a hash table?",
        user_answer="   ",
        category="Technical",
        difficulty="Easy",
        client=mock_client
    )

    assert result["score"] == 0
    assert "No answer was provided" in result["feedback"]
    mock_client.chat.completions.create.assert_not_called()


# ==============================================================================
# 5. SERVER-SIDE VALIDATION & SAFE PARSING TESTS
# ==============================================================================

def test_safe_parse_json_strips_markdown_fences():
    """Verify that markdown code fences ```json ... ``` are cleanly stripped."""
    raw = "```json\n{\"score\": 90, \"feedback\": \"Good job\"}\n```"
    parsed = safe_parse_json(raw)
    assert parsed == {"score": 90, "feedback": "Good job"}


def test_safe_parse_json_rejects_malformed():
    """Verify that invalid JSON raises GroqValidationError."""
    with pytest.raises(GroqValidationError):
        safe_parse_json("Not a json at all")


def test_server_validation_rejects_invalid_score():
    """Verify server rejects out-of-range (<0 or >100) or non-numeric scores."""
    # Out of range > 100
    with pytest.raises(GroqValidationError):
        validate_evaluation_payload({
            "score": 150,
            "feedback": "Too high",
            "strengths": ["Good"],
            "weaknesses": ["None"],
            "suggestions": ["None"]
        })

    # Out of range < 0
    with pytest.raises(GroqValidationError):
        validate_evaluation_payload({
            "score": -5,
            "feedback": "Negative",
            "strengths": ["None"],
            "weaknesses": ["None"],
            "suggestions": ["None"]
        })

    # Non-numeric
    with pytest.raises(GroqValidationError):
        validate_evaluation_payload({
            "score": "A+",
            "feedback": "Letter grade",
            "strengths": ["None"],
            "weaknesses": ["None"],
            "suggestions": ["None"]
        })


def test_never_executes_model_text_as_code():
    """Security verification: model output containing executable code syntax is treated purely as string."""
    dangerous_text = "{\"question\": \"__import__('os').system('echo hacked')\", \"expected_aspects\": [\"none\"]}"
    parsed = safe_parse_json(dangerous_text)
    assert isinstance(parsed["question"], str)
    assert parsed["question"] == "__import__('os').system('echo hacked')"


# ==============================================================================
# 6. RECOVERABLE ERROR HANDLING (DO NOT INVENT SCORES ON FAILURE)
# ==============================================================================

def test_api_timeout_raises_recoverable_error():
    """Verify that an API timeout raises GroqAPIError and NEVER invents a score."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = APITimeoutError(request=MagicMock())

    with pytest.raises(GroqAPIError) as exc_info:
        evaluate_interview_answer(
            question_text="Explain quicksort.",
            user_answer="Quicksort divides an array using a pivot element.",
            category="Technical",
            difficulty="Medium",
            client=mock_client,
            model="test-model"
        )
    assert "timed out" in str(exc_info.value).lower()


def test_rate_limit_raises_recoverable_error():
    """Verify that a rate limit raises GroqAPIError and NEVER invents a score."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = RateLimitError(
        message="Rate limit exceeded",
        response=MagicMock(status_code=429),
        body={}
    )

    with pytest.raises(GroqAPIError) as exc_info:
        evaluate_interview_answer(
            question_text="Explain quicksort.",
            user_answer="Quicksort divides an array using a pivot element.",
            category="Technical",
            difficulty="Medium",
            client=mock_client,
            model="test-model"
        )
    assert "rate limit" in str(exc_info.value).lower()


def test_unavailable_model_raises_recoverable_error():
    """Verify that an unavailable model raises GroqAPIError and NEVER invents a score."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = NotFoundError(
        message="Model not found",
        response=MagicMock(status_code=404),
        body={}
    )

    with pytest.raises(GroqAPIError) as exc_info:
        evaluate_interview_answer(
            question_text="Explain quicksort.",
            user_answer="Quicksort divides an array using a pivot element.",
            category="Technical",
            difficulty="Medium",
            client=mock_client,
            model="non-existent-model"
        )
    assert "unavailable or invalid" in str(exc_info.value).lower()


def test_no_credentials_in_error_messages(monkeypatch):
    """Verify that sensitive API key (gsk_...) is never leaked in exceptions."""
    sensitive_key = "gsk_SECRET_KEY_NEVER_LEAK_9999"
    monkeypatch.setenv("GROQ_API_KEY", sensitive_key)
    monkeypatch.setenv("GROQ_MODEL", "qwen/qwen3.8-27b")

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = AuthenticationError(
        message=f"Invalid key: {sensitive_key}",
        response=MagicMock(status_code=401),
        body={}
    )

    with pytest.raises(GroqAPIError) as exc_info:
        evaluate_interview_answer(
            question_text="Explain polymorphism.",
            user_answer="Polymorphism allows objects to take multiple forms.",
            category="Technical",
            difficulty="Easy",
            client=mock_client
        )

    # The exception message presented to callers must NOT contain the sensitive key
    assert sensitive_key not in str(exc_info.value)


# ==============================================================================
# 7. PHASE 2: ENHANCED PROMPTS, EVALUATION SCHEMA & FOLLOW-UPS
# ==============================================================================

def test_generate_question_with_branch_and_followup():
    """Verify question generation includes branch, experience level, and previous answer context for follow-ups."""
    mock_payload = {
        "question": "Given your mention of setup time, what are the primary clock jitter trade-offs in sub-micron ASIC design?",
        "category": "Technical",
        "difficulty": "Intermediate",
        "topic": "Timing Closure",
        "expected_aspects": ["Clock skew vs jitter", "Hold time margin", "Sub-micron impact"]
    }

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = build_mock_completion(mock_payload)

    previous_answers = [
        {
            "question": "What is setup and hold time?",
            "user_answer": "Setup time is the minimum duration the data must be stable before the active clock edge."
        }
    ]

    result = generate_interview_question(
        category="Technical",
        difficulty="Intermediate",
        job_role="VLSI Design Engineer",
        branch="ECE",
        experience_level="Fresher",
        previous_questions=["What is setup and hold time?"],
        previous_answers=previous_answers,
        client=mock_client,
        model="mock-test-model"
    )

    assert result["question"] == mock_payload["question"]
    assert result["category"] == "Technical"
    assert result["difficulty"] == "Intermediate"

    mock_client.chat.completions.create.assert_called_once()
    kwargs = mock_client.chat.completions.create.call_args.kwargs
    prompt = kwargs["messages"][1]["content"]

    # Verify context is injected into the prompt
    assert "Engineering Branch: 'ECE'" in prompt
    assert "Candidate Experience Level: 'Fresher'" in prompt
    assert "Target Job Role: 'VLSI Design Engineer'" in prompt
    assert "PREVIOUS CANDIDATE RESPONSES IN THIS SESSION:" in prompt
    assert "Setup time is the minimum duration" in prompt
    assert "FOLLOW-UP GUIDANCE:" in prompt


def test_generate_question_mixed_category():
    """Verify Mixed category and Beginner difficulty normalization and prompt instructions."""
    mock_payload = {
        "question": "Explain how a microcontroller handles external interrupts and write a high-level flowchart.",
        "category": "Mixed",
        "difficulty": "Beginner",
        "topic": "Embedded Interrupts",
        "expected_aspects": ["Interrupt Service Routine (ISR)", "Interrupt Vector Table", "Latency considerations"]
    }

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = build_mock_completion(mock_payload)

    result = generate_interview_question(
        category="Mixed",
        difficulty="Beginner",
        job_role="Embedded Systems Engineer",
        branch="EEE",
        experience_level="Fresher",
        client=mock_client,
        model="mock-test-model"
    )

    assert result["category"] == "Mixed"
    assert result["difficulty"] == "Beginner"
    kwargs = mock_client.chat.completions.create.call_args.kwargs
    prompt = kwargs["messages"][1]["content"]
    assert "Engineering Branch: 'EEE'" in prompt
    assert "Category: Mixed" in prompt


def test_evaluate_answer_full_schema():
    """Verify evaluation returns complete Phase 2 structured schema with all required fields."""
    mock_payload = {
        "score": 85,
        "classification": "correct",
        "correct_concepts": [
            "Accurate definition of ACID properties",
            "Clear transaction isolation boundary example"
        ],
        "mistakes": [
            "Omitted phantom read anomaly under Repeatable Read"
        ],
        "missing_concepts": [
            "Multi-Version Concurrency Control (MVCC) snapshot isolation"
        ],
        "explanation": "Atomicity and Consistency are well described; however, isolation levels require deeper coverage of phantom reads and MVCC.",
        "improved_answer": "ACID guarantees database reliability. Atomicity ensures all-or-nothing execution, Consistency enforces schema constraints, Isolation avoids dirty/non-repeatable/phantom reads via MVCC or locking, and Durability ensures committed transactions persist across power failures via write-ahead logging.",
        "suggestions": [
            "Review MVCC and Serializable Snapshot Isolation in relational databases"
        ],
        "communication_feedback": "Well-structured explanation with clear engineering terminology.",
        "follow_up_question": "How does Write-Ahead Logging (WAL) ensure durability during a power failure?"
    }

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = build_mock_completion(mock_payload)

    result = evaluate_interview_answer(
        question_text="Explain the ACID properties in database management systems.",
        user_answer="Atomicity means all or nothing. Consistency ensures DB state is valid. Isolation keeps transactions independent. Durability ensures commits are saved.",
        category="Technical",
        difficulty="Intermediate",
        job_role="Backend Developer",
        branch="CSE",
        experience_level="Fresher",
        client=mock_client,
        model="mock-test-model"
    )

    # Validate Phase 2 schema fields
    assert result["score"] == 85
    assert result["classification"] == "correct"
    assert len(result["correct_concepts"]) == 2
    assert len(result["mistakes"]) == 1
    assert len(result["missing_concepts"]) == 1
    assert "Atomicity and Consistency" in result["explanation"]
    assert "ACID guarantees" in result["improved_answer"]
    assert len(result["suggestions"]) == 1
    assert "Well-structured" in result["communication_feedback"]
    assert "Write-Ahead Logging" in result["follow_up_question"]

    # Validate backward-compatible legacy fields
    assert "feedback" in result
    assert "strengths" in result
    assert "weaknesses" in result


def test_validate_evaluation_payload_classification_deduction():
    """Verify classification is deduced accurately from numerical score when omitted or partial."""
    # Score 85 -> "correct"
    res1 = validate_evaluation_payload({"score": 85, "explanation": "Good"})
    assert res1["classification"] == "correct"

    # Score 62 -> "partially_correct"
    res2 = validate_evaluation_payload({"score": 62, "explanation": "Partial"})
    assert res2["classification"] == "partially_correct"

    # Score 35 -> "incorrect"
    res3 = validate_evaluation_payload({"score": 35, "explanation": "Weak"})
    assert res3["classification"] == "incorrect"

    # Explicit string variation "Partially Correct"
    res4 = validate_evaluation_payload({"score": 70, "classification": "Partially Correct"})
    assert res4["classification"] == "partially_correct"


def test_empty_answer_returns_structured_zeros():
    """Verify empty/blank candidate answer returns score 0, incorrect classification, and sample answer."""
    mock_client = MagicMock()
    result = evaluate_interview_answer(
        question_text="Explain binary search complexity.",
        user_answer="",
        category="Technical",
        difficulty="Easy",
        client=mock_client
    )

    assert result["score"] == 0
    assert result["classification"] == "incorrect"
    assert result["correct_concepts"] == []
    assert len(result["mistakes"]) > 0
    assert len(result["missing_concepts"]) > 0
    assert "improved_answer" in result
    assert len(result["suggestions"]) > 0
    mock_client.chat.completions.create.assert_not_called()


def test_evaluate_answer_with_branch_and_experience_context():
    """Verify candidate's branch and experience level are included in the evaluation rubric prompt."""
    mock_payload = {
        "score": 92,
        "classification": "correct",
        "explanation": "Solid engineering reasoning.",
        "improved_answer": "Excellent response."
    }

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = build_mock_completion(mock_payload)

    evaluate_interview_answer(
        question_text="Describe finite element analysis meshing trade-offs.",
        user_answer="Coarser mesh solves faster but captures stress concentrations poorly. Finer mesh improves accuracy at high computational cost.",
        category="Technical",
        difficulty="Advanced",
        job_role="Structural Design Engineer",
        branch="Mechanical",
        experience_level="Experienced",
        client=mock_client
    )

    kwargs = mock_client.chat.completions.create.call_args.kwargs
    prompt = kwargs["messages"][1]["content"]

    assert "Engineering Branch: Mechanical" in prompt
    assert "Target Role: Structural Design Engineer" in prompt
    assert "Experience Level: Experienced" in prompt
    assert "Difficulty: Advanced" in prompt


# ==============================================================================
# 8. LIVE INTEGRATION TEST (Runs only when credentials configured)
# ==============================================================================

def test_live_groq_integration():
    """
    Optional live integration test that runs only when GROQ_API_KEY and GROQ_MODEL
    are actively configured in .env.
    """
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    model = os.getenv("GROQ_MODEL", "").strip()

    if not api_key or api_key.startswith("your_") or not model:
        pytest.skip("Groq credentials or GROQ_MODEL not configured. Skipping live integration test.")

    # 1. Test live question generation
    question_res = generate_interview_question(
        category="Technical",
        difficulty="Easy",
        job_role="Software Engineer"
    )

    assert "question" in question_res
    assert isinstance(question_res["question"], str)
    assert len(question_res["question"]) > 10
    assert question_res["category"] == "Technical"
    assert question_res["difficulty"] == "Easy"
    assert isinstance(question_res.get("expected_aspects", []), list)

    # 2. Test live answer evaluation
    eval_res = evaluate_interview_answer(
        question_text=question_res["question"],
        user_answer="It enables modularity and reusability across software components by abstracting core logic.",
        category="Technical",
        difficulty="Easy",
        job_role="Software Engineer"
    )

    assert isinstance(eval_res["score"], int)
    assert 0 <= eval_res["score"] <= 100
    assert isinstance(eval_res["feedback"], str)
    assert len(eval_res["feedback"]) > 5
    assert isinstance(eval_res["strengths"], list)
    assert isinstance(eval_res["weaknesses"], list)
    assert isinstance(eval_res["suggestions"], list)
