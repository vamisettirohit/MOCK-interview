"""
Mock Interview AI — Interview Domain Service
Handles score aggregation, performance summary calculation, recommended practice topics,
and report formatting. Reusable across REST API and HTML routes.
"""
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone


def calculate_overall_score(questions: List[Dict[str, Any]]) -> float:
    """
    Calculates the exact arithmetic average score from valid numeric evaluations of answered questions.
    Returns 0.0 if no answered questions or valid scores exist.
    Never fabricates scores or demo numbers.
    """
    if not questions or not isinstance(questions, list):
        return 0.0

    valid_scores = []
    for q in questions:
        if not isinstance(q, dict):
            continue
        # Only count if marked answered or has a valid numeric score
        score = q.get("score")
        if score is None and q.get("evaluation") and isinstance(q["evaluation"], dict):
            score = q["evaluation"].get("score")

        if isinstance(score, (int, float)) and not isinstance(score, bool):
            # Clamp between 0 and 100 for safety
            valid_scores.append(max(0.0, min(100.0, float(score))))

    if not valid_scores:
        return 0.0

    return round(sum(valid_scores) / len(valid_scores), 1)


def calculate_performance_summary(
    answered_questions: List[Dict[str, Any]],
    category: str = "Technical",
    job_role: str = ""
) -> Dict[str, Any]:
    """
    Aggregates strengths, weaknesses, mistakes, missing concepts, actionable suggestions,
    and recommended topics for further practice across all answered questions.
    """
    if not answered_questions or not isinstance(answered_questions, list):
        return {
            "strengths": ["No answers recorded."],
            "weaknesses": ["Interview was completed without answering questions."],
            "suggestions": ["Participate in active practice sessions to receive feedback."],
            "correct_concepts": [],
            "mistakes": [],
            "missing_concepts": [],
            "recommended_topics": [
                f"{category} Fundamentals" if category else "Core Technical Fundamentals",
                "System Architecture & Trade-offs",
                "Communication & Structured Problem Solving"
            ]
        }

    all_strengths = []
    all_weaknesses = []
    all_suggestions = []
    all_correct_concepts = []
    all_mistakes = []
    all_missing_concepts = []
    topic_candidates = []

    for q in answered_questions:
        if not isinstance(q, dict):
            continue

        eval_data = q.get("evaluation") or {}
        if not isinstance(eval_data, dict):
            eval_data = {}

        # Strengths & correct concepts
        all_strengths.extend(eval_data.get("strengths") or [])
        all_correct_concepts.extend(eval_data.get("correct_concepts") or [])

        # Weaknesses, mistakes & missing concepts
        all_weaknesses.extend(eval_data.get("weaknesses") or [])
        all_mistakes.extend(eval_data.get("mistakes") or [])
        all_missing_concepts.extend(eval_data.get("missing_concepts") or [])

        # Suggestions
        all_suggestions.extend(eval_data.get("suggestions") or [])

        # Topic extraction for practice recommendations
        q_topic = q.get("topic")
        q_score = q.get("score")
        q_class = q.get("classification") or eval_data.get("classification")

        if q_topic:
            # If candidate scored < 75 or had mistakes, prioritize this topic
            if (q_score is not None and q_score < 75) or q_class in ["partially_correct", "incorrect"]:
                topic_candidates.insert(0, str(q_topic).strip())
            else:
                topic_candidates.append(str(q_topic).strip())

    # Add missing concepts as topic candidates
    for mc in all_missing_concepts:
        cleaned_mc = str(mc).strip()
        if cleaned_mc:
            topic_candidates.append(cleaned_mc)

    # Deduplicate while preserving order
    def unique_items(items: list, limit: int = 5) -> list:
        seen = set()
        res = []
        for x in items:
            clean = str(x).strip()
            if clean and clean.lower() not in seen:
                seen.add(clean.lower())
                res.append(clean)
            if len(res) >= limit:
                break
        return res

    deduped_topics = unique_items(topic_candidates, limit=5)

    # If candidate answered everything perfectly, supply high-leverage advanced topics
    if not deduped_topics:
        default_topics_map = {
            "Technical": ["Distributed Systems Resilience", "High-Throughput Concurrency", "Database Query Plan Optimization", "System Security & Auth"],
            "HR": ["Executive Stakeholder Alignment", "Cross-Functional Conflict Mediation", "Strategic Prioritization"],
            "Aptitude": ["Advanced Probability & Combinatorics", "Optimization Algorithms", "Data Interpretation"],
            "Communication": ["Technical Presentation to Leadership", "Architectural Decision Records", "Active Clarification Strategies"],
            "Mixed": ["System Architecture Design", "Technical Leadership Trade-offs", "Root Cause Analysis"]
        }
        category_key = category if category in default_topics_map else "Technical"
        deduped_topics = default_topics_map[category_key][:4]

    return {
        "strengths": unique_items(all_strengths or all_correct_concepts, limit=5),
        "weaknesses": unique_items(all_weaknesses or (all_mistakes + all_missing_concepts), limit=5),
        "suggestions": unique_items(all_suggestions, limit=5),
        "correct_concepts": unique_items(all_correct_concepts, limit=5),
        "mistakes": unique_items(all_mistakes, limit=5),
        "missing_concepts": unique_items(all_missing_concepts, limit=5),
        "recommended_topics": deduped_topics
    }


def get_score_rating(score: float) -> tuple[str, str]:
    """
    Returns human-friendly rating label and CSS badge class for a score.
    """
    if score >= 80.0:
        return "Outstanding", "badge-easy"
    elif score >= 60.0:
        return "Proficient", "badge-medium"
    else:
        return "Needs Practice", "badge-hard"


def build_performance_report(interview: Dict[str, Any]) -> Dict[str, Any]:
    """
    Builds a complete, normalized performance report payload for an interview.
    Consistently computes overall score, answer breakdown, and aggregated summary.
    """
    questions = interview.get("questions", [])
    answered_qs = [q for q in questions if q.get("answered")]
    overall_score = calculate_overall_score(answered_qs)

    category = interview.get("category", "Technical")
    job_role = interview.get("job_role", "Software Engineer")
    summary = calculate_performance_summary(answered_qs, category=category, job_role=job_role)

    completed_at = interview.get("completed_at")
    if isinstance(completed_at, datetime):
        completed_at_iso = completed_at.isoformat()
    elif completed_at:
        completed_at_iso = str(completed_at)
    else:
        completed_at_iso = datetime.now(timezone.utc).isoformat()

    return {
        "interview_id": str(interview.get("_id", "")),
        "category": category,
        "difficulty": interview.get("difficulty", "Medium"),
        "branch": interview.get("branch", "CSE"),
        "job_role": job_role,
        "experience_level": interview.get("experience_level", "Fresher"),
        "duration_minutes": interview.get("duration_minutes", 15),
        "total_questions": interview.get("total_questions", len(questions)),
        "completed_questions": len(answered_qs),
        "status": interview.get("status", "in_progress"),
        "overall_score": overall_score,
        "summary": summary,
        "completed_at": completed_at_iso,
        "questions": [
            {
                "question_number": q.get("question_number", idx + 1),
                "question": q.get("question") or q.get("question_text", ""),
                "category": q.get("category", category),
                "difficulty": q.get("difficulty", interview.get("difficulty")),
                "topic": q.get("topic", ""),
                "user_answer": q.get("user_answer", ""),
                "score": q.get("score"),
                "classification": q.get("classification") or (q.get("evaluation") or {}).get("classification"),
                "evaluation": q.get("evaluation") or {}
            }
            for idx, q in enumerate(answered_qs)
        ]
    }
