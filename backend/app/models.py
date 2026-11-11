from datetime import datetime, timezone
from sqlalchemy import String, Integer, ForeignKey, DateTime, Boolean, Text, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base

def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)

class Identity:
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class Company(Identity, Base):
    __tablename__ = 'companies'
    name: Mapped[str] = mapped_column(String(160))
    industry: Mapped[str] = mapped_column(String(100), default='')
    country: Mapped[str] = mapped_column(String(80), default='India')
    size: Mapped[str] = mapped_column(String(40), default='1–10')
    currency: Mapped[str] = mapped_column(String(3), default='INR')
    timezone: Mapped[str] = mapped_column(String(80), default='Asia/Kolkata')
    plan: Mapped[str] = mapped_column(String(40), default='Starter')

class User(Identity, Base):
    __tablename__ = 'users'
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(Text)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    phone: Mapped[str] = mapped_column(String(40), default='')
    job_title: Mapped[str] = mapped_column(String(120), default='')
    department: Mapped[str] = mapped_column(String(120), default='')
    timezone: Mapped[str] = mapped_column(String(80), default='Asia/Kolkata')
    language: Mapped[str] = mapped_column(String(20), default='English')
    avatar: Mapped[str] = mapped_column(Text, default='')

class Membership(Identity, Base):
    __tablename__ = 'memberships'
    __table_args__ = (UniqueConstraint('user_id', 'company_id'),)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey('companies.id'), index=True)
    role: Mapped[str] = mapped_column(String(40), default='viewer')
    permissions: Mapped[list] = mapped_column(JSON, default=list)

class Challenge(Identity, Base):
    __tablename__ = 'auth_challenges'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    purpose: Mapped[str] = mapped_column(String(20))
    digest: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    used: Mapped[bool] = mapped_column(Boolean, default=False)

class TenantRecord(Identity):
    company_id: Mapped[int] = mapped_column(ForeignKey('companies.id'), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class Customer(TenantRecord, Base):
    __tablename__ = 'customers'
    name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(254), default='')
    organization: Mapped[str] = mapped_column(String(160), default='')
    status: Mapped[str] = mapped_column(String(40), default='Lead')
    notes: Mapped[str] = mapped_column(Text, default='')

class Project(TenantRecord, Base):
    __tablename__ = 'projects'
    name: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(40), default='In progress')
    notes: Mapped[str] = mapped_column(Text, default='')

class Task(TenantRecord, Base):
    __tablename__ = 'tasks'
    name: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(40), default='To do')
    priority: Mapped[str] = mapped_column(String(20), default='Medium')
    due_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey('customers.id'), nullable=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey('projects.id'), nullable=True)
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default='')

class Activity(Identity, Base):
    __tablename__ = 'activities'
    company_id: Mapped[int] = mapped_column(ForeignKey('companies.id'), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    action: Mapped[str] = mapped_column(String(100))
    entity: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(160))
    before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSON, nullable=True)

class Invitation(Identity, Base):
    __tablename__ = 'invitations'
    company_id: Mapped[int] = mapped_column(ForeignKey('companies.id'), index=True)
    email: Mapped[str] = mapped_column(String(254))
    role: Mapped[str] = mapped_column(String(40))
    digest: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
