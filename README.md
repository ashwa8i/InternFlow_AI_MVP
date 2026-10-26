# InternFlow AI

A fast local MVP for intern task allocation, submission tracking, mentor reviews, email notification previews/SMTP, and task-aware AI assistance.

## Requirements
- Python 3.11+
- Node.js 20+
- Optional: Gmail SMTP credentials and an Anthropic API key

## Windows PowerShell setup

```powershell
cd internflow-ai
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
cd frontend
npm install
npm run build
cd ..
python app.py
```

Open `http://127.0.0.1:5000`. The React application is served by the Flask backend. The SQLite database and demo seed data are initialized automatically on first run.

For frontend development with Vite hot reload, run `python app.py` in one terminal and `npm run dev` from `frontend` in another, then open the Vite URL shown in the terminal.

## Demo accounts

- Admin: `admin@internflow.local` / `Admin123!`
- Intern: `asha@example.test` / `Intern123!`
- Other seeded interns: `ravi@example.test`, `mina@example.test` (password `Intern123!`)

These accounts are for local demo only. Do not deploy with these credentials. For a real deployment, implement an administrator-controlled password reset/invitation flow, verified email ownership, HTTPS, and secure session management.

## Features
- Intern registration and CSV import (`name,email` required; optional `password`)
- Cohort CSV import for up to 100 interns with individual task templates and review meetings
- Projects and ordered task templates
- Assignment records with duplicate protection
- Submission link history
- Mentor review, feedback, revision request, approval and next-task allocation
- Email notification log with explicit simulated/SMTP accepted/failed status
- Claude-backed task-aware assistant when `ANTHROPIC_API_KEY` is set; otherwise a labeled demo response
- SQLite persistence

## Configure real SMTP
1. Set `DEMO_MODE=false` in `.env`.
2. Set `SMTP_USERNAME`, `SMTP_PASSWORD`, and `SMTP_FROM_EMAIL`.
3. For Gmail, enable 2-Step Verification and create an App Password where available. Do not use your normal Gmail password.
4. Restart the Flask app.
5. Test with an address you control. `SMTP_ACCEPTED` means the SMTP server accepted the message; it does not guarantee inbox delivery.

## Configure Google Meet scheduling
The admin intern-import flow can create an individual Google Calendar review event with a generated Meet link for each CSV row. The event invitation goes to the intern; the task-assignment email also includes its link. Admins can also schedule a review for an existing assignment from **Assignments → Review scheduling assistant**.

1. In Google Cloud Console, select or create a project, enable **Google Calendar API**, configure the OAuth consent screen, and add your Google account as a test user if the app is in testing.
2. Create an OAuth client ID with application type **Desktop app** and download its JSON file. Keep it private and do not commit it to source control.
3. From `internflow-ai`, run `python setup_google_calendar.py "C:\path\to\client_secret.json"`. A browser window will ask you to sign into Google and grant Calendar event access. The script writes the OAuth client ID, secret, and refresh token directly into `.env`; do not paste them into chat.
4. Optionally set `GOOGLE_CALENDAR_ID` and `GOOGLE_MEET_DURATION_MINUTES` (default: `primary` calendar and 30 minutes).
5. Restart Flask. The cohort import checks both Google Calendar and real SMTP configuration before creating events or accounts.

Download `data/intern_cohort_template.csv`, fill one row per intern (up to 100), then use **Interns → Import CSV**. Each row requires `name,email,password,task_title,task_description,acceptance_criteria,deadline,review_datetime,timezone`. Use `YYYY-MM-DD` for deadlines, `YYYY-MM-DD HH:MM` for local review times, and an IANA time zone such as `Asia/Kolkata`. Each imported intern gets a distinct task template and a separate review event. If event creation fails, the import cancels any meetings created in that attempt and does not create the cohort in the database.

## Configure Claude (optional)
Set `ANTHROPIC_API_KEY` and optionally `CLAUDE_MODEL` in `.env`, then restart the app. API use may incur charges according to your Anthropic account and model.

## Important MVP limitations
- Email is outbound only; automatic Gmail inbox monitoring and email-thread reply handling are not implemented.
- Review dates are stored and shown, but a persistent background reminder scheduler is not included.
- Intern login is a local demo login, not verified email authentication.
- No actual project file/repository analysis is performed; the mentor reviews the submitted link.
- Before real use, add verified-email onboarding, password reset, rate limiting, robust audit/retention policy, HTTPS, backups, and stronger production authentication.

## Tests
```powershell
pytest -q
```

## Project structure
- `app.py`: Flask API, session handling, and React app serving
- `frontend/`: React application and Vite build configuration
- `models.py`, `database.py`: SQLAlchemy models and database
- `auth.py`: password hashing and verification
- `services/task_service.py`: task allocation and next-task logic
- `services/review_service.py`: review outcomes
- `services/email_service.py`: email previews and optional SMTP
- `services/ai_service.py`: optional Claude integration and demo fallback
- `services/scheduling_service.py`: notification logging and scheduler hook
- `data/sample_interns.csv`: fictional sample import
