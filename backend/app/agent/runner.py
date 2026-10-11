"""Agent runner (spec §7.1, §7.3). Runs inside a background job, never in a request.

Full mode (primary): the model inspects through the tools itself, at most ``AGENT_MAX_STEPS``
LLM turns and ``AGENT_WALL_S`` seconds. Compact mode (backup, or ``AGENT_MODE=compact``): the
runner calls the same read-only tools on the model's behalf, sends the results in one
untrusted-data block, and forces ``submit_plan`` (1 repair round at most).

If the primary fails, the run restarts from scratch on the backup in compact mode; the
primary's conversation is never replayed. Within one engine, assistant messages are echoed
exactly as returned (``model_dump(exclude_none=True)``).

Every LLM call, tool call, validation and fallback is written to ``agent_steps``.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.agent import prompts
from app.agent.gateway import EngineFailure, Gateway, LLMResult, ToolCall
from app.agent.plan_validator import validate_plan
from app.agent.tools import (
    ALLOWED_TOOLS,
    SUBMIT_PLAN,
    ToolContext,
    ToolError,
    dispatch,
    tool_specs,
    wrap_result,
)
from app.config import Settings
from app.logging import get_logger, strip_provider_details
from app.models import AgentRun, AgentStep
from app.schemas.plan import normalize_plan
from app.services import inputs

log = get_logger("ai")

STEP_CAP_BYTES = 8 * 1024
MAX_ERRORS_TO_MODEL = 30
FORCE_SUBMIT = {"type": "function", "function": {"name": SUBMIT_PLAN}}


class AgentFailure(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


@dataclass
class RunnerOutcome:
    plan: dict[str, Any]
    engine: str
    mode: str
    fell_back: bool


def cap(value: Any) -> Any:
    """Keep a step payload under 8 KB (the rest stays out of the database)."""
    text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text.encode("utf-8")) <= STEP_CAP_BYTES:
        return value
    return {"truncated": True,
            "preview": text.encode("utf-8")[:STEP_CAP_BYTES - 256].decode("utf-8", "ignore")}


class StepRecorder:
    """Writes one ``agent_steps`` row per event and commits, so the UI can poll a live trace."""

    def __init__(self, db: Session, run: AgentRun) -> None:
        self.db, self.run = db, run
        self.step_no = run.steps or 0

    def add(self, kind: str, *, engine: str | None, tool_name: str | None = None,
            args: Any = None, result: Any = None, ok: bool = True, latency_ms: int = 0,
            tokens_in: int = 0, tokens_out: int = 0, error: str | None = None) -> None:
        self.step_no += 1
        self.db.add(AgentStep(
            agent_run_id=self.run.id, step_no=self.step_no, kind=kind, tool_name=tool_name,
            args=cap(args) if args is not None else None,
            result=cap(result) if result is not None else None,
            ok=ok, latency_ms=latency_ms, tokens_in=tokens_in, tokens_out=tokens_out,
            engine=engine, error=error,
        ))
        self.run.steps = self.step_no
        self.run.tokens_in = (self.run.tokens_in or 0) + tokens_in
        self.run.tokens_out = (self.run.tokens_out or 0) + tokens_out
        self.db.commit()


class AgentRunner:
    def __init__(self, db: Session, run: AgentRun, gateway: Gateway, settings: Settings, *,
                 revision: str | None = None) -> None:
        self.db, self.run, self.gateway, self.settings = db, run, gateway, settings
        self.revision = revision
        self.ctx = ToolContext(db, run.project_id)
        self.rec = StepRecorder(db, run)
        self.source = inputs.source_schema()
        self.target = inputs.target_schema()
        self._deadline = 0.0
        self._repairs = 0

    # ------------------------------------------------------------------ orchestration
    def execute(self) -> RunnerOutcome:
        skip = self.gateway.primary_skip_reason()
        if skip is None:
            mode = "compact" if self.settings.agent_mode == "compact" else "full"
            try:
                return self._run("primary", mode, fell_back=False)
            except EngineFailure as exc:
                reason = exc.reason
        else:
            reason = skip
        if not self.gateway.configured("backup"):
            raise AgentFailure("LLM_UNAVAILABLE", "AI services are unavailable right now. You "
                               "can still load the reference plan or edit a plan manually.",
                               {"primary": reason, "backup": "not_configured"})
        self.rec.add("fallback", engine="backup", ok=True,
                     result={"from": "primary", "to": "backup", "reason": reason,
                             "mode": "compact",
                             "message": f"restarted on backup ({reason})"})
        log.warning("llm.fallback", from_engine="primary", to_engine="backup", reason=reason,
                    agent_run_id=self.run.id)
        try:
            return self._run("backup", "compact", fell_back=True)
        except EngineFailure as exc:
            raise AgentFailure("LLM_UNAVAILABLE", "AI services are unavailable right now. You "
                               "can still load the reference plan or edit a plan manually.",
                               {"primary": reason, "backup": exc.reason}) from exc

    def _run(self, alias: str, mode: str, *, fell_back: bool) -> RunnerOutcome:
        self.run.engine, self.run.mode, self.run.fell_back = alias, mode, fell_back
        self.run.model_id = "mock" if self.gateway.mock else self.gateway.engine(alias).model
        self.db.commit()
        self._repairs = 0
        wall = self.settings.agent_wall_s if mode == "full" else self.settings.agent_compact_wall_s
        self._deadline = time.monotonic() + wall
        plan = self._full(alias) if mode == "full" else self._compact(alias)
        return RunnerOutcome(plan=plan, engine=alias, mode=mode, fell_back=fell_back)

    # ------------------------------------------------------------------ modes
    def _task(self) -> str:
        source, target = self.source["entity"], self.target["entity"]
        if self.revision:
            return prompts.revise_task(source, target, self.revision)
        return prompts.propose_task(source, target)

    def _full(self, alias: str) -> dict[str, Any]:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": prompts.SYSTEM_PROMPT},
            {"role": "user", "content": self._task()},
        ]
        tools = tool_specs()
        max_turns = self.settings.agent_max_steps
        for turn in range(1, max_turns + 1):
            left = max_turns - turn  # turns after this one
            choice: Any = FORCE_SUBMIT if left == 0 else "auto"
            res = self._llm(alias, messages, tools, choice)
            messages.append(res.assistant_message)
            if not res.tool_calls:
                messages.append({"role": "user", "content": prompts.NUDGE_USE_TOOLS})
                continue
            for tc in res.tool_calls:
                content, plan = self._handle(alias, tc, self.settings.agent_max_repairs)
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": content})
                if plan is not None:
                    return plan
            if left == 2:
                messages.append({"role": "user", "content": prompts.turns_left_notice(left)})
        raise AgentFailure("MAX_STEPS", f"The agent did not submit a valid plan within "
                           f"{max_turns} steps.")

    def _compact(self, alias: str) -> dict[str, Any]:
        calls: list[tuple[str, dict[str, Any]]] = [("get_source_schema", {}),
                                                   ("get_target_schema", {})]
        calls += [("profile_source_field", {"field": f["name"]}) for f in self.source["fields"]]
        calls += [("list_transformations", {}), ("sample_source_records", {"limit": 10})]
        blocks = []
        for name, args in calls:
            started = time.perf_counter()
            result = dispatch(self.ctx, name, args)
            self.rec.add("tool_call", engine=alias, tool_name=name, args=args,
                         result={"invoked_by": "runner", "data": result},
                         latency_ms=int((time.perf_counter() - started) * 1000))
            log.info("tool.call", tool=name, invoked_by="runner", ok=True)
            blocks.append(f"## {name} {json.dumps(args)}\n{wrap_result(name, result)}")
        task = prompts.compact_task(self.source["entity"], self.target["entity"],
                                    "\n\n".join(blocks), self.revision)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": prompts.SYSTEM_PROMPT},
            {"role": "user", "content": task},
        ]
        tools = tool_specs([SUBMIT_PLAN])
        for _round in range(2):  # the first submission and at most one repair
            res = self._llm(alias, messages, tools, FORCE_SUBMIT)
            messages.append(res.assistant_message)
            if not res.tool_calls:
                messages.append({"role": "user", "content": "Call submit_plan now."})
                continue
            for tc in res.tool_calls:
                content, plan = self._handle(alias, tc, 1)
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": content})
                if plan is not None:
                    return plan
        raise AgentFailure("PLAN_INVALID", "The agent did not produce a valid plan.")

    # ------------------------------------------------------------------ one LLM call
    def _remaining(self) -> float:
        return self._deadline - time.monotonic()

    def _llm(self, alias: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]],
             tool_choice: Any) -> LLMResult:
        remaining = self._remaining()
        if remaining <= 1:
            raise AgentFailure("LLM_TIMEOUT", "The agent ran out of time before finishing.")
        engine_timeout = self.gateway.timeout_for(alias)
        timeout = min(engine_timeout, remaining)
        max_tokens = (self.settings.primary_max_completion_tokens if alias == "primary"
                      else self.settings.backup_max_completion_tokens)
        args = {"messages": len(messages), "tool_choice": tool_choice if isinstance(
                tool_choice, str) else SUBMIT_PLAN, "prompt_version": prompts.PROMPT_VERSION}
        try:
            res = self.gateway.call(alias, messages=messages, tools=tools,
                                    tool_choice=tool_choice, max_completion_tokens=max_tokens,
                                    timeout_s=timeout, prompt_version=prompts.PROMPT_VERSION)
        except EngineFailure as exc:
            self.rec.add("llm_call", engine=alias, args=args, ok=False, error=exc.reason,
                         latency_ms=exc.latency_ms)
            if exc.reason == "timeout" and timeout < engine_timeout:
                raise AgentFailure("LLM_TIMEOUT", "The agent ran out of time before "
                                   "finishing.") from exc
            raise
        self.rec.add(
            "llm_call", engine=alias, args=args, latency_ms=res.latency_ms,
            tokens_in=res.tokens_in, tokens_out=res.tokens_out,
            result=strip_provider_details({
                "finish_reason": res.finish_reason,
                "content": (res.content or "")[:2000] or None,
                "tool_calls": [{"name": tc.name, "arguments": tc.arguments}
                               for tc in res.tool_calls],
            }),
        )
        return res

    # ------------------------------------------------------------------ one tool call
    def _handle(self, alias: str, tc: ToolCall, max_repairs: int
                ) -> tuple[str, dict[str, Any] | None]:
        """Returns (tool message content, accepted plan or None)."""
        if tc.name not in ALLOWED_TOOLS:
            err = ToolError("UNKNOWN_TOOL", f"'{tc.name}' is not an available tool.",
                            {"available_tools": sorted(ALLOWED_TOOLS)}).to_result()
            self.rec.add("tool_call", engine=alias, tool_name=tc.name[:64], args=tc.arguments,
                         result=err, ok=False, error="UNKNOWN_TOOL")
            log.warning("tool.rejected", tool=tc.name[:64], reason="not_allowed")
            return json.dumps(err), None
        if tc.name == SUBMIT_PLAN:
            return self._submit(alias, tc, max_repairs)
        started = time.perf_counter()
        try:
            result = dispatch(self.ctx, tc.name, tc.arguments)
        except ToolError as exc:
            err = exc.to_result()
            self.rec.add("tool_call", engine=alias, tool_name=tc.name, args=tc.arguments,
                         result=err, ok=False, error=exc.code,
                         latency_ms=int((time.perf_counter() - started) * 1000))
            log.warning("tool.rejected", tool=tc.name, reason=exc.code)
            return json.dumps(err), None
        latency_ms = int((time.perf_counter() - started) * 1000)
        self.rec.add("tool_call", engine=alias, tool_name=tc.name, args=tc.arguments,
                     result=result, latency_ms=latency_ms)
        log.info("tool.call", tool=tc.name, ok=True, latency_ms=latency_ms)
        return wrap_result(tc.name, result), None

    def _submit(self, alias: str, tc: ToolCall, max_repairs: int
                ) -> tuple[str, dict[str, Any] | None]:
        validation = validate_plan(tc.arguments)
        if validation.valid and validation.plan is not None:
            self.rec.add("validation", engine=alias, tool_name=SUBMIT_PLAN,
                         result={"accepted": True, "warnings": validation.warnings})
            return json.dumps({"accepted": True}), normalize_plan(validation.plan)
        self._repairs += 1
        errors = validation.errors
        self.rec.add("validation", engine=alias, tool_name=SUBMIT_PLAN, ok=False,
                     error="PLAN_INVALID", args=tc.arguments,
                     result={"accepted": False, "repair_round": self._repairs, "errors": errors})
        log.info("plan.validation_failed", errors=len(errors), repair_round=self._repairs,
                 codes=sorted({e["code"] for e in errors}))
        if self._repairs > max_repairs:
            raise AgentFailure("PLAN_INVALID", f"The plan was still invalid after {max_repairs} "
                               f"repair round(s); see the trace for the validator errors.",
                               {"errors": errors[:MAX_ERRORS_TO_MODEL]})
        return json.dumps({
            "accepted": False,
            "errors": errors[:MAX_ERRORS_TO_MODEL],
            "repairs_left": max_repairs - self._repairs,
            "instruction": "Fix these errors and call submit_plan again with the full plan.",
        }), None
