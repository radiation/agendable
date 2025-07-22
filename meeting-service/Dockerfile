#################
# BUILDER STAGE #
#################
FROM python:3.13-slim AS builder
WORKDIR /app

RUN pip install --upgrade pip uv

COPY pyproject.toml uv.lock README.md ./
COPY common-lib/        common-lib/
COPY meeting-service/   meeting-service/
COPY user-service/      user-service/

WORKDIR /app
RUN uv sync \
      --no-install-package user-service \
      --no-dev \
        && uv pip install -e common-lib

###############
# FINAL IMAGE #
###############
FROM python:3.13-slim
WORKDIR /app/meeting-service

COPY --from=builder /app/.venv /app/.venv

COPY --from=builder /app/meeting-service/app ./app

ENV VIRTUAL_ENV=/app/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

ENV PYTHONPATH=/app/meeting-service

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
