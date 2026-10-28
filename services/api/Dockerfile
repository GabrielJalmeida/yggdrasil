FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY pyproject.toml requirements.txt ./
COPY app ./app
COPY scripts ./scripts
COPY evaluation ./evaluation
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
RUN pip install --upgrade pip && pip install .
RUN useradd --system --uid 10001 --create-home yggdrasil && mkdir -p /app/data && chown -R yggdrasil:yggdrasil /app
USER yggdrasil
EXPOSE 8000
CMD ["sh", "-c", "python -m alembic upgrade head && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"]
