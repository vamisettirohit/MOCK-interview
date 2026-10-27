"""
Service wrapper bridging app.services.groq_service to src.groq_service.
"""
from src.groq_service import (
    generate_interview_question,
    evaluate_interview_answer,
    generate_question,
    evaluate_answer,
    get_groq_client,
    get_groq_config,
    safe_parse_json,
    validate_evaluation_payload,
    normalize_category,
    normalize_difficulty,
    SUPPORTED_CATEGORIES,
    SUPPORTED_DIFFICULTIES,
    GroqServiceError,
    GroqConfigurationError,
    GroqAPIError,
    GroqValidationError,
)

__all__ = [
    "generate_interview_question",
    "evaluate_interview_answer",
    "generate_question",
    "evaluate_answer",
    "get_groq_client",
    "get_groq_config",
    "safe_parse_json",
    "validate_evaluation_payload",
    "normalize_category",
    "normalize_difficulty",
    "SUPPORTED_CATEGORIES",
    "SUPPORTED_DIFFICULTIES",
    "GroqServiceError",
    "GroqConfigurationError",
    "GroqAPIError",
    "GroqValidationError",
]
