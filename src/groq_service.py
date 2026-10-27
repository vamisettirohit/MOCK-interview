"""
Groq AI Service Module.
Handles dynamic interview question generation and structured answer evaluation
using the official Groq Python SDK.
"""
import os
import re
import json
import logging
from typing import Optional, List, Dict, Any, Tuple
from dotenv import load_dotenv

from groq import (
    Groq,
    APIError,
    APITimeoutError,
    RateLimitError,
    AuthenticationError,
    NotFoundError,
    APIConnectionError,
)

logger = logging.getLogger(__name__)

# Canonical supported categories and difficulty levels
SUPPORTED_CATEGORIES = ("Technical", "HR", "Aptitude", "Communication", "Mixed")
SUPPORTED_DIFFICULTIES = ("Easy", "Medium", "Hard", "Beginner", "Intermediate", "Advanced")


# ==============================================================================
# CUSTOM EXCEPTIONS (Prevents credential and raw traceback leakage)
# ==============================================================================

class GroqServiceError(Exception):
    """Base exception for all Groq service errors."""
    pass


class GroqConfigurationError(GroqServiceError):
    """Raised when environment variables (GROQ_API_KEY, GROQ_MODEL) are missing or invalid."""
    pass


class GroqAPIError(GroqServiceError):
    """Raised when Groq API encounters network, timeout, rate-limiting or model errors."""
    pass


class GroqValidationError(GroqServiceError):
    """Raised when Groq model output is malformed or fails schema validation."""
    pass


# ==============================================================================
# INPUT NORMALIZATION & VALIDATION
# ==============================================================================

def normalize_category(category: str) -> str:
    """
    Validates and normalizes category to one of Technical, HR, Aptitude, Communication, Mixed.
    Supports flexible case-insensitive matching.
    """
    if not category or not isinstance(category, str):
        raise ValueError("Category must be a non-empty string.")

    cleaned = category.strip().lower()
    for valid in SUPPORTED_CATEGORIES:
        if cleaned == valid.lower() or valid.lower() in cleaned:
            return valid

    raise ValueError(
        f"Unsupported category '{category}'. Must be one of: {', '.join(SUPPORTED_CATEGORIES)}"
    )


def normalize_difficulty(difficulty: str) -> str:
    """
    Validates and normalizes difficulty level.
    Supports Beginner, Intermediate, Advanced, Easy, Medium, Hard.
    """
    if not difficulty or not isinstance(difficulty, str):
        raise ValueError("Difficulty must be a non-empty string.")

    cleaned = difficulty.strip().lower()
    for valid in SUPPORTED_DIFFICULTIES:
        if cleaned == valid.lower():
            return valid

    raise ValueError(
        f"Unsupported difficulty '{difficulty}'. Must be one of: {', '.join(SUPPORTED_DIFFICULTIES)}"
    )


def get_groq_config() -> Tuple[str, str]:
    """
    Loads GROQ_API_KEY and GROQ_MODEL from environment variables.
    Does NOT assume or hardcode a model that might no longer be available.
    """
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    model = os.getenv("GROQ_MODEL", "").strip()

    if not api_key:
        raise GroqConfigurationError(
            "GROQ_API_KEY environment variable is missing or empty. "
            "Please configure your API key in .env."
        )
    if not model:
        raise GroqConfigurationError(
            "GROQ_MODEL environment variable is missing or empty. "
            "Do not rely on hardcoded models; please configure GROQ_MODEL in your environment."
        )
    return api_key, model


def get_groq_client(api_key: Optional[str] = None) -> Groq:
    """Instantiates and returns the official Groq client."""
    key = api_key or get_groq_config()[0]
    return Groq(api_key=key, timeout=30.0, max_retries=2)


# ==============================================================================
# SAFE JSON PARSER (Never treats model text as executable code)
# ==============================================================================

def safe_parse_json(content: str) -> Dict[str, Any]:
    """
    Parses model-generated JSON text securely using json.loads.
    Strips markdown code blocks if present.
    NEVER uses eval(), exec(), or any dynamic execution.
    """
    if not content or not isinstance(content, str):
        raise GroqValidationError("Empty or non-string response received from AI model.")

    clean_content = content.strip()

    # Strip markdown code fences if model returned ```json ... ```
    if clean_content.startswith("```"):
        clean_content = re.sub(r"^```(?:json)?\s*", "", clean_content)
        clean_content = re.sub(r"\s*```$", "", clean_content)
        clean_content = clean_content.strip()

    try:
        data = json.loads(clean_content)
        if not isinstance(data, dict):
            raise GroqValidationError("Parsed JSON is not a key-value dictionary object.")
        return data
    except json.JSONDecodeError as err:
        logger.error(f"Malformed JSON received from AI model: {err}")
        raise GroqValidationError("AI model produced malformed JSON that could not be parsed.")


# ==============================================================================
# QUESTION GENERATION
# ==============================================================================

def build_question_prompt(
    category: str,
    difficulty: str,
    job_role: Optional[str] = None,
    previous_questions: Optional[List[str]] = None,
    branch: Optional[str] = None,
    experience_level: Optional[str] = None,
    topic: Optional[str] = None,
    previous_answers: Optional[List[Dict[str, Any]]] = None
) -> str:
    """
    Constructs an explicit interview prompt that elicits a tailored question
    WITHOUT giving away the answer or hints in the question itself.
    Incorporates engineering branch, experience level, and candidate's previous
    responses to support natural, contextual follow-up questions.
    """
    role_ctx = f"Target Job Role: '{job_role.strip()}'" if job_role and job_role.strip() else "Target Job Role: General Candidate"
    branch_ctx = f"Engineering Branch: '{branch.strip()}'" if branch and branch.strip() else ""
    exp_ctx = f"Candidate Experience Level: '{experience_level.strip()}'" if experience_level and experience_level.strip() else ""
    topic_ctx = f"Specific Focus Topic: '{topic.strip()}'" if topic and topic.strip() else ""

    profile_lines = [line for line in [role_ctx, branch_ctx, exp_ctx, topic_ctx] if line]
    profile_block = "\n".join(profile_lines)

    prev_ctx = ""
    if previous_questions:
        prev_list = json.dumps(previous_questions[:10])
        prev_ctx = f"\nPrevious questions asked in this interview (DO NOT repeat these or closely similar questions):\n{prev_list}\n"

    # Follow-up context from previous candidate answers
    followup_ctx = ""
    if previous_answers and isinstance(previous_answers, list):
        qa_entries = []
        for i, item in enumerate(previous_answers[-3:], 1):
            q_str = str(item.get("question", "")).strip()
            a_str = str(item.get("user_answer", "") or item.get("answer", "")).strip()[:250]
            if q_str:
                qa_entries.append(f"- Question {i}: {q_str}\n  Candidate Answer: {a_str if a_str else '[No response provided]'}")
        if qa_entries:
            followup_ctx = (
                "\nPREVIOUS CANDIDATE RESPONSES IN THIS SESSION:\n" +
                "\n".join(qa_entries) +
                "\n\nFOLLOW-UP GUIDANCE:\n"
                "If the candidate's recent answers indicated a noteworthy concept, omission, or interesting viewpoint, "
                "you may formulate a natural, contextual follow-up question to probe deeper into practical application, trade-offs, or system constraints, "
                "OR advance smoothly to the next core dimension in their track. Do NOT repeat previous questions.\n"
            )

    category_instructions = {
        "Technical": (
            "Ask a conceptual, problem-solving, or architectural technical question appropriate for the specified level. "
            "Tailor the question to the candidate's engineering branch and target job role. "
            "Do NOT include the answer, code solutions, hints, or spoilers in the question."
        ),
        "HR": (
            "Ask a behavioral interview question utilizing the STAR framework (Situation, Task, Action, Result). "
            "Focus on teamwork, handling conflict, leadership, adaptability, or work ethic appropriate for the candidate's experience level. "
            "Do NOT suggest the ideal answer in the question."
        ),
        "Aptitude": (
            "Ask an analytical, logical reasoning, or problem-solving estimation question suitable for an interview discussion. "
            "Present only the scenario and the problem statement. Do NOT reveal calculation steps or the final answer."
        ),
        "Communication": (
            "Ask a situational communication question (e.g. explaining complex technical concepts to non-technical stakeholders, "
            "resolving a disagreement with a peer, or handling an escalated customer). "
            "Do NOT provide sample phrasing or answers."
        ),
        "Mixed": (
            "Ask a well-rounded interview question combining technical domain reasoning, analytical problem-solving, or engineering judgment "
            "tailored to the candidate's engineering branch, experience level, and target role. "
            "Do NOT include the answer or spoilers in the question."
        )
    }

    instruction = category_instructions.get(category, category_instructions["Technical"])

    prompt = f"""You are an expert interviewer conducting an interview.
Category: {category}
Difficulty: {difficulty}
{profile_block}
{prev_ctx}
{followup_ctx}
INSTRUCTION:
{instruction}
Generate exactly ONE interview question.

You must respond with ONLY valid JSON adhering strictly to this schema:
{{
  "question": "string - The interview question text (must NOT contain or reveal the answer)",
  "category": "{category}",
  "difficulty": "{difficulty}",
  "topic": "string - The concise topic or skill assessed",
  "expected_aspects": ["string - 2 to 3 core dimensions a strong candidate response should address"]
}}"""
    return prompt


def generate_interview_question(
    category: str,
    difficulty: str,
    job_role: Optional[str] = None,
    previous_questions: Optional[List[str]] = None,
    client: Optional[Groq] = None,
    model: Optional[str] = None,
    branch: Optional[str] = None,
    experience_level: Optional[str] = None,
    topic: Optional[str] = None,
    previous_answers: Optional[List[Dict[str, Any]]] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Generates one interview question at a time using Groq AI.
    
    Args:
        category: "Technical", "HR", "Aptitude", "Communication", or "Mixed"
        difficulty: "Beginner", "Intermediate", "Advanced", "Easy", "Medium", or "Hard"
        job_role: Optional job role / focus area
        previous_questions: Optional list of previous questions to avoid repetition
        client: Optional pre-configured Groq client (useful for tests)
        model: Optional model override (defaults to GROQ_MODEL env var)
        branch: Optional engineering branch (e.g. CSE, IT, ECE, EEE, Mechanical, Civil)
        experience_level: Optional experience level (e.g. Fresher, Internship, Experienced)
        topic: Optional specific focus topic
        previous_answers: Optional list of previous answered Q&A to support contextual follow-ups
        
    Returns:
        Structured question dictionary
    """
    norm_cat = normalize_category(category)
    norm_diff = normalize_difficulty(difficulty)

    api_key, env_model = get_groq_config()
    active_model = model or env_model
    active_client = client or get_groq_client(api_key=api_key)

    prompt = build_question_prompt(
        category=norm_cat,
        difficulty=norm_diff,
        job_role=job_role,
        previous_questions=previous_questions,
        branch=branch,
        experience_level=experience_level,
        topic=topic,
        previous_answers=previous_answers
    )

    try:
        chat_completion = active_client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a professional hiring manager and interview coach. You output ONLY valid JSON without markdown wrapping or commentary."
                },
                {"role": "user", "content": prompt}
            ],
            model=active_model,
            response_format={"type": "json_object"},
            temperature=0.7,
            max_tokens=600
        )

        content = chat_completion.choices[0].message.content
        data = safe_parse_json(content)

        # Validate question response structure
        question_text = str(data.get("question", "")).strip()
        if not question_text:
            raise GroqValidationError("Model response is missing the required 'question' text.")

        topic_val = str(data.get("topic") or topic or job_role or norm_cat).strip()
        expected = data.get("expected_aspects")
        if not isinstance(expected, list) or not expected:
            expected = ["Conceptual understanding", "Depth of explanation", "Practical relevance"]

        return {
            "question": question_text,
            "category": norm_cat,
            "difficulty": norm_diff,
            "topic": topic_val,
            "expected_aspects": [str(x).strip() for x in expected if str(x).strip()]
        }

    except APITimeoutError:
        logger.error("Groq API timed out during question generation.")
        raise GroqAPIError("AI question generation timed out. Please try again.")
    except RateLimitError:
        logger.error("Groq API rate limit reached during question generation.")
        raise GroqAPIError("AI service rate limit reached. Please wait a moment before trying again.")
    except NotFoundError:
        logger.error(f"Configured Groq model '{active_model}' not found.")
        raise GroqAPIError(f"Configured model '{active_model}' is unavailable or invalid.")
    except AuthenticationError:
        logger.error("Groq API authentication failed.")
        raise GroqAPIError("AI service authentication failed. Please verify GROQ_API_KEY.")
    except APIConnectionError:
        logger.error("Network error connecting to Groq API.")
        raise GroqAPIError("Could not connect to Groq AI service. Please check network connectivity.")
    except APIError as e:
        logger.error(f"Groq API error: {type(e).__name__}")
        raise GroqAPIError("AI service returned an API error. Please try again.")
    except GroqServiceError:
        raise
    except Exception as e:
        logger.error(f"Unexpected question generation error: {type(e).__name__}")
        raise GroqAPIError("An unexpected error occurred while generating interview question.")


# Alias for compatibility
generate_question = generate_interview_question


# ==============================================================================
# ANSWER EVALUATION & CORRECTION
# ==============================================================================

def validate_evaluation_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validates evaluation schema and score range [0, 100].
    Enforces score, classification, mistakes, explanation, and improved answer.
    Never trusts unvalidated model scores.
    """
    if "score" not in data:
        raise GroqValidationError("Model evaluation response is missing required 'score' field.")

    raw_score = data["score"]
    try:
        score_val = int(round(float(raw_score)))
    except (ValueError, TypeError):
        raise GroqValidationError(f"Invalid score format '{raw_score}'; must be numeric between 0 and 100.")

    if not (0 <= score_val <= 100):
        raise GroqValidationError(f"Score {score_val} is out of valid range [0, 100].")

    # 1. Classification: "correct", "partially_correct", or "incorrect"
    raw_class = str(data.get("classification", "")).strip().lower()
    if raw_class in ("correct", "partially_correct", "incorrect"):
        classification = raw_class
    elif "partial" in raw_class:
        classification = "partially_correct"
    elif "incorrect" in raw_class or "wrong" in raw_class:
        classification = "incorrect"
    elif "correct" in raw_class:
        classification = "correct"
    else:
        # Deduce logically from validated numerical score
        if score_val >= 75:
            classification = "correct"
        elif score_val >= 50:
            classification = "partially_correct"
        else:
            classification = "incorrect"

    def ensure_string_list(val: Any, default_items: Optional[List[str]] = None) -> List[str]:
        if isinstance(val, list):
            items = [str(x).strip() for x in val if str(x).strip()]
            if items:
                return items
        elif isinstance(val, str) and val.strip():
            return [val.strip()]
        return default_items or []

    # 2. Lists: correct_concepts, mistakes, missing_concepts, suggestions
    correct_concepts = ensure_string_list(
        data.get("correct_concepts") or data.get("strengths"),
        ["Addressed core concepts of the prompt."] if score_val > 0 else []
    )

    mistakes = ensure_string_list(
        data.get("mistakes"),
        [] if score_val >= 90 else ["Could expand with deeper technical rigor."]
    )

    missing_concepts = ensure_string_list(
        data.get("missing_concepts"),
        [] if score_val >= 90 else ["Practical edge cases and system trade-offs."]
    )

    suggestions = ensure_string_list(
        data.get("suggestions"),
        ["Structure responses using clear technical reasoning and concrete examples."]
    )

    # 3. Text fields: explanation, improved_answer, communication_feedback, follow_up_question
    explanation = str(data.get("explanation") or data.get("feedback") or "").strip()
    if not explanation:
        if classification == "correct":
            explanation = "The response is accurate and demonstrates solid conceptual understanding."
        elif classification == "partially_correct":
            explanation = "The response captures partial concepts but misses key depth, constraints, or trade-offs."
        else:
            explanation = "The response is largely inaccurate or omits the essential technical principles."

    improved_answer = str(data.get("improved_answer") or "").strip()
    if not improved_answer:
        improved_answer = (
            "An exemplary response should define the core principles clearly, "
            "provide concrete practical examples or code structure, and discuss trade-offs and edge cases."
        )

    communication_feedback = str(
        data.get("communication_feedback") or "Communication was coherent and straightforward."
    ).strip()

    follow_up_question = data.get("follow_up_question")
    if follow_up_question and isinstance(follow_up_question, str):
        follow_up_question = follow_up_question.strip()
    else:
        follow_up_question = None

    # Backward-compatible fields
    feedback_text = str(data.get("feedback") or explanation).strip()
    strengths = ensure_string_list(data.get("strengths") or correct_concepts, ["Solid conceptual foundation."])
    weaknesses = ensure_string_list(data.get("weaknesses") or (mistakes + missing_concepts), ["Could expand further on trade-offs."])

    return {
        "score": score_val,
        "classification": classification,
        "correct_concepts": correct_concepts,
        "mistakes": mistakes,
        "missing_concepts": missing_concepts,
        "explanation": explanation,
        "improved_answer": improved_answer,
        "suggestions": suggestions,
        "communication_feedback": communication_feedback,
        "follow_up_question": follow_up_question,
        # Legacy backward-compatible keys
        "feedback": feedback_text,
        "strengths": strengths,
        "weaknesses": weaknesses
    }


def evaluate_interview_answer(
    question_text: str,
    user_answer: str,
    category: str,
    difficulty: str,
    job_role: Optional[str] = None,
    client: Optional[Groq] = None,
    model: Optional[str] = None,
    branch: Optional[str] = None,
    experience_level: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Evaluates a candidate's answer for relevance, correctness, clarity, and completeness.
    Returns structured JSON with:
      - score: Numerical score (0-100)
      - classification: "correct", "partially_correct", or "incorrect"
      - correct_concepts: List of accurate concepts identified
      - mistakes: Specific mistakes identified
      - missing_concepts: Essential points that were omitted
      - explanation: In-depth educational explanation of mistakes and missing points
      - improved_answer: Polished sample answer (Model Answer)
      - suggestions: Actionable recommendations for improvement
      - communication_feedback: Structural and clarity evaluation
      - follow_up_question: Optional logical follow-up question
    
    CRITICAL: Does NOT invent scores when the API call fails; raises GroqAPIError instead.
    """
    if not question_text or not question_text.strip():
        raise ValueError("Interview question text cannot be empty.")

    cleaned_answer = (user_answer or "").strip()
    norm_cat = normalize_category(category)
    norm_diff = normalize_difficulty(difficulty)

    # Empty answer check: If candidate submits blank answer, return 0 score without invoking API
    if not cleaned_answer:
        return {
            "score": 0,
            "classification": "incorrect",
            "correct_concepts": [],
            "mistakes": ["No answer provided."],
            "missing_concepts": ["All core concepts relevant to the question."],
            "explanation": "No response was provided by the candidate.",
            "improved_answer": "An effective answer should directly define the core principles, provide concrete technical or practical examples, and explain trade-offs.",
            "suggestions": ["Formulate a structured response addressing the core points of the question."],
            "communication_feedback": "N/A - Blank response.",
            "follow_up_question": None,
            "feedback": "No answer was provided. A comprehensive response addressing the question is required.",
            "strengths": ["None - answer was blank."],
            "weaknesses": ["No answer submitted."]
        }

    api_key, env_model = get_groq_config()
    active_model = model or env_model
    active_client = client or get_groq_client(api_key=api_key)

    role_ctx = f"Target Role: {job_role.strip()}" if job_role and job_role.strip() else ""
    branch_ctx = f"Engineering Branch: {branch.strip()}" if branch and branch.strip() else ""
    exp_ctx = f"Experience Level: {experience_level.strip()}" if experience_level and experience_level.strip() else ""

    profile_items = [p for p in [role_ctx, branch_ctx, exp_ctx] if p]
    profile_block = "\n".join(profile_items)

    category_rubrics = {
        "Technical": (
            "Focus primarily on factual and conceptual accuracy, depth of engineering reasoning, "
            "algorithmic or architectural soundness, and awareness of edge cases and practical trade-offs."
        ),
        "HR": (
            "Evaluate behavioral relevance, communication structure (e.g. STAR framework: Situation, Task, Action, Result), "
            "clarity, collaboration, and situational judgment. Do NOT assume there is only one rigid answer; assess self-awareness, leadership, and emotional intelligence."
        ),
        "Aptitude": (
            "Evaluate analytical reasoning, logical progression, problem-solving methodology, and quantitative validity. "
            "Prioritize step-by-step reasoning over mere rote guesses."
        ),
        "Communication": (
            "Evaluate clarity, structured explanation, audience adaptation, and conciseness."
        ),
        "Mixed": (
            "Evaluate domain technical accuracy, practical problem-solving, and clear professional articulation."
        )
    }
    rubric_focus = category_rubrics.get(norm_cat, category_rubrics["Technical"])

    eval_prompt = f"""You are an expert interviewer evaluating a student candidate's answer.
Category: {norm_cat}
Difficulty: {norm_diff}
{profile_block}

RUBRIC FOCUS:
{rubric_focus}

INTERVIEW QUESTION:
\"{question_text.strip()}\"

CANDIDATE'S SUBMITTED ANSWER:
\"{cleaned_answer}\"

EVALUATION CRITERIA:
1. Relevance: Did the candidate answer what was asked directly?
2. Correctness: Are the factual, conceptual, or technical claims accurate?
3. Clarity: Is the communication coherent, articulate, and well-structured?
4. Completeness: Did the answer provide adequate depth and consider edge cases or trade-offs?

Scoring Scale:
- 90-100: Exceptional, comprehensive, and thoroughly articulated. (Classification: "correct")
- 75-89: Solid, accurate, and mostly complete with minor omissions. (Classification: "correct")
- 50-74: Partially correct or superficial; lacks depth or clarity. (Classification: "partially_correct")
- 1-49: Largely incorrect, irrelevant, or severely incomplete. (Classification: "incorrect")
- 0: Empty or completely off-topic. (Classification: "incorrect")

Respond ONLY with valid JSON conforming strictly to this schema:
{{
  "score": integer (0 to 100 overall score),
  "classification": "correct" | "partially_correct" | "incorrect",
  "correct_concepts": ["string - 2 to 3 specific accurate concepts or strengths demonstrated in the response"],
  "mistakes": ["string - 1 to 3 specific mistakes, inaccuracies, or misconceptions in the answer"],
  "missing_concepts": ["string - 1 to 3 key principles, edge cases, or details that were omitted"],
  "explanation": "string - educational breakdown explaining why the mistakes are wrong and what was missing",
  "improved_answer": "string - an ideal model answer demonstrating how an excellent candidate would answer clearly and concisely",
  "suggestions": ["string - 2 to 3 actionable suggestions for improvement"],
  "communication_feedback": "string - feedback on clarity, structure, and answer organization",
  "follow_up_question": "string - an optional relevant follow-up question to probe deeper (or null)"
}}"""

    try:
        chat_completion = active_client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are an objective, encouraging, and rigorous interview evaluator. Output ONLY valid JSON without markdown wrapping or preamble."
                },
                {"role": "user", "content": eval_prompt}
            ],
            model=active_model,
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=1000
        )

        content = chat_completion.choices[0].message.content
        raw_data = safe_parse_json(content)
        validated_result = validate_evaluation_payload(raw_data)
        return validated_result

    except APITimeoutError:
        logger.error("Groq API timed out during answer evaluation.")
        raise GroqAPIError("AI answer evaluation timed out. Please try again.")
    except RateLimitError:
        logger.error("Groq API rate limit reached during answer evaluation.")
        raise GroqAPIError("AI service rate limit reached. Please wait a moment before trying again.")
    except NotFoundError:
        logger.error(f"Configured Groq model '{active_model}' not found.")
        raise GroqAPIError(f"Configured model '{active_model}' is unavailable or invalid.")
    except AuthenticationError:
        logger.error("Groq API authentication failed during answer evaluation.")
        raise GroqAPIError("AI service authentication failed. Please verify GROQ_API_KEY.")
    except APIConnectionError:
        logger.error("Network error connecting to Groq API.")
        raise GroqAPIError("Could not connect to Groq AI service. Please check network connectivity.")
    except APIError as e:
        logger.error(f"Groq API error: {type(e).__name__}")
        raise GroqAPIError("AI service returned an API error. Please try again.")
    except GroqServiceError:
        raise
    except Exception as e:
        logger.error(f"Unexpected evaluation error: {type(e).__name__}")
        raise GroqAPIError("An unexpected error occurred while evaluating the candidate's answer.")


# Alias for compatibility
evaluate_answer = evaluate_interview_answer

