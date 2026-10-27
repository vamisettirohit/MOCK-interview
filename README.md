# Mock Interview AI ⚡

An AI-driven technical and behavioral interview preparation platform for college students and job seekers. Powered by **Python 3.12**, **Flask**, **MongoDB Atlas**, and **Groq Cloud API** (Llama 3).

---

## 🚀 Key Features
- **Dynamic Question Generation**: Realistic, non-repetitive interview questions tailored by track, difficulty, and optional topic focus using Groq's high-speed inference.
- **Automated Rubric Evaluation**: Instant grading on **Technical Accuracy (40%)**, **Depth & Completeness (30%)**, and **Communication Clarity (30%)** with numerical scoring (0-100).
- **Constructive Feedback & Sample Model Answers**: Actionable strengths, areas for improvement, and high-caliber model answers for every question.
- **Candidate Dashboard**: Analytics tracking total interviews, average score, performance by category, and complete interview history.
- **Secure Authentication**: Cryptographic password hashing (`werkzeug.security`) and server-side session management.
- **Modern Glassmorphic UI**: Fast, responsive Vanilla CSS design system with dark mode aesthetics.

---

## 🛠️ Technology Stack
- **Backend**: Python 3.12, Flask (Application Factory, Blueprints)
- **Database**: MongoDB Atlas (`pymongo[srv]`)
- **AI Engine**: Groq Cloud API (`groq`, `llama-3.3-70b-versatile` / `llama-3.1-8b-instant`)
- **Frontend**: HTML5, Vanilla Modern CSS, Vanilla JavaScript (ES6 Fetch API)
- **Configuration**: `python-dotenv`

---

## 📂 Project Architecture
```text
mock_interview_ai/
│
├── .env.example              # Template for environment variables
├── .gitignore                # Git ignore rules
├── requirements.txt          # Python dependencies
├── config.py                 # Central application configuration
├── run.py                    # Entry point to launch the Flask server
├── README.md                 # Project documentation
│
├── app/
│   ├── __init__.py           # Flask Application Factory
│   │
│   ├── routes/               # Modular Flask Blueprints
│   │   ├── main.py           # Landing page & about
│   │   ├── auth.py           # Registration, login, logout
│   │   ├── interview.py      # Setup, live session, Groq question/answer API, reports
│   │   └── dashboard.py      # Candidate metrics & interview history
│   │
│   ├── services/             # External services & databases
│   │   ├── db.py             # MongoDB Atlas connection manager & indexes
│   │   └── groq_service.py   # Groq API client with structured JSON prompts & fallback
│   │
│   ├── utils/                # Helper utilities
│   │   ├── auth.py           # Password hashing & @login_required decorator
│   │   └── validators.py     # Input sanitation & parameter validation
│   │
│   ├── static/               # Frontend assets
│   │   ├── css/              # main.css, auth.css, interview.css, dashboard.css
│   │   └── js/               # main.js, interview.js
│   │
│   └── templates/            # Jinja2 HTML templates
│       ├── base.html         # Base template with responsive navbar & flash alerts
│       ├── index.html        # Landing page
│       ├── about.html        # Project architecture documentation
│       ├── 404.html & 500.html
│       ├── auth/             # login.html, register.html
│       ├── interview/        # setup.html, session.html, report.html
│       └── dashboard/        # index.html
```

---

## ⚙️ Installation & Local Setup

### 1. Clone or Open Project
```bash
cd mock_interview_ai
```

### 2. Create and Activate Virtual Environment
**On Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**On macOS / Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Update `.env` with your credentials:
```env
SECRET_KEY=your_secure_random_key_here
MONGO_URI=mongodb+srv://<username>:<password>@cluster0.mongodb.net/?retryWrites=true&w=majority
MONGO_DB_NAME=mock_interview_db
GROQ_API_KEY=gsk_your_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile
```

> **Note:** If you don't have Groq or MongoDB credentials yet, the application will automatically run in fallback/demo mode with realistic mock questions and feedback so you can test all UI flows immediately.

### 5. Run the Application
```bash
python run.py
```
Open your browser and navigate to:
```
http://localhost:5000
```

### 6. Run Automated Tests
```bash
pytest -v
```

---

## 📡 REST API Reference

All `/api/interviews` endpoints require session authentication (`@login_required`).

| Method | Endpoint | Description | Status Codes |
|---|---|---|---|
| `POST` | `/api/interviews` | Create an interview for the authenticated student | `201 Created`, `400 Bad Request`, `401 Unauthorized`, `503 Service Unavailable` |
| `GET` | `/api/interviews` | List only the authenticated student's interviews | `200 OK`, `401 Unauthorized` |
| `GET` | `/api/interviews/<id>` | Retrieve an interview owned by the current student | `200 OK`, `400 Bad Request`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found` |
| `POST` | `/api/interviews/<id>/answer` | Evaluate and save an answer for the current question | `200 OK`, `400 Bad Request`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found`, `503 Service Unavailable` |
| `POST` | `/api/interviews/<id>/next` | Generate or retrieve the next question | `200 OK`, `400 Bad Request`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found`, `503 Service Unavailable` |
| `POST` | `/api/interviews/<id>/finish` | Finish an interview and calculate the final report | `200 OK`, `400 Bad Request`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found` |
| `GET` | `/api/interviews/<id>/report` | Retrieve the completed interview report | `200 OK`, `400 Bad Request`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found` |

### Security & State Integrity
- **Ownership Verification**: Enforced via MongoDB query filtering on `user_id`. Attempting to access another student's session returns `403 Forbidden`.
- **Validation**: Strict validation of ObjectId formatting, allowed categories (`Technical`, `HR`, `Aptitude`, `Communication`), difficulties (`Easy`, `Medium`, `Hard`), and answer lengths (5–5000 characters).
- **Immutability**: Completed interviews reject subsequent answers and question generations (`400 Bad Request`).
- **Duplicate Prevention**: Questions already answered cannot be re-answered (`400 Bad Request`).
- **Groq Failure Isolation**: If Groq API experiences rate limits or timeouts, MongoDB state is left untouched (unanswered) so students can retry safely without data loss or fabricated scores (`503 Service Unavailable`).
