"""Agent runs: rate limits, queueing, the background job and the public trace."""

from __future__ import annotations

import math
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.agent.gateway import get_gateway
from app.agent.runner import AgentFailure, AgentRunner
from app.config import get_settings
from app.db import session_factory
from app.errors import AppError
from app.logging import get_logger, strip_provider_details
from app.models import AgentRun, AgentStep, Project, utcnow
from app.security import CurrentUser
from app.services import audit, jobs, plans

log = get_logger("ai")
WINDOW = timedelta(hours=1)


def _aware(ts: datetime) -> datetime:
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def check_window(created: list[datetime], limit: int, scope: str) -> None:
    """429 RATE_LIMITED when ``limit`` events already happened in the last hour."""
    now = utcnow()
    recent = sorted(_aware(t) for t in created if _aware(t) > now - WINDOW)
    if len(recent) >= limit:
        oldest = recent[len(recent) - limit]
        retry_after = max(1, math.ceil((oldest + WINDOW - now).total_seconds()))
        raise AppError("RATE_LIMITED", f"Too many requests ({scope}: {limit} per hour). Try "
                       f"again in {retry_after} s.",
                       details={"scope": scope, "limit": limit, "retry_after": retry_after},
                       headers={"Retry-After": str(retry_after)})


def _check_limits(db: Session, project_id: int) -> None:
    settings = get_settings()
    active = db.scalars(select(AgentRun.id).where(
        AgentRun.project_id == project_id, AgentRun.status.in_(("QUEUED", "RUNNING")))).first()
    if active is not None:
        raise AppError("RATE_LIMITED", f"Agent run {active} is still in progress for this "
                       "project.", details={"scope": "active_run", "agent_run_id": active,
                                            "retry_after": 10},
                       headers={"Retry-After": "10"})
    per_project = settings.agent_runs_per_project_hour
    check_window(list(db.scalars(
        select(AgentRun.created_at).where(AgentRun.project_id == project_id)
        .order_by(AgentRun.id.desc()).limit(per_project)).all()), per_project, "project")
    cap = settings.agent_runs_global_hour
    check_window(list(db.scalars(
        select(AgentRun.created_at).order_by(AgentRun.id.desc()).limit(cap)).all()), cap,
        "global")


def get_agent_run(db: Session, run_id: int) -> AgentRun:
    run = db.get(AgentRun, run_id)
    if run is None:
        raise AppError("NOT_FOUND", f"Agent run {run_id} was not found.")
    return run


def create_agent_run(db: Session, user: CurrentUser, project: Project,
                     base_version_id: int | None, use_answers: bool) -> AgentRun:
    if base_version_id is not None:
        base = plans.get_version(db, base_version_id)
        if base.project_id != project.id:
            raise AppError("VALIDATION_ERROR", "The base version belongs to another project.")
    _check_limits(db, project.id)
    kind = "revise" if base_version_id is not None else "propose"
    run = AgentRun(project_id=project.id, base_version_id=base_version_id, kind=kind,
                   status="QUEUED", created_by=user.id)
    db.add(run)
    db.flush()
    audit.record(db, project_id=project.id, entity_type="agent_run", entity_id=run.id,
                 action="agent.run.queued", actor_id=user.id,
                 details={"kind": kind, "base_version_id": base_version_id,
                          "use_answers": use_answers})
    db.commit()
    jobs.submit(run_agent_job, run.id, use_answers)
    db.refresh(run)
    return run


def _revision_text(db: Session, run: AgentRun, use_answers: bool) -> str | None:
    if run.base_version_id is None:
        return None
    from app.agent import prompts

    base = plans.get_version(db, run.base_version_id)
    answers = plans.answers_for(db, base.id) if use_answers else {}
    questions = {q["id"]: q["question"] for q in base.plan.get("clarification_questions", [])}
    items = [{"question_id": qid, "question": questions.get(qid, ""), "answer": answer}
             for qid, answer in sorted(answers.items())]
    return prompts.revision_block(base.plan, items, base.change_note)


def _fail(run_id: int, code: str, message: str, started: float) -> None:
    with session_factory()() as db:
        run = db.get(AgentRun, run_id)
        if run is None:
            return
        run.status, run.error_code, run.error_message = "FAILED", code, message
        run.finished_at = utcnow()
        run.latency_ms = int((time.perf_counter() - started) * 1000)
        audit.record(db, project_id=run.project_id, entity_type="agent_run", entity_id=run.id,
                     action="agent.run.failed", actor_id=run.created_by,
                     details={"error_code": code, "engine": run.engine,
                              "fell_back": run.fell_back})
        db.commit()
    log.warning("agent.run.failed", agent_run_id=run_id, error_code=code)


def run_agent_job(run_id: int, use_answers: bool = True) -> None:
    """The background job. It always leaves the run SUCCEEDED or FAILED."""
    settings = get_settings()
    started = time.perf_counter()
    try:
        with session_factory()() as db:
            claimed = db.execute(
                update(AgentRun).where(AgentRun.id == run_id, AgentRun.status == "QUEUED")
                .values(status="RUNNING", started_at=utcnow())
            ).rowcount
            db.commit()
            if claimed != 1:
                return
            run = get_agent_run(db, run_id)
            log.info("agent.run.started", agent_run_id=run.id, kind=run.kind)
            runner = AgentRunner(db, run, get_gateway(settings), settings,
                                 revision=_revision_text(db, run, use_answers))
            outcome = runner.execute()
            project = db.get(Project, run.project_id)
            assert project is not None
            note = (f"Agent revision of the base version using the reviewer's answers "
                    f"(agent run {run.id})" if run.kind == "revise"
                    else f"Agent proposal (agent run {run.id})")
            version = plans.create_version(
                db, project=project, raw_plan=outcome.plan, author_type="agent",
                author_id=None, change_note=note, parent_version_id=run.base_version_id,
                agent_run_id=run.id, commit=False)
            run.status, run.result_version_id = "SUCCEEDED", version.id
            run.finished_at = utcnow()
            run.latency_ms = int((time.perf_counter() - started) * 1000)
            audit.record(db, project_id=run.project_id, entity_type="agent_run",
                         entity_id=run.id, action="agent.run.completed",
                         actor_id=run.created_by,
                         details={"engine": run.engine, "mode": run.mode,
                                  "fell_back": run.fell_back, "steps": run.steps,
                                  "result_version_id": version.id})
            db.commit()
            log.info("agent.run.completed", agent_run_id=run.id, engine=run.engine,
                     mode=run.mode, fell_back=run.fell_back, steps=run.steps,
                     latency_ms=run.latency_ms, tokens_in=run.tokens_in,
                     tokens_out=run.tokens_out)
    except AgentFailure as exc:
        _fail(run_id, exc.code, exc.message, started)
    except AppError as exc:
        _fail(run_id, exc.code, exc.message, started)
    except Exception:  # noqa: BLE001 - a job must never stay RUNNING; details go to the log
        log.exception("agent.run.crashed", agent_run_id=run_id)
        _fail(run_id, "INTERNAL", "The agent run failed unexpectedly.", started)


def step_out(s: AgentStep) -> dict[str, Any]:
    result = s.result
    invoked_by = result.get("invoked_by", "model") if isinstance(result, dict) else "model"
    return {
        "step_no": s.step_no, "kind": s.kind, "tool_name": s.tool_name, "args": s.args,
        "result": result, "ok": s.ok, "latency_ms": s.latency_ms, "tokens_in": s.tokens_in,
        "tokens_out": s.tokens_out, "engine": s.engine, "error": s.error,
        "invoked_by": invoked_by, "created_at": s.created_at,
    }


def agent_run_out(db: Session, run: AgentRun, *, since_step: int = 0) -> dict[str, Any]:
    """Public shape: engine aliases only (``model_id`` is never serialised)."""
    steps = db.scalars(select(AgentStep).where(AgentStep.agent_run_id == run.id,
                                               AgentStep.step_no > since_step)
                       .order_by(AgentStep.step_no)).all()
    out = {
        "id": run.id, "project_id": run.project_id, "kind": run.kind, "status": run.status,
        "mode": run.mode, "engine": run.engine, "fell_back": run.fell_back,
        "llm_mode": "mock" if get_settings().llm_mode == "mock" else "live",
        "steps": run.steps, "tokens_in": run.tokens_in, "tokens_out": run.tokens_out,
        "latency_ms": run.latency_ms, "error_code": run.error_code,
        "error_message": run.error_message, "base_version_id": run.base_version_id,
        "result_version_id": run.result_version_id, "created_by": run.created_by,
        "created_at": run.created_at, "started_at": run.started_at,
        "finished_at": run.finished_at,
        "trace": [step_out(s) for s in steps],
    }
    return strip_provider_details(out)
