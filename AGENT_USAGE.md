# AI agent usage

This file records how AI coding agents were used to build MigrateIQ, what they got wrong and how their output was checked.

## Tools used

- Kiro, using its workflow agents (Claude models) for planning, phased implementation, code review and documentation. Work was split into phases (setup and skeleton deploy, deterministic core, agent, frontend, deployment and docs), each run as a workflow step with its own status notes and commits.
- The application's own models, named openly: `qwen/qwen3.8-27b` on Groq (primary) and `gemini-3.5-flash-lite` through Gemini's OpenAI-compatible endpoint (backup). These run inside the product and are not coding tools. The UI shows only "Primary" and "Backup".

## Representative prompts

Paraphrased and shortened from the instructions given to the workflow agents.

1. "Build the deterministic core from the spec: plan contract and validator, record validation, a pure dry run with a result hash, state machines with compare-and-set transitions, a chunked idempotent executor and a read-only reconciler. The reference plan must reproduce 60/55/45/15 on `baseline_60`."
2. "Write the LLM gateway against two OpenAI-compatible base URLs with one client, failover from primary to backup, a circuit breaker and a cached health probe. Never send provider or model names to the browser, and add a test that proves it."
3. "The primary's free tier caps tokens per minute and full plans are being cut off. Make compact mode the default: the runner calls the read-only tools itself, forces `submit_plan`, and the model writes a compact plan that code expands. Keep validation and repairs strict."
4. "Run one live agent run against the deployed backend, record calls, tokens, duration and the eval scores, and report the dry-run counts of the resulting plan next to the reference plan."
5. "Scaffold the React workspace stepper with TanStack Query, loading, empty and error states for every view, accessible dialogs, and five Vitest tests."
6. "Write the README, AGENT_USAGE.md and ADRs from what is actually in the repository and the phase notes; name the models openly and state that the live numbers come from one run."

## What was delegated and what was reviewed by hand

Delegated to agents, then reviewed: the dataset generator and its expected counts, the transform registry and its tests, ORM models and the initial migration, API routes and DTOs, the frontend scaffolding and pages, the deploy script, and first drafts of the docs.

Designed and reviewed line by line: the approval gate and what it binds (plan hash, dry-run hash, source checksum), the three idempotency layers (idempotency key, `ON CONFLICT DO NOTHING` on unique keys, and the per-run result ledger written in the same transaction), the partial unique index for one active run per project, the failover policy and the gateway, the agent's tool allow-list, and the decision that the agent can only ever create a DRAFT.

## Agent mistakes and rejected suggestions

These are real incidents from this build.

1. Unapproved tool. A sample LLM snippet used as a starting point enabled a `google_search` tool. Rejected: the agent may use only the tools this application provides, so the allow-list is fixed and any other tool call is rejected and logged.
2. Structured output with images. Strict `json_schema` output combined with an image returned an object with empty fields on the primary model. Switched to `json_object` mode and validation with Pydantic.
3. Failover by replaying history. The first design continued a failed primary conversation on the backup. A probe showed the backup rejects replayed tool-call history that lacks its own thought signature (HTTP 400). Failover now restarts the run from scratch on the backup in compact mode and never replays the conversation.
4. Truncated plans. Free-tier tokens-per-minute caps cut off full plans written by the model. The compact plan format was introduced: the model writes a short JSON plan and code expands it into the full contract.
5. Invented keys. With reasoning turned off, the primary invented keys such as `source_fields_v2`. Fixed by making the tool schemas closed (`additionalProperties: false`) and making `source_fields` required.
6. Foreign transform params. The model put a `value` param into `map_values` and `to_boolean`. Params a transform does not accept are now stripped with a recorded warning, and required params are never invented by code; a missing required param stays a validation error.
7. Testing the wrong server. During a live test, a leftover dev server on port 8000 was running in mock mode and silently answered the requests. The rule now is to check `/api/health` and confirm the `ai` status before every live test.
8. Private files in a public ignore list. The first `.gitignore` named private planning files. Those patterns moved to `.git/info/exclude`, so no committed file names them.
9. Unsafe latency fix. To reduce `/api/health` latency against Neon, turning off the connection pool's reset-on-return was considered and rejected, because it is unsafe with PgBouncer in transaction mode.

## Verification

- Backend pytest suite (about 136 tests, SQLite plus the mock LLM locally; two Postgres-only tests run in CI) and 5 frontend Vitest tests.
- CI on GitHub Actions: ruff, Alembic upgrade and downgrade, pytest against `postgres:16`, and gitleaks.
- `scripts/probe_llm.py` for one live call per provider, and `scripts/eval_agent.py` to score a plan against the gold mapping.
- A health check of the AI status before each live run.
- Manual review of every server-side gate (approval, execute, retry, rollback) and of each agent incident above before the fix was accepted.
