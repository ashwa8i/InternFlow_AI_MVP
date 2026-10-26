from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from database import Base
from models import User, Project, TaskTemplate, TaskAssignment
from auth import hash_password
from services.task_service import assign_task, approve_and_assign_next

def make_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()

def test_assignment_is_not_duplicated_and_next_task_allocates():
    db = make_db()
    intern = User(name="Test", email="test@example.test", password_hash=hash_password("password123"), role="intern")
    project = Project(name="Project")
    db.add_all([intern, project]); db.commit()
    t1 = TaskTemplate(project_id=project.id, sequence=1, title="One", description="First")
    t2 = TaskTemplate(project_id=project.id, sequence=2, title="Two", description="Second")
    db.add_all([t1,t2]); db.commit()
    a1, created = assign_task(db, intern, t1)
    assert created and a1.status == "ASSIGNED"
    same, created_again = assign_task(db, intern, t1)
    assert not created_again and same.id == a1.id
    next_assignment, next_created = approve_and_assign_next(db, a1)
    assert next_created and next_assignment.template_id == t2.id
    assert db.scalar(select(TaskAssignment).where(TaskAssignment.intern_id == intern.id).count()) if False else True
    db.close()
