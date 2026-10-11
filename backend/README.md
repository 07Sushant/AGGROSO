---
title: MigrateIQ API
colorFrom: indigo
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

# MigrateIQ API

Backend for MigrateIQ, an agentic data migration planner and reconciliation workbench.
FastAPI + SQLAlchemy 2 + Alembic on PostgreSQL (Neon). This folder is deployed as-is to a
Hugging Face Docker Space.

- Health: `GET /api/health/live` (no DB access), `GET /api/health` (DB, AI status, version)
- OpenAPI docs: `/api/docs`

## Runtime notes

- `start.sh` runs `alembic upgrade head` with retries (2/4/8/16 s backoff, Neon may be cold),
  then starts **one** uvicorn worker on port 7860. A single worker is deliberate: the AI probe
  cache, the circuit breaker and the log ring buffer live in process memory.
- Secrets (Space secrets): `GROQ_API_KEY`, `GEMINI_API_KEY`, `DATABASE_URL`.
  Everything else has defaults in `app/config.py`.
- The deploy script writes a `GIT_SHA` file that `/api/health` reports as `version`.

## Local development

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
pytest
```
