from datetime import date, timedelta
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from models import TaskAssignment, TaskTemplate, Project, ActivityLog

def assign_task(db, intern, template, deadline=None, review_at="", meet_url="", actor="admin"):
    existing = db.scalar(select(TaskAssignment).where(
        TaskAssignment.intern_id == intern.id, TaskAssignment.template_id == template.id))
    if existing:
        return existing, False
    if not deadline:
        deadline = (date.today() + timedelta(days=max(1, template.default_days))).isoformat()
    assignment = TaskAssignment(
        intern_id=intern.id, template_id=template.id, status="ASSIGNED",
        deadline=deadline, review_at=review_at, meet_url=meet_url
    )
    db.add(assignment)
    db.add(ActivityLog(actor_email=actor, action="TASK_ASSIGNED",
                       details=f"intern={intern.email}; task={template.title}"))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(TaskAssignment).where(
            TaskAssignment.intern_id == intern.id, TaskAssignment.template_id == template.id))
        return existing, False
    db.refresh(assignment)
    return assignment, True

def approve_and_assign_next(db, assignment, actor="admin"):
    assignment.status = "APPROVED"
    db.add(ActivityLog(actor_email=actor, action="TASK_APPROVED", details=f"assignment_id={assignment.id}"))
    db.commit()
    templates = db.scalars(select(TaskTemplate).where(
        TaskTemplate.project_id == assignment.template.project_id
    ).order_by(TaskTemplate.sequence)).all()
    for template in templates:
        if template.sequence > assignment.template.sequence:
            existing = db.scalar(select(TaskAssignment).where(
                TaskAssignment.intern_id == assignment.intern_id,
                TaskAssignment.template_id == template.id))
            if not existing:
                return assign_task(db, assignment.intern, template, actor=actor)
    return None, False
