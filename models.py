from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, ForeignKey, Text, Boolean, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base

def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="intern")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    assignments: Mapped[list["TaskAssignment"]] = relationship(back_populates="intern")

class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    tasks: Mapped[list["TaskTemplate"]] = relationship(back_populates="project", cascade="all, delete-orphan")

class TaskTemplate(Base):
    __tablename__ = "task_templates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    sequence: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    acceptance_criteria: Mapped[str] = mapped_column(Text, default="")
    default_days: Mapped[int] = mapped_column(Integer, default=7)
    project: Mapped["Project"] = relationship(back_populates="tasks")
    assignments: Mapped[list["TaskAssignment"]] = relationship(back_populates="template")

class TaskAssignment(Base):
    __tablename__ = "task_assignments"
    __table_args__ = (UniqueConstraint("intern_id", "template_id", name="uq_intern_template"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    intern_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("task_templates.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="ASSIGNED")
    deadline: Mapped[str] = mapped_column(String(40), default="")
    review_at: Mapped[str] = mapped_column(String(80), default="")
    meet_url: Mapped[str] = mapped_column(String(500), default="")
    submission_url: Mapped[str] = mapped_column(String(1000), default="")
    feedback: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    intern: Mapped["User"] = relationship(back_populates="assignments")
    template: Mapped["TaskTemplate"] = relationship(back_populates="assignments")
    submissions: Mapped[list["Submission"]] = relationship(back_populates="assignment", cascade="all, delete-orphan")
    reviews: Mapped[list["Review"]] = relationship(back_populates="assignment", cascade="all, delete-orphan")

class Submission(Base):
    __tablename__ = "submissions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("task_assignments.id"), index=True)
    url: Mapped[str] = mapped_column(String(1000))
    note: Mapped[str] = mapped_column(Text, default="")
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    assignment: Mapped["TaskAssignment"] = relationship(back_populates="submissions")

class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("task_assignments.id"), index=True)
    outcome: Mapped[str] = mapped_column(String(32))
    feedback: Mapped[str] = mapped_column(Text)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    assignment: Mapped["TaskAssignment"] = relationship(back_populates="reviews")

class EmailNotification(Base):
    __tablename__ = "email_notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recipient: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="PREVIEW")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    intern_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    assignment_id: Mapped[int | None] = mapped_column(ForeignKey("task_assignments.id"), nullable=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class ActivityLog(Base):
    __tablename__ = "activity_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_email: Mapped[str] = mapped_column(String(255), default="system")
    action: Mapped[str] = mapped_column(String(200))
    details: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
