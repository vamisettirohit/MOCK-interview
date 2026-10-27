import pytest

def test_home_page(client):
    """Test the landing page returns 200 OK and contains brand elements."""
    response = client.get("/")
    assert response.status_code == 200
    assert b"Mock Interview AI" in response.data or b"Interview" in response.data

def test_about_page(client):
    """Test the about page returns 200 OK."""
    response = client.get("/about")
    assert response.status_code == 200

def test_login_page_renders(client):
    """Test the login page returns 200 OK."""
    response = client.get("/auth/login")
    assert response.status_code == 200
    assert b"login" in response.data.lower()

def test_register_page_renders(client):
    """Test the registration page returns 200 OK."""
    response = client.get("/auth/register")
    assert response.status_code == 200
    assert b"register" in response.data.lower() or b"create account" in response.data.lower()

def test_404_handler(client):
    """Test non-existent route returns 404."""
    response = client.get("/this-route-does-not-exist-12345")
    assert response.status_code == 404

def test_protected_dashboard_redirects_unauthenticated(client):
    """Test that accessing /dashboard/ unauthenticated redirects to login."""
    response = client.get("/dashboard/", follow_redirects=False)
    assert response.status_code in [301, 302, 308]
    assert "/auth/login" in response.headers.get("Location", "")

def test_protected_interview_setup_redirects_unauthenticated(client):
    """Test that accessing /interview/setup unauthenticated redirects to login."""
    response = client.get("/interview/setup", follow_redirects=False)
    assert response.status_code in [301, 302, 308]
    assert "/auth/login" in response.headers.get("Location", "")

def test_protected_history_redirects_unauthenticated(client):
    """Test that accessing /dashboard/history unauthenticated redirects to login."""
    response = client.get("/dashboard/history", follow_redirects=False)
    assert response.status_code in [301, 302, 308]
    assert "/auth/login" in response.headers.get("Location", "")

def test_authenticated_history_renders(client):
    """Test that authenticated student can load /dashboard/history."""
    from bson.objectid import ObjectId
    with client.session_transaction() as sess:
        sess["user"] = {
            "id": str(ObjectId()),
            "name": "Jane Doe",
            "email": "jane@example.com",
            "target_role": "Backend Engineer"
        }
    response = client.get("/dashboard/history")
    assert response.status_code == 200
    assert b"Interview History" in response.data


def test_session_view_renders_video_interview_elements(client):
    """
    Test that authenticated student accessing /interview/session/<id> receives
    the Phase 3 Face-to-Face video interview stage, avatar, and speech controls.
    """
    from bson.objectid import ObjectId
    from datetime import datetime, timezone
    import app.services.db as db_module

    db = db_module.get_db()
    user_id = ObjectId()
    interview_doc = {
        "user_id": user_id,
        "branch": "CSE",
        "job_role": "Software Developer",
        "experience_level": "Fresher",
        "category": "Technical",
        "difficulty": "Intermediate",
        "duration_minutes": 15,
        "topic": "System Design",
        "total_questions": 3,
        "completed_questions": 0,
        "overall_score": 0,
        "status": "in_progress",
        "questions": [
            {
                "question_number": 1,
                "question": "How do microservices communicate efficiently?",
                "category": "Technical",
                "difficulty": "Intermediate",
                "answered": False,
                "user_answer": "",
                "score": None,
                "evaluation": None
            }
        ],
        "created_at": datetime.now(timezone.utc),
        "completed_at": None
    }
    insert_res = db.interviews.insert_one(interview_doc)
    interview_id = str(insert_res.inserted_id)

    with client.session_transaction() as sess:
        sess["user"] = {
            "id": str(user_id),
            "name": "Test Candidate",
            "email": "candidate@example.com",
            "target_role": "Software Developer"
        }

    response = client.get(f"/interview/session/{interview_id}")
    assert response.status_code == 200

    html = response.data.decode("utf-8")

    # Verify Video Stage & AI Avatar Tile
    assert 'id="ai-video-tile"' in html
    assert 'class="avatar-visual"' in html
    assert 'id="soundwave-container"' in html
    assert 'id="tts-play-btn"' in html

    # Verify Candidate Camera Self-View Tile
    assert 'id="candidate-video-tile"' in html
    assert 'id="candidate-webcam"' in html
    assert 'id="toggle-camera-btn"' in html

    # Verify Prominent Microphone Controls
    assert 'id="mic-toggle-btn"' in html
    assert 'id="start-listening-btn"' in html
    assert 'id="stop-listening-btn"' in html
    assert 'id="cancel-recording-btn"' in html
    assert 'id="clear-transcript-btn"' in html

    # Verify Editable Transcript Area & Question Card
    assert 'id="answer-input"' in html
    assert 'id="question-text"' in html
    assert 'id="submit-answer-btn"' in html

    # Verify Phase 4 Controls: Replay Question, Stop Speaking, Live Audio Meter & Privacy Notice
    assert 'id="tts-replay-btn"' in html
    assert 'id="tts-stop-btn"' in html
    assert 'id="live-audio-meter"' in html
    assert 'class="privacy-note"' in html



