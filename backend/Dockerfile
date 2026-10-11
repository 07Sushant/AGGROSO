# Hugging Face Space (Docker SDK). HF runs containers as uid 1000 and probes port 7860.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    APP_ENV=production

RUN useradd --create-home --uid 1000 user
WORKDIR /home/user/app

COPY --chown=user:user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=user:user . .

USER user
EXPOSE 7860

# start.sh: alembic upgrade head with retries, then `uvicorn --workers 1` on :7860.
CMD ["sh", "start.sh"]
