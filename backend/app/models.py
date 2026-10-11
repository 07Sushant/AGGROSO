"""ORM models for every table in the data model (spec §4.4).

Dialect rules: JSON columns are JSONB on PostgreSQL and JSON elsewhere; the partial unique index
carries both ``postgresql_where`` and ``sqlite_where``. The append-only trigger on
``audit_events`` lives in the Alembic migration (PostgreSQL only).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

JSONType = JSON().with_variant(JSONB(), "postgresql")

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _in(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


ROLES = ("operator", "approver")
PLAN_STATUSES = ("DRAFT", "APPROVED", "REJECTED", "SUPERSEDED")
AUTHOR_TYPES = ("agent", "human")
APPROVAL_DECISIONS = ("APPROVED", "REJECTED", "REVOKED")
RECORD_OUTCOMES = ("ACCEPTED", "REJECTED")
RUN_STATUSES = ("RUNNING", "COMPLETED", "FAILED", "ROLLING_BACK", "ROLLED_BACK")
ATTEMPT_KINDS = ("EXECUTE", "RETRY")
ATTEMPT_STATUSES = ("RUNNING", "COMPLETED", "FAILED")
RESULT_OUTCOMES = ("INSERTED", "SKIPPED_EXISTING", "QUARANTINED")
ROLLBACK_STATUSES = ("COMPLETED", "FAILED")
CUSTOMER_STATUSES = ("active", "inactive", "suspended")
ACCOUNT_TIERS = ("standard", "gold")
AGENT_RUN_KINDS = ("propose", "revise")
AGENT_RUN_STATUSES = ("QUEUED", "RUNNING", "SUCCEEDED", "FAILED")
ENGINES = ("primary", "backup", "mock")
AGENT_STEP_KINDS = ("llm_call", "tool_call", "validation", "fallback")
SCHEMA_IMPORT_STATUSES = ("EXTRACTING", "PROPOSED", "APPROVED", "REJECTED", "FAILED")


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {dict[str, Any]: JSONType, list[Any]: JSONType}


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint(_in("role", ROLES), name="role"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    dataset_key: Mapped[str] = mapped_column(String(64))
    source_checksum: Mapped[str] = mapped_column(String(64))
    record_count: Mapped[int] = mapped_column(Integer)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SourceRecord(Base):
    __tablename__ = "source_records"
    __table_args__ = (UniqueConstraint("project_id", "row_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    row_number: Mapped[int] = mapped_column(Integer)
    source_key: Mapped[str | None] = mapped_column(String(200))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType)
    payload_hash: Mapped[str] = mapped_column(String(64))


class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint(_in("kind", AGENT_RUN_KINDS), name="kind"),
        CheckConstraint(_in("status", AGENT_RUN_STATUSES), name="status"),
        CheckConstraint(f"engine IS NULL OR {_in('engine', ENGINES)}", name="engine"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    base_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("plan_versions.id", use_alter=True)
    )
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="QUEUED")
    mode: Mapped[str | None] = mapped_column(String(20))
    engine: Mapped[str | None] = mapped_column(String(20))
    model_id: Mapped[str | None] = mapped_column(String(120))  # internal only, never serialised
    steps: Mapped[int] = mapped_column(Integer, default=0)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    fell_back: Mapped[bool] = mapped_column(Boolean, default=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    result_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("plan_versions.id", use_alter=True)
    )
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PlanVersion(Base):
    __tablename__ = "plan_versions"
    __table_args__ = (
        UniqueConstraint("project_id", "version_number"),
        CheckConstraint(_in("author_type", AUTHOR_TYPES), name="author_type"),
        CheckConstraint(_in("status", PLAN_STATUSES), name="status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    parent_version_id: Mapped[int | None] = mapped_column(ForeignKey("plan_versions.id"))
    author_type: Mapped[str] = mapped_column(String(10))
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    plan: Mapped[dict[str, Any]] = mapped_column(JSONType)
    content_hash: Mapped[str] = mapped_column(String(64))
    change_note: Mapped[str | None] = mapped_column(Text)
    agent_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ClarificationAnswer(Base):
    __tablename__ = "clarification_answers"
    __table_args__ = (UniqueConstraint("plan_version_id", "question_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_version_id: Mapped[int] = mapped_column(ForeignKey("plan_versions.id"), index=True)
    question_id: Mapped[str] = mapped_column(String(64))
    answer: Mapped[str] = mapped_column(Text)
    answered_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    answered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RiskAcknowledgement(Base):
    __tablename__ = "risk_acknowledgements"
    __table_args__ = (UniqueConstraint("plan_version_id", "risk_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_version_id: Mapped[int] = mapped_column(ForeignKey("plan_versions.id"), index=True)
    risk_id: Mapped[str] = mapped_column(String(64))
    acknowledged_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    acknowledged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DryRun(Base):
    __tablename__ = "dry_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_version_id: Mapped[int] = mapped_column(ForeignKey("plan_versions.id"), index=True)
    source_checksum: Mapped[str] = mapped_column(String(64))
    source_count: Mapped[int] = mapped_column(Integer)
    transformed_count: Mapped[int] = mapped_column(Integer)
    accepted_count: Mapped[int] = mapped_column(Integer)
    rejected_count: Mapped[int] = mapped_column(Integer)
    result_hash: Mapped[str] = mapped_column(String(64))
    code_version: Mapped[str] = mapped_column(String(64))
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DryRunRecord(Base):
    __tablename__ = "dry_run_records"
    __table_args__ = (
        UniqueConstraint("dry_run_id", "source_record_id"),
        CheckConstraint(_in("outcome", RECORD_OUTCOMES), name="outcome"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dry_run_id: Mapped[int] = mapped_column(ForeignKey("dry_runs.id"), index=True)
    source_record_id: Mapped[int] = mapped_column(ForeignKey("source_records.id"))
    row_number: Mapped[int] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(String(20))
    transformed: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    row_hash: Mapped[str | None] = mapped_column(String(64))
    errors: Mapped[list[Any]] = mapped_column(JSONType, default=list)


class Approval(Base):
    __tablename__ = "approvals"
    __table_args__ = (CheckConstraint(_in("decision", APPROVAL_DECISIONS), name="decision"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_version_id: Mapped[int] = mapped_column(ForeignKey("plan_versions.id"), index=True)
    decision: Mapped[str] = mapped_column(String(20))
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    comment: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    dry_run_id: Mapped[int | None] = mapped_column(ForeignKey("dry_runs.id"))
    dry_run_result_hash: Mapped[str | None] = mapped_column(String(64))
    source_checksum: Mapped[str | None] = mapped_column(String(64))
    self_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MigrationRun(Base):
    __tablename__ = "migration_runs"
    __table_args__ = (
        CheckConstraint(_in("status", RUN_STATUSES), name="status"),
        # One active (non-rolled-back) run per project, enforced by the database.
        Index(
            "uq_migration_runs_one_active_per_project",
            "project_id",
            unique=True,
            postgresql_where=text("status <> 'ROLLED_BACK'"),
            sqlite_where=text("status <> 'ROLLED_BACK'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    plan_version_id: Mapped[int] = mapped_column(ForeignKey("plan_versions.id"))
    approval_id: Mapped[int] = mapped_column(ForeignKey("approvals.id"))
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="RUNNING")
    inserted: Mapped[int] = mapped_column(Integer, default=0)
    skipped_existing: Mapped[int] = mapped_column(Integer, default=0)
    quarantined: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RunAttempt(Base):
    __tablename__ = "run_attempts"
    __table_args__ = (
        UniqueConstraint("run_id", "attempt_number"),
        CheckConstraint(_in("kind", ATTEMPT_KINDS), name="kind"),
        CheckConstraint(_in("status", ATTEMPT_STATUSES), name="status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("migration_runs.id"), index=True)
    attempt_number: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), default="RUNNING")
    inserted: Mapped[int] = mapped_column(Integer, default=0)
    skipped_existing: Mapped[int] = mapped_column(Integer, default=0)
    quarantined: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RunRecordResult(Base):
    __tablename__ = "run_record_results"
    __table_args__ = (
        UniqueConstraint("run_id", "source_record_id"),
        CheckConstraint(_in("outcome", RESULT_OUTCOMES), name="outcome"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("migration_runs.id"), index=True)
    source_record_id: Mapped[int] = mapped_column(ForeignKey("source_records.id"))
    attempt_id: Mapped[int] = mapped_column(ForeignKey("run_attempts.id"))
    outcome: Mapped[str] = mapped_column(String(20))
    errors: Mapped[list[Any]] = mapped_column(JSONType, default=list)


class Rollback(Base):
    __tablename__ = "rollbacks"
    __table_args__ = (CheckConstraint(_in("status", ROLLBACK_STATUSES), name="status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("migration_runs.id"), index=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(Text)
    deleted_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="COMPLETED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TgtCustomer(Base):
    """The mock target store. Constraints are enforced by the database, not only by code."""

    __tablename__ = "tgt_customers"
    __table_args__ = (
        UniqueConstraint("project_id", "legacy_id"),
        UniqueConstraint("project_id", "email"),
        CheckConstraint(_in("status", CUSTOMER_STATUSES), name="status"),
        CheckConstraint(_in("account_tier", ACCOUNT_TIERS), name="account_tier"),
        CheckConstraint(
            "credit_limit_cents IS NULL OR credit_limit_cents >= 0", name="credit_limit_cents"
        ),
        CheckConstraint("length(country_code) = 2", name="country_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    legacy_id: Mapped[str] = mapped_column(String(64))
    first_name: Mapped[str] = mapped_column(String(120))
    last_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254))
    phone_e164: Mapped[str | None] = mapped_column(String(20))
    signup_date: Mapped[date] = mapped_column(Date)
    country_code: Mapped[str] = mapped_column(String(2))
    status: Mapped[str] = mapped_column(String(20))
    credit_limit_cents: Mapped[int | None] = mapped_column(Integer)
    marketing_opt_in: Mapped[bool] = mapped_column(Boolean, default=False)
    account_tier: Mapped[str] = mapped_column(String(20))
    migration_run_id: Mapped[int] = mapped_column(ForeignKey("migration_runs.id"), index=True)
    row_hash: Mapped[str] = mapped_column(String(64))
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AgentStep(Base):
    __tablename__ = "agent_steps"
    __table_args__ = (
        UniqueConstraint("agent_run_id", "step_no"),
        CheckConstraint(_in("kind", AGENT_STEP_KINDS), name="kind"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_run_id: Mapped[int] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    step_no: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(20))
    tool_name: Mapped[str | None] = mapped_column(String(64))
    args: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONType)  # capped at 8 KB by writer
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    engine: Mapped[str | None] = mapped_column(String(20))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEvent(Base):
    """Append-only. On PostgreSQL a trigger blocks UPDATE, DELETE and TRUNCATE."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), index=True)
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    request_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SchemaImport(Base):
    """Screenshot → schema proposal. The image itself is never stored, only its hash."""

    __tablename__ = "schema_imports"
    __table_args__ = (
        CheckConstraint(_in("status", SCHEMA_IMPORT_STATUSES), name="status"),
        CheckConstraint(f"engine IS NULL OR {_in('engine', ENGINES)}", name="engine"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), index=True)
    image_sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="PROPOSED")
    extracted: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    normalized: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    findings: Mapped[list[Any] | None] = mapped_column(JSONType)
    engine: Mapped[str | None] = mapped_column(String(20))
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
