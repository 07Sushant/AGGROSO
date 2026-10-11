#!/bin/sh
# Container entrypoint: apply migrations (Neon may be cold, so retry with backoff), then start
# a single uvicorn worker. One worker on purpose: the AI probe cache, circuit breaker and log
# ring buffer live in process memory.
set -u

attempt=1
for delay in 2 4 8 16 0; do
  if alembic upgrade head; then
    echo '{"event": "startup.migrations_applied", "logger": "app", "level": "info"}'
    break
  fi
  if [ "$delay" -eq 0 ]; then
    # Start anyway: /api/health will report the database problem instead of a crash loop.
    echo '{"event": "startup.migrations_failed", "logger": "app", "level": "error"}'
    break
  fi
  echo "{\"event\": \"startup.migrations_retry\", \"attempt\": $attempt, \"delay_s\": $delay, \"logger\": \"app\", \"level\": \"warning\"}"
  sleep "$delay"
  attempt=$((attempt + 1))
done

exec uvicorn app.main:app --host 0.0.0.0 --port 7860 --workers 1 \
  --proxy-headers --forwarded-allow-ips="*" --no-access-log
