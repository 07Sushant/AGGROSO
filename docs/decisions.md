# Architecture decisions

Short records of the main decisions. Each lists the context, the decision and the trade-off.

## ADR-01: One Postgres database for app data and the mock target

- Context: run results and target rows must commit together, or a crash between commits corrupts history.
- Decision: one Neon Postgres database; the mock target is the `tgt_customers` table, scoped by `project_id`.
- Trade-off: no physical separation between source, app and target, but no two-phase commit is needed and the target's constraints are enforced by the database.

## ADR-02: Approval bound to hashes

- Context: a human approves specific output, not a plan name.
- Decision: an approval stores the plan content hash, the dry-run id and result hash, and the source checksum. Execute checks them and compares row hashes chunk by chunk; any difference gives `DRIFT_DETECTED`.
- Trade-off: any edit or new dry run needs a fresh approval.

## ADR-03: `ON CONFLICT DO NOTHING` plus classification instead of aborting

- Context: one conflicting row should not block the rest of a run.
- Decision: chunked inserts with `ON CONFLICT DO NOTHING RETURNING`; rows that were not inserted are classified as `SKIPPED_EXISTING` or `QUARANTINED` with evidence, with a SAVEPOINT row-by-row fallback for other constraint errors.
- Trade-off: a run can finish with quarantined rows; reconciliation makes them visible.

## ADR-04: Partial unique index instead of application locks

- Context: two concurrent executes must not create two active runs.
- Decision: a partial unique index allows one non-rolled-back run per project, plus compare-and-set status updates.
- Trade-off: Postgres-specific; covered by a Postgres-only test in CI.

## ADR-05: Background agent runs with polling

- Context: agent runs take from seconds to minutes, longer on the backup.
- Decision: runs execute in a background thread; the UI polls the run and its steps about once a second while it is active.
- Trade-off: needs a single worker and a stale-run recovery at startup; simpler than WebSockets and works through proxies.

## ADR-06: One OpenAI-compatible gateway

- Context: two providers, and guardrails must stay visible.
- Decision: one `openai` SDK client pointed at two OpenAI-compatible base URLs, with provider extras passed per engine; no agent framework.
- Trade-off: provider-specific features are used only through `extra_body`; switching providers is an environment change.

## ADR-07: Failover restarts in compact mode

- Context: the backup rejects replayed tool-call history without its own thought signature, and free-tier token caps truncate long conversations.
- Decision: if the primary fails, the run restarts from scratch on the backup in compact mode. Compact mode is also the default: the runner calls the read-only tools, forces `submit_plan`, the model writes a compact plan that code expands, with up to 2 repair rounds. A circuit breaker and cached probe skip a provider that is down.
- Trade-off: the backup repeats work already done, and a failover run is slower (107 s in the one recorded live run).

## ADR-08: Demo JWT auth with two roles

- Context: "who approved" must mean something, and destructive actions should not be anonymous.
- Decision: two seeded accounts, `operator` and `approver`, with bcrypt hashes and HS256 JWTs (8 hours). Self-approval is allowed but flagged.
- Trade-off: shared demo credentials, not real user management.

## ADR-09: SQLite tests locally, Postgres in CI

- Context: no Docker on the development machine, but dialect behaviour matters.
- Decision: the suite runs on SQLite with a mock LLM locally; CI runs it on `postgres:16`, including the partial index and audit-trigger tests.
- Trade-off: two Postgres-only tests are skipped locally.

## ADR-10: Hugging Face Space instead of Render

- Context: the backend needs background jobs and should not sleep often.
- Decision: a Docker Space on the free CPU tier, single uvicorn worker on port 7860, migrations run with retries at startup.
- Trade-off: the Space sleeps after about 48 hours idle and is far from the Neon region, which adds round-trip latency.
