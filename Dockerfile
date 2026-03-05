FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Keep the virtualenv outside /app so docker-compose bind mounts don't clobber it.
RUN python -m venv /opt/venv
ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

RUN groupadd --system agendable \
    && useradd --system --gid agendable --create-home --home-dir /home/agendable agendable

COPY pyproject.toml uv.lock README.md /app/
COPY src /app/src
COPY alembic.ini /app/alembic.ini
COPY migrations /app/migrations

RUN pip install --upgrade pip \
    && pip install uv \
    && uv sync --active --frozen --no-dev

RUN chown -R agendable:agendable /app /opt/venv

USER agendable

EXPOSE 8000

CMD ["uvicorn", "agendable.app:app", "--host", "0.0.0.0", "--port", "8000"]
