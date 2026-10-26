import csv
import io
from datetime import date, datetime
from functools import wraps
from pathlib import Path

from flask import Flask, g, jsonify, request, send_from_directory, session
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from auth import hash_password, verify_password
from config import (
    ANTHROPIC_API_KEY,
    APP_NAME,
    APP_SECRET,
    DEMO_MODE,
    SMTP_FROM_EMAIL,
    SMTP_PASSWORD,
    SMTP_USERNAME,
)
from database import SessionLocal, init_db
from models import (
    ActivityLog,
    ChatMessage,
    EmailNotification,
    Project,
    Submission,
    TaskAssignment,
    TaskTemplate,
    User,
)
from services.ai_service import answer_doubt
from services.calendar_service import (
    calendar_is_configured,
    create_review_meeting,
    delete_review_meeting,
    validate_review_slot,
)
from services.email_service import task_email
from services.review_service import record_review
from services.scheduling_service import notify
from services.task_service import approve_and_assign_next, assign_task


FRONTEND_DIST = Path(__file__).parent / "frontend" / "dist"
app = Flask(__name__, static_folder=None)
app.secret_key = APP_SECRET
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)


def get_db():
    if "db" not in g:
        g.db = SessionLocal()
    return g.db


@app.teardown_appcontext
def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    user = get_db().get(User, user_id)
    if not user or not user.active:
        session.clear()
        return None
    return user


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            return jsonify(error="Please sign in to continue."), 401
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if current_user().role != "admin":
            return jsonify(error="Administrator access is required."), 403
        return view(*args, **kwargs)

    return wrapped


def json_body():
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}


def serialize_user(user):
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "active": user.active,
    }


def serialize_assignment(assignment, include_history=False):
    result = {
        "id": assignment.id,
        "intern_id": assignment.intern_id,
        "intern_name": assignment.intern.name,
        "intern_email": assignment.intern.email,
        "template_id": assignment.template_id,
        "task_title": assignment.template.title,
        "task_description": assignment.template.description,
        "acceptance_criteria": assignment.template.acceptance_criteria,
        "project_id": assignment.template.project_id,
        "project_name": assignment.template.project.name,
        "sequence": assignment.template.sequence,
        "status": assignment.status,
        "deadline": assignment.deadline,
        "review_at": assignment.review_at,
        "meet_url": assignment.meet_url,
        "submission_url": assignment.submission_url,
        "feedback": assignment.feedback,
        "created_at": assignment.created_at.isoformat(),
        "updated_at": assignment.updated_at.isoformat(),
    }
    if include_history:
        result["submissions"] = [
            {
                "id": submission.id,
                "url": submission.url,
                "note": submission.note,
                "submitted_at": submission.submitted_at.isoformat(),
            }
            for submission in sorted(
                assignment.submissions,
                key=lambda item: item.submitted_at,
                reverse=True,
            )
        ]
    return result


def send_assignment_email(db, assignment):
    body = task_email(
        assignment.intern.name,
        assignment.template.title,
        assignment.template.description,
        assignment.deadline,
        assignment.review_at,
        assignment.meet_url,
        app_url="your InternFlow dashboard",
    )
    return notify(
        db,
        assignment.intern.email,
        f"InternFlow AI: {assignment.template.title} assigned",
        body,
    )


def seed_if_empty():
    db = SessionLocal()
    try:
        if not db.scalar(select(func.count(User.id))):
            db.add_all(
                [
                    User(
                        name="Demo Administrator",
                        email="admin@internflow.local",
                        password_hash=hash_password("Admin123!"),
                        role="admin",
                    ),
                    User(
                        name="Asha Demo",
                        email="asha@example.test",
                        password_hash=hash_password("Intern123!"),
                        role="intern",
                    ),
                    User(
                        name="Ravi Demo",
                        email="ravi@example.test",
                        password_hash=hash_password("Intern123!"),
                        role="intern",
                    ),
                    User(
                        name="Mina Demo",
                        email="mina@example.test",
                        password_hash=hash_password("Intern123!"),
                        role="intern",
                    ),
                ]
            )
            db.commit()
        if not db.scalar(select(func.count(Project.id))):
            project = Project(
                name="Backend API Starter",
                description="Practice building and documenting a small REST API.",
            )
            db.add(project)
            db.flush()
            db.add_all(
                [
                    TaskTemplate(
                        project_id=project.id,
                        sequence=1,
                        title="Task 1: API Design",
                        description="Design a REST API with CRUD endpoints. Document request and response examples.",
                        acceptance_criteria="CRUD endpoints documented; request/response examples; input validation.",
                        default_days=3,
                    ),
                    TaskTemplate(
                        project_id=project.id,
                        sequence=2,
                        title="Task 2: Database Integration",
                        description="Connect the API to a relational database and implement persistence.",
                        acceptance_criteria="Database models; create/read/update/delete operations; basic tests.",
                        default_days=4,
                    ),
                ]
            )
            db.commit()
    finally:
        db.close()


init_db()
seed_if_empty()


@app.get("/api/session")
def session_info():
    user = current_user()
    if not user:
        return jsonify(user=None)
    return jsonify(user=serialize_user(user))


@app.post("/api/login")
def login():
    body = json_body()
    email = str(body.get("email", "")).strip().lower()
    password = body.get("password", "")
    if not email or not isinstance(password, str):
        return jsonify(error="Enter your email and password."), 400
    user = get_db().scalar(
        select(User).where(
            func.lower(User.email) == email,
            User.active.is_(True),
        )
    )
    if not user or not verify_password(password, user.password_hash):
        return jsonify(error="Invalid email or password."), 401
    session.clear()
    session["user_id"] = user.id
    return jsonify(user=serialize_user(user))


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@app.get("/api/dashboard")
@login_required
def dashboard():
    db = get_db()
    user = current_user()
    query = select(TaskAssignment).order_by(TaskAssignment.created_at.desc())
    if user.role == "intern":
        query = query.where(TaskAssignment.intern_id == user.id)
    assignments = db.scalars(query).all()
    if user.role == "admin":
        stats = {
            "interns": db.scalar(
                select(func.count(User.id)).where(User.role == "intern")
            )
            or 0,
            "projects": db.scalar(
                select(func.count(Project.id)).where(Project.active.is_(True))
            )
            or 0,
            "active_assignments": db.scalar(
                select(func.count(TaskAssignment.id)).where(
                    TaskAssignment.status.notin_(["APPROVED", "PROJECT_COMPLETE"])
                )
            )
            or 0,
            "pending_reviews": db.scalar(
                select(func.count(TaskAssignment.id)).where(
                    TaskAssignment.status == "SUBMITTED"
                )
            )
            or 0,
        }
    else:
        stats = {
            "assigned_tasks": len(assignments),
            "approved": sum(item.status == "APPROVED" for item in assignments),
            "needs_action": sum(
                item.status in ["ASSIGNED", "IN_PROGRESS", "REVISION_REQUIRED"]
                for item in assignments
            ),
        }
    return jsonify(
        stats=stats,
        assignments=[serialize_assignment(item) for item in assignments],
    )


@app.get("/api/interns")
@admin_required
def list_interns():
    users = get_db().scalars(
        select(User).where(User.role == "intern").order_by(User.name)
    )
    return jsonify(interns=[serialize_user(user) for user in users])


@app.post("/api/interns")
@admin_required
def create_intern():
    body = json_body()
    name = str(body.get("name", "")).strip()
    email = str(body.get("email", "")).strip().lower()
    password = body.get("password", "")
    if not name or "@" not in email or not isinstance(password, str) or len(password) < 8:
        return jsonify(error="Enter a name, valid email, and password of at least 8 characters."), 400
    db = get_db()
    if db.scalar(select(User.id).where(func.lower(User.email) == email)):
        return jsonify(error="That email is already registered."), 409
    intern = User(
        name=name,
        email=email,
        password_hash=hash_password(password),
        role="intern",
    )
    db.add(intern)
    db.commit()
    return jsonify(intern=serialize_user(intern)), 201


@app.post("/api/interns/import")
@admin_required
def import_interns():
    upload = request.files.get("file")
    if not upload:
        return jsonify(error="Choose a CSV file to import."), 400
    try:
        rows = csv.DictReader(io.StringIO(upload.stream.read().decode("utf-8-sig")))
        if not rows.fieldnames or not {"name", "email"}.issubset(rows.fieldnames):
            return jsonify(error="CSV must contain name and email columns."), 400
        db = get_db()
        added, skipped = 0, []
        for row in rows:
            name = (row.get("name") or "").strip()
            email = (row.get("email") or "").strip().lower()
            if (
                not name
                or "@" not in email
                or db.scalar(select(User.id).where(func.lower(User.email) == email))
            ):
                skipped.append(email or "(empty)")
                continue
            password = (row.get("password") or "").strip() or "ChangeMe123!"
            db.add(
                User(
                    name=name,
                    email=email,
                    password_hash=hash_password(password),
                    role="intern",
                )
            )
            added += 1
        db.commit()
        return jsonify(added=added, skipped=skipped)
    except (UnicodeDecodeError, csv.Error) as exc:
        return jsonify(error=f"Could not read CSV: {exc}"), 400


@app.get("/api/interns/cohort-template")
@admin_required
def download_cohort_template():
    return send_from_directory(
        Path(__file__).parent / "data",
        "intern_cohort_template.csv",
        as_attachment=True,
    )


@app.post("/api/interns/import-cohort")
@admin_required
def import_intern_cohort():
    if not calendar_is_configured():
        return jsonify(
            error=(
                "Google Calendar is not configured. Set GOOGLE_CLIENT_ID, "
                "GOOGLE_CLIENT_SECRET, and GOOGLE_REFRESH_TOKEN in .env before importing."
            )
        ), 503
    if DEMO_MODE or not all([SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM_EMAIL]):
        return jsonify(
            error=(
                "Real email delivery is not configured. Set DEMO_MODE=false and configure "
                "SMTP_USERNAME, SMTP_PASSWORD, and SMTP_FROM_EMAIL before importing."
            )
        ), 503

    upload = request.files.get("file")
    if not upload:
        return jsonify(error="Choose the completed cohort CSV file."), 400
    content = upload.stream.read(2_000_001)
    if len(content) > 2_000_000:
        return jsonify(error="CSV is too large. Maximum upload size is 2 MB."), 413
    try:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
        required = {
            "name",
            "email",
            "password",
            "task_title",
            "task_description",
            "acceptance_criteria",
            "deadline",
            "review_datetime",
            "timezone",
        }
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            return jsonify(
                error="CSV must use the cohort template headers. Download a fresh template and fill it in."
            ), 400
        rows = []
        for row_number, source in enumerate(reader, start=2):
            if not any((value or "").strip() for value in source.values() if isinstance(value, str)):
                continue
            if None in source:
                return jsonify(error=f"Row {row_number} has extra values or commas in a field; quote CSV text fields."), 400
            row = {key: (source.get(key) or "").strip() for key in required}
            if any(not row[key] for key in required):
                return jsonify(error=f"Row {row_number}: every template field is required."), 400
            row["email"] = row["email"].lower()
            if "@" not in row["email"] or row["email"].startswith("@") or row["email"].endswith("@"):
                return jsonify(error=f"Row {row_number}: enter a valid email address."), 400
            if len(row["password"]) < 8:
                return jsonify(error=f"Row {row_number}: temporary password must be at least 8 characters."), 400
            try:
                row["deadline"] = date.fromisoformat(row["deadline"]).isoformat()
                validate_review_slot(row["review_datetime"], row["timezone"])
            except ValueError as exc:
                return jsonify(error=f"Row {row_number}: {exc}"), 400
            rows.append(row)
            if len(rows) > 100:
                return jsonify(error="A cohort import can contain at most 100 interns."), 400
        if not rows:
            return jsonify(error="The CSV has no intern rows to import."), 400
        email_addresses = [row["email"] for row in rows]
        if len(set(email_addresses)) != len(email_addresses):
            return jsonify(error="Each intern must have a unique email address in the CSV."), 409
        task_titles = [row["task_title"].casefold() for row in rows]
        if len(set(task_titles)) != len(task_titles):
            return jsonify(error="Each intern must have a distinct task title in the CSV."), 409
    except (UnicodeDecodeError, csv.Error) as exc:
        return jsonify(error=f"Could not read CSV: {exc}"), 400

    db = get_db()
    existing_emails = set(
        db.scalars(
            select(func.lower(User.email)).where(
                func.lower(User.email).in_(email_addresses)
            )
        ).all()
    )
    if existing_emails:
        return jsonify(
            error="Some email addresses are already registered.",
            duplicate_emails=sorted(existing_emails),
        ), 409

    events = []
    try:
        for row in rows:
            event = create_review_meeting(
                attendee_email=row["email"],
                task_title=row["task_title"],
                review_datetime=row["review_datetime"],
                timezone_name=row["timezone"],
            )
            events.append(event)
    except (RuntimeError, ValueError) as exc:
        cancellation_errors = []
        for event in reversed(events):
            try:
                delete_review_meeting(event["event_id"])
            except RuntimeError as cancel_error:
                cancellation_errors.append(str(cancel_error))
        return jsonify(
            error=str(exc),
            cancelled_meetings=len(events) - len(cancellation_errors),
            cleanup_errors=cancellation_errors,
        ), 502

    project = Project(
        name=f"Intern cohort — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        description="Cohort imported from CSV. Each intern has an individual task and review meeting.",
    )
    imported_assignments = []
    try:
        db.add(project)
        db.flush()
        for index, (row, event) in enumerate(zip(rows, events), start=1):
            intern = User(
                name=row["name"],
                email=row["email"],
                password_hash=hash_password(row["password"]),
                role="intern",
            )
            db.add(intern)
            db.flush()
            template = TaskTemplate(
                project_id=project.id,
                sequence=index,
                title=row["task_title"],
                description=row["task_description"],
                acceptance_criteria=row["acceptance_criteria"],
                default_days=max(
                    1,
                    (date.fromisoformat(row["deadline"]) - date.today()).days,
                ),
            )
            db.add(template)
            db.flush()
            assignment = TaskAssignment(
                intern_id=intern.id,
                template_id=template.id,
                status="ASSIGNED",
                deadline=row["deadline"],
                review_at=f"{row['review_datetime']} {row['timezone']}",
                meet_url=event["meet_url"],
            )
            db.add(assignment)
            db.add(
                ActivityLog(
                    actor_email=current_user().email,
                    action="COHORT_TASK_ASSIGNED",
                    details=f"intern={intern.email}; task={template.title}",
                )
            )
            imported_assignments.append(assignment)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        cancellation_errors = []
        for event in reversed(events):
            try:
                delete_review_meeting(event["event_id"])
            except RuntimeError as exc:
                cancellation_errors.append(str(exc))
        return jsonify(
            error="Could not save the cohort to the database; the import was rolled back.",
            cleanup_errors=cancellation_errors,
        ), 500

    email_results = []
    for assignment in imported_assignments:
        status, error = send_assignment_email(db, assignment)
        email_results.append(
            {
                "email": assignment.intern.email,
                "status": status,
                "message": error,
            }
        )
    return jsonify(
        imported=len(imported_assignments),
        project_name=project.name,
        emails=email_results,
        email_failures=sum(result["status"] == "FAILED" for result in email_results),
    ), 201


@app.get("/api/projects")
@admin_required
def list_projects():
    projects = get_db().scalars(select(Project).order_by(Project.name)).all()
    return jsonify(
        projects=[
            {
                "id": project.id,
                "name": project.name,
                "description": project.description,
                "active": project.active,
                "tasks": [
                    {
                        "id": task.id,
                        "sequence": task.sequence,
                        "title": task.title,
                        "description": task.description,
                        "acceptance_criteria": task.acceptance_criteria,
                        "default_days": task.default_days,
                    }
                    for task in sorted(project.tasks, key=lambda item: item.sequence)
                ],
            }
            for project in projects
        ]
    )


@app.post("/api/projects")
@admin_required
def create_project():
    body = json_body()
    name = str(body.get("name", "")).strip()
    if not name:
        return jsonify(error="Project name is required."), 400
    project = Project(name=name, description=str(body.get("description", "")).strip())
    db = get_db()
    db.add(project)
    db.commit()
    return jsonify(id=project.id, name=project.name), 201


@app.post("/api/projects/<int:project_id>/tasks")
@admin_required
def create_task_template(project_id):
    body = json_body()
    db = get_db()
    project = db.get(Project, project_id)
    title = str(body.get("title", "")).strip()
    description = str(body.get("description", "")).strip()
    if not project:
        return jsonify(error="Project not found."), 404
    if not title or not description:
        return jsonify(error="Task title and instructions are required."), 400
    try:
        sequence = int(body.get("sequence", 1))
        days = int(body.get("default_days", 7))
    except (ValueError, TypeError):
        return jsonify(error="Sequence and deadline must be whole numbers."), 400
    if sequence < 1 or not 1 <= days <= 90:
        return jsonify(error="Sequence must be positive and deadline must be 1–90 days."), 400
    task = TaskTemplate(
        project_id=project.id,
        sequence=sequence,
        title=title,
        description=description,
        acceptance_criteria=str(body.get("acceptance_criteria", "")).strip(),
        default_days=days,
    )
    db.add(task)
    db.commit()
    return jsonify(id=task.id, title=task.title), 201


@app.get("/api/assignments")
@admin_required
def list_assignments():
    assignments = get_db().scalars(
        select(TaskAssignment).order_by(TaskAssignment.created_at.desc())
    ).all()
    return jsonify(assignments=[serialize_assignment(item) for item in assignments])


@app.post("/api/assignments")
@admin_required
def create_assignment():
    body = json_body()
    db = get_db()
    intern = db.get(User, body.get("intern_id"))
    template = db.get(TaskTemplate, body.get("template_id"))
    if not intern or intern.role != "intern" or not intern.active:
        return jsonify(error="Select an active intern."), 400
    if not template:
        return jsonify(error="Select a valid task."), 400
    meet_url = str(body.get("meet_url", "")).strip()
    if meet_url and not meet_url.startswith("https://"):
        return jsonify(error="Meeting URL must start with https://."), 400
    deadline = str(body.get("deadline", "")).strip() or date.today().isoformat()
    assignment, created = assign_task(
        db,
        intern,
        template,
        deadline=deadline,
        review_at=str(body.get("review_at", "")).strip(),
        meet_url=meet_url,
        actor=current_user().email,
    )
    if not created:
        return jsonify(
            error="This task is already assigned to this intern.",
            assignment=serialize_assignment(assignment),
        ), 409
    status, error = send_assignment_email(db, assignment)
    return jsonify(
        assignment=serialize_assignment(assignment),
        email_status=status,
        email_message=error,
    ), 201


@app.post("/api/assignments/<int:assignment_id>/schedule-review")
@admin_required
def schedule_assignment_review(assignment_id):
    if not calendar_is_configured():
        return jsonify(
            error=(
                "Google Calendar is not configured. Set GOOGLE_CLIENT_ID, "
                "GOOGLE_CLIENT_SECRET, and GOOGLE_REFRESH_TOKEN in .env."
            )
        ), 503
    if DEMO_MODE or not all([SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM_EMAIL]):
        return jsonify(
            error=(
                "Real email delivery is not configured. Set DEMO_MODE=false and "
                "configure SMTP_USERNAME, SMTP_PASSWORD, and SMTP_FROM_EMAIL in .env."
            )
        ), 503
    body = json_body()
    review_datetime = str(body.get("review_datetime", "")).strip()
    timezone_name = str(body.get("timezone", "")).strip()
    try:
        validate_review_slot(review_datetime, timezone_name)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400

    db = get_db()
    assignment = db.get(TaskAssignment, assignment_id)
    if not assignment:
        return jsonify(error="Assignment not found."), 404
    if assignment.meet_url:
        return jsonify(error="A meeting link is already set for this assignment."), 409

    try:
        event = create_review_meeting(
            attendee_email=assignment.intern.email,
            task_title=assignment.template.title,
            review_datetime=review_datetime,
            timezone_name=timezone_name,
        )
    except (RuntimeError, ValueError) as exc:
        return jsonify(error=str(exc)), 502

    assignment.review_at = f"{review_datetime} {timezone_name}"
    assignment.meet_url = event["meet_url"]
    db.add(
        ActivityLog(
            actor_email=current_user().email,
            action="REVIEW_MEETING_SCHEDULED",
            details=f"assignment_id={assignment.id}; event_id={event['event_id']}",
        )
    )
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        try:
            delete_review_meeting(event["event_id"])
        except RuntimeError as exc:
            return jsonify(
                error="Could not save the meeting to the assignment or cancel its calendar event.",
                cleanup_error=str(exc),
            ), 500
        return jsonify(error="Could not save the meeting to the assignment; the calendar event was cancelled."), 500

    status, error = notify(
        db,
        assignment.intern.email,
        f"Review meeting scheduled: {assignment.template.title}",
        (
            f"Your review meeting for {assignment.template.title} is scheduled for "
            f"{review_datetime} {timezone_name}.\n\n"
            f"Google Meet: {event['meet_url']}\n\n"
            "The calendar invitation has also been sent."
        ),
    )
    return jsonify(
        assignment=serialize_assignment(assignment),
        email_status=status,
        email_message=error,
    )


@app.post("/api/assignments/<int:assignment_id>/submission")
@login_required
def submit_assignment(assignment_id):
    user = current_user()
    db = get_db()
    assignment = db.get(TaskAssignment, assignment_id)
    if not assignment or (user.role == "intern" and assignment.intern_id != user.id):
        return jsonify(error="Assignment not found."), 404
    if user.role != "intern":
        return jsonify(error="Only interns can submit work."), 403
    if assignment.status not in ["ASSIGNED", "IN_PROGRESS", "REVISION_REQUIRED"]:
        return jsonify(error="This assignment is not accepting submissions."), 409
    body = json_body()
    url = str(body.get("url", "")).strip()
    if not url.startswith(("https://", "http://")):
        return jsonify(error="Enter a valid http(s) submission URL."), 400
    note = str(body.get("note", "")).strip()
    db.add(Submission(assignment_id=assignment.id, url=url, note=note))
    assignment.submission_url = url
    assignment.status = "SUBMITTED"
    db.commit()
    status, error = notify(
        db,
        user.email,
        f"Submission received: {assignment.template.title}",
        f"Submission received for {assignment.template.title}.\nSubmission: {url}",
    )
    return jsonify(
        assignment=serialize_assignment(assignment, include_history=True),
        email_status=status,
        email_message=error,
    )


@app.get("/api/reviews")
@admin_required
def list_reviews():
    assignments = get_db().scalars(
        select(TaskAssignment)
        .where(
            TaskAssignment.status.in_(
                ["SUBMITTED", "UNDER_REVIEW", "REVISION_REQUIRED"]
            )
        )
        .order_by(TaskAssignment.updated_at)
    ).all()
    return jsonify(assignments=[serialize_assignment(item, True) for item in assignments])


@app.post("/api/assignments/<int:assignment_id>/review")
@admin_required
def review_assignment(assignment_id):
    body = json_body()
    outcome = body.get("outcome")
    feedback = str(body.get("feedback", "")).strip()
    if outcome not in ["CHANGES_REQUESTED", "APPROVED", "REJECTED"]:
        return jsonify(error="Choose a valid review outcome."), 400
    db = get_db()
    assignment = db.get(TaskAssignment, assignment_id)
    if not assignment:
        return jsonify(error="Assignment not found."), 404
    record_review(db, assignment, outcome, feedback, actor=current_user().email)
    status, error = notify(
        db,
        assignment.intern.email,
        f"Review feedback: {assignment.template.title}",
        f"Review result for {assignment.template.title}: {outcome}\n\nFeedback:\n{feedback}\n\nPlease log in to your InternFlow dashboard for details.",
    )
    next_task = None
    if outcome == "APPROVED":
        next_assignment, created = approve_and_assign_next(
            db, assignment, actor=current_user().email
        )
        if next_assignment and created:
            next_task = next_assignment.template.title
            send_assignment_email(db, next_assignment)
        elif not next_assignment:
            notify(
                db,
                assignment.intern.email,
                f"Project completed: {assignment.template.project.name}",
                f"Congratulations! All tasks in the project '{assignment.template.project.name}' have been approved.",
            )
    return jsonify(
        assignment=serialize_assignment(assignment),
        email_status=status,
        email_message=error,
        next_task=next_task,
    )


@app.post("/api/assistant")
@login_required
def ask_assistant():
    user = current_user()
    if user.role != "intern":
        return jsonify(error="The assistant is available to interns."), 403
    body = json_body()
    question = str(body.get("question", "")).strip()
    if not question:
        return jsonify(error="Enter a question first."), 400
    db = get_db()
    assignment = None
    assignment_id = body.get("assignment_id")
    if assignment_id:
        assignment = db.get(TaskAssignment, assignment_id)
        if not assignment or assignment.intern_id != user.id:
            return jsonify(error="Task context not found."), 404
    context = ""
    if assignment:
        context = (
            f"Task: {assignment.template.title}\n"
            f"Instructions: {assignment.template.description}\n"
            f"Acceptance criteria: {assignment.template.acceptance_criteria}\n"
            f"Mentor feedback: {assignment.feedback}"
        )
    answer, mode = answer_doubt(question, context)
    db.add_all(
        [
            ChatMessage(
                intern_id=user.id,
                assignment_id=assignment.id if assignment else None,
                role="user",
                content=question,
            ),
            ChatMessage(
                intern_id=user.id,
                assignment_id=assignment.id if assignment else None,
                role="assistant",
                content=answer,
            ),
        ]
    )
    db.commit()
    return jsonify(answer=answer, mode=mode)


@app.get("/api/assistant/history")
@login_required
def assistant_history():
    user = current_user()
    if user.role != "intern":
        return jsonify(messages=[])
    messages = get_db().scalars(
        select(ChatMessage)
        .where(ChatMessage.intern_id == user.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(20)
    ).all()
    return jsonify(
        messages=[
            {
                "role": message.role,
                "content": message.content,
                "created_at": message.created_at.isoformat(),
            }
            for message in reversed(messages)
        ]
    )


@app.get("/api/email-log")
@admin_required
def email_log():
    logs = get_db().scalars(
        select(EmailNotification)
        .order_by(EmailNotification.created_at.desc())
        .limit(300)
    ).all()
    return jsonify(
        emails=[
            {
                "recipient": item.recipient,
                "subject": item.subject,
                "status": item.status,
                "created_at": item.created_at.isoformat(),
                "error": item.error,
            }
            for item in logs
        ]
    )


@app.get("/api/settings")
@admin_required
def settings():
    return jsonify(
        email_mode="SIMULATED" if DEMO_MODE else "SMTP configured mode",
        email_configured=not DEMO_MODE and all(
            [SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM_EMAIL]
        ),
        ai_mode="Claude" if ANTHROPIC_API_KEY else "Demo fallback",
        demo_mode=DEMO_MODE,
        google_calendar_configured=calendar_is_configured(),
    )


@app.get("/", defaults={"path": ""})
@app.get("/<path:path>")
def frontend(path):
    if path.startswith("api/"):
        return jsonify(error="API endpoint not found."), 404
    if not FRONTEND_DIST.exists():
        return (
            "Frontend has not been built. Run `npm install` and `npm run build` in the frontend directory.",
            503,
        )
    requested = FRONTEND_DIST / path
    if path and requested.is_file():
        return send_from_directory(FRONTEND_DIST, path)
    return send_from_directory(FRONTEND_DIST, "index.html")


if __name__ == "__main__":
    app.run(port=5000)
