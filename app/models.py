from datetime import date, datetime, timezone
from sqlalchemy import String, Text, ForeignKey, DateTime, Date, Index, CheckConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base


def now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    timezone: Mapped[str] = mapped_column(String(80), default='UTC')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Session(Base):
    __tablename__ = 'sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    csrf: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Resume(Base):
    __tablename__ = 'resume_files'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    name: Mapped[str] = mapped_column(String(100))
    filename: Mapped[str] = mapped_column(String(50), unique=True)
    size: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Application(Base):
    __tablename__ = 'applications'
    __table_args__ = (
        Index('ix_app_user_status', 'user_id', 'status'),
        CheckConstraint("status IN ('Saved','Applied','Assessment','Interview','Offer','Rejected','Withdrawn')"),
        CheckConstraint("work_mode IN ('Remote','Hybrid','On-site')"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    company: Mapped[str] = mapped_column(String(160))
    role: Mapped[str] = mapped_column(String(160))
    job_url: Mapped[str] = mapped_column(String(2000), default='')
    location: Mapped[str] = mapped_column(String(160), default='')
    work_mode: Mapped[str] = mapped_column(String(20), default='Remote')
    salary: Mapped[str] = mapped_column(String(160), default='')
    status: Mapped[str] = mapped_column(String(20), default='Saved')
    application_date: Mapped[date | None] = mapped_column(Date)
    deadline: Mapped[date | None] = mapped_column(Date)
    recruiter_name: Mapped[str] = mapped_column(String(100), default='')
    recruiter_email: Mapped[str] = mapped_column(String(254), default='')
    notes: Mapped[str] = mapped_column(Text, default='')
    resume_id: Mapped[int | None] = mapped_column(ForeignKey('resume_files.id', ondelete='SET NULL'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class StatusHistory(Base):
    __tablename__ = 'application_status_history'
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey('applications.id', ondelete='CASCADE'), index=True)
    status: Mapped[str] = mapped_column(String(20))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Interview(Base):
    __tablename__ = 'interviews'
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey('applications.id', ondelete='CASCADE'), index=True)
    title: Mapped[str] = mapped_column(String(160))
    type: Mapped[str] = mapped_column(String(20))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    timezone: Mapped[str] = mapped_column(String(80))
    venue: Mapped[str] = mapped_column(String(2000), default='')
    notes: Mapped[str] = mapped_column(Text, default='')
    outcome: Mapped[str] = mapped_column(Text, default='')


class FollowUp(Base):
    __tablename__ = 'follow_ups'
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey('applications.id', ondelete='CASCADE'), index=True)
    due_date: Mapped[date] = mapped_column(Date, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GoogleAccount(Base):
    __tablename__ = 'google_accounts'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    subject: Mapped[str] = mapped_column(String(255), unique=True)
    email: Mapped[str] = mapped_column(String(254))
    refresh_token: Mapped[str | None] = mapped_column(Text)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sync_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    page_token: Mapped[str | None] = mapped_column(Text)


class GoogleOAuthState(Base):
    __tablename__ = 'google_oauth_states'
    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    browser_hash: Mapped[str] = mapped_column(String(64))
    verifier: Mapped[str] = mapped_column(String(128))
    purpose: Mapped[str] = mapped_column(String(20))
    session_hash: Mapped[str | None] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EmailCandidate(Base):
    __tablename__ = 'email_candidates'
    __table_args__ = (UniqueConstraint('user_id', 'message_id', name='uq_email_user_message'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    message_id: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(500))
    sender: Mapped[str] = mapped_column(String(500))
    snippet: Mapped[str] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    suggested_status: Mapped[str] = mapped_column(String(20), default='Applied')
    company: Mapped[str] = mapped_column(String(160), default='')
    role: Mapped[str] = mapped_column(String(160), default='')
    reviewed: Mapped[bool] = mapped_column(default=False)
    application_id: Mapped[int | None] = mapped_column(ForeignKey('applications.id', ondelete='SET NULL'))
