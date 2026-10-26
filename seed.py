from database import init_db, SessionLocal
from sqlalchemy import select, func
from models import User, Project, TaskTemplate
from auth import hash_password

init_db()
db = SessionLocal()
try:
    if not db.scalar(select(func.count(User.id))):
        db.add_all([
            User(name="Demo Administrator", email="admin@internflow.local", password_hash=hash_password("Admin123!"), role="admin"),
            User(name="Asha Demo", email="asha@example.test", password_hash=hash_password("Intern123!"), role="intern"),
            User(name="Ravi Demo", email="ravi@example.test", password_hash=hash_password("Intern123!"), role="intern"),
            User(name="Mina Demo", email="mina@example.test", password_hash=hash_password("Intern123!"), role="intern"),
        ])
        db.commit()
    if not db.scalar(select(func.count(Project.id))):
        project = Project(name="Backend API Starter", description="Practice building and documenting a small REST API.")
        db.add(project)
        db.flush()
        db.add_all([
            TaskTemplate(project_id=project.id, sequence=1, title="Task 1: API Design", description="Design a REST API with CRUD endpoints. Document request and response examples.", acceptance_criteria="CRUD endpoints documented; request/response examples; input validation.", default_days=3),
            TaskTemplate(project_id=project.id, sequence=2, title="Task 2: Database Integration", description="Connect the API to a relational database and implement persistence.", acceptance_criteria="Database models; create/read/update/delete operations; basic tests.", default_days=4),
        ])
        db.commit()
    print("Database initialized and demo data is ready.")
finally:
    db.close()
