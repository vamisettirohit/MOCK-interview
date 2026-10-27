import re

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")

VALID_BRANCHES = [
    "CSE",
    "IT",
    "ECE",
    "EEE",
    "Mechanical",
    "Civil",
    "Other"
]

VALID_EXPERIENCE_LEVELS = [
    "Fresher",
    "Internship",
    "Experienced"
]

VALID_ROLES = [
    "Software Developer",
    "Web Developer",
    "Python Developer",
    "Java Developer",
    "Data Analyst",
    "AI/ML Engineer",
    "Custom Role"
]

VALID_CATEGORIES = [
    "Technical",
    "HR",
    "Aptitude",
    "Mixed",
    "Communication",
    "Full Stack Web Development",
    "Frontend Development",
    "Backend & APIs",
    "Data Science & Machine Learning",
    "DevOps & Cloud Computing",
    "System Design & Architecture",
    "HR & Behavioral"
]

VALID_DIFFICULTIES = [
    "Beginner",
    "Intermediate",
    "Advanced",
    "Easy",
    "Medium",
    "Hard"
]

VALID_DURATIONS = [10, 15, 20, 30, 45, 60]

def normalize_email(email: str) -> str:
    """Strips whitespace and converts email to lowercase."""
    return email.strip().lower() if email else ""

def validate_registration(name: str, email: str, password: str, confirm_password: str = None):
    """
    Validates registration input.
    Returns:
        (is_valid: bool, error_message: str or None)
    """
    if not name or len(name.strip()) < 2:
        return False, "Full name must be at least 2 characters long."
    
    if len(name.strip()) > 100:
        return False, "Full name cannot exceed 100 characters."
    
    norm_email = normalize_email(email)
    if not norm_email or not EMAIL_REGEX.match(norm_email):
        return False, "Please enter a valid email address."
    
    if len(norm_email) > 255:
        return False, "Email address is too long."
    
    if not password or len(password) < 6:
        return False, "Password must be at least 6 characters long."
    
    if len(password) > 128:
        return False, "Password cannot exceed 128 characters."
    
    if confirm_password is not None and password != confirm_password:
        return False, "Passwords do not match."
    
    return True, None

def validate_interview_setup(
    category: str,
    difficulty: str,
    num_questions: str,
    branch: str = None,
    experience_level: str = None,
    duration: str = None
):
    """
    Validates interview setup parameters.
    Maintains backward compatibility with 3-arg positional calls while
    validating branch, experience level, and duration when provided.
    Returns:
        (is_valid: bool, error_message: str or None)
    """
    if not category or not isinstance(category, str):
        return False, "Category must be specified."

    cat_cleaned = category.strip()
    valid_cat_match = any(
        cat_cleaned.lower() == c.lower() or c.lower() in cat_cleaned.lower()
        for c in VALID_CATEGORIES
    )
    if not valid_cat_match:
        return False, f"Invalid category selected. Choose from: Technical, HR, Aptitude, Mixed."

    if not difficulty or not isinstance(difficulty, str):
        return False, "Difficulty must be specified."

    diff_cleaned = difficulty.strip().capitalize()
    if diff_cleaned not in [d.capitalize() for d in VALID_DIFFICULTIES]:
        return False, "Difficulty must be Beginner, Intermediate, or Advanced (or Easy, Medium, Hard)."

    try:
        count = int(num_questions)
        if count < 1 or count > 10:
            return False, "Number of questions must be between 1 and 10."
    except (ValueError, TypeError):
        return False, "Invalid question count. Must be a number between 1 and 10."

    if branch is not None and isinstance(branch, str):
        b_clean = branch.strip()
        if not b_clean:
            return False, "Engineering branch cannot be empty."
        if len(b_clean) > 100:
            return False, "Engineering branch name cannot exceed 100 characters."

    if experience_level is not None and isinstance(experience_level, str):
        exp_clean = experience_level.strip().capitalize()
        valid_exp = [e.capitalize() for e in VALID_EXPERIENCE_LEVELS]
        if exp_clean not in valid_exp:
            return False, f"Experience level must be one of: {', '.join(VALID_EXPERIENCE_LEVELS)}."

    if duration is not None:
        try:
            dur = int(duration)
            if dur < 5 or dur > 180:
                return False, "Interview duration must be between 5 and 180 minutes."
        except (ValueError, TypeError):
            return False, "Invalid duration value."

    return True, None

