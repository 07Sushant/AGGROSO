"""Projects: one migration workspace each, with an immutable source snapshot."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain.dry_run import SourceRow
from app.domain.hashing import payload_hash, source_checksum
from app.errors import AppError
from app.models import DryRun, MigrationRun, PlanVersion, Project, SourceRecord, User
from app.security import CurrentUser
from app.services import audit, inputs


def create_project(db: Session, user: CurrentUser, name: str, dataset_key: str) -> Project:
    ds = inputs.dataset(dataset_key)
    records = ds["records"]
    limit = get_settings().max_source_records
    if len(records) > limit:
        raise AppError(
            "LIMIT_EXCEEDED",
            f"This dataset has {len(records)} records; the maximum is {limit}.",
            details={"record_count": len(records), "max_source_records": limit},
        )
    key_field = inputs.source_schema()["primary_key"]
    hashes = [payload_hash(r) for r in records]
    project = Project(
        name=name.strip(),
        dataset_key=dataset_key,
        source_checksum=source_checksum(hashes),
        record_count=len(records),
        created_by=user.id,
    )
    db.add(project)
    db.flush()
    db.execute(
        insert(SourceRecord),
        [
            {
                "project_id": project.id,
                "row_number": i + 1,
                "source_key": (str(r.get(key_field)) if r.get(key_field) is not None else None),
                "payload": r,
                "payload_hash": h,
            }
            for i, (r, h) in enumerate(zip(records, hashes, strict=True))
        ],
    )
    audit.record(db, project_id=project.id, entity_type="project", entity_id=project.id,
                 action="project.created", actor_id=user.id,
                 details={"dataset_key": dataset_key, "record_count": len(records),
                          "source_checksum": project.source_checksum})
    db.commit()
    return project


def get_project(db: Session, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise AppError("NOT_FOUND", f"Project {project_id} was not found.")
    return project


def source_rows(db: Session, project_id: int) -> list[SourceRow]:
    rows = db.execute(
        select(SourceRecord.id, SourceRecord.row_number, SourceRecord.payload)
        .where(SourceRecord.project_id == project_id)
        .order_by(SourceRecord.row_number)
    ).all()
    return [SourceRow(r.id, r.row_number, r.payload) for r in rows]


def current_source_checksum(db: Session, project_id: int) -> str:
    hashes = db.scalars(
        select(SourceRecord.payload_hash)
        .where(SourceRecord.project_id == project_id)
        .order_by(SourceRecord.row_number)
    ).all()
    return source_checksum(hashes)


def project_out(db: Session, project: Project, *, detail: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": project.id,
        "name": project.name,
        "dataset_key": project.dataset_key,
        "record_count": project.record_count,
        "source_checksum": project.source_checksum,
        "created_by": project.created_by,
        "created_at": project.created_at,
    }
    if detail:
        latest = db.scalars(
            select(PlanVersion).where(PlanVersion.project_id == project.id)
            .order_by(PlanVersion.version_number.desc()).limit(1)
        ).first()
        approved = db.scalars(
            select(PlanVersion).where(PlanVersion.project_id == project.id,
                                      PlanVersion.status == "APPROVED").limit(1)
        ).first()
        active_run = db.scalars(
            select(MigrationRun).where(MigrationRun.project_id == project.id,
                                       MigrationRun.status != "ROLLED_BACK").limit(1)
        ).first()
        latest_dry = None
        if latest is not None:
            latest_dry = db.scalars(
                select(DryRun).where(DryRun.plan_version_id == latest.id)
                .order_by(DryRun.id.desc()).limit(1)
            ).first()
        out.update({
            "version_count": latest.version_number if latest else 0,
            "latest_version": (
                {"id": latest.id, "version_number": latest.version_number,
                 "status": latest.status} if latest else None
            ),
            "approved_version": (
                {"id": approved.id, "version_number": approved.version_number}
                if approved else None
            ),
            "latest_dry_run_id": latest_dry.id if latest_dry else None,
            "active_run": (
                {"id": active_run.id, "status": active_run.status} if active_run else None
            ),
        })
    return out


def list_projects(db: Session) -> list[dict[str, Any]]:
    rows = db.execute(
        select(Project, User.username)
        .join(User, User.id == Project.created_by)
        .order_by(Project.id.desc())
    ).all()
    return [{**project_out(db, p), "created_by_username": username} for p, username in rows]


def source_records_page(
    db: Session, project_id: int, limit: int, offset: int
) -> dict[str, Any]:
    total = db.scalar(
        select(func.count()).select_from(SourceRecord).where(SourceRecord.project_id == project_id)
    )
    rows = db.scalars(
        select(SourceRecord).where(SourceRecord.project_id == project_id)
        .order_by(SourceRecord.row_number).limit(limit).offset(offset)
    ).all()
    return {
        "total": total or 0,
        "items": [
            {"id": r.id, "row_number": r.row_number, "source_key": r.source_key,
             "payload": r.payload}
            for r in rows
        ],
    }
