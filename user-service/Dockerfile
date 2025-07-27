#################
# BUILDER STAGE #
#################
FROM python:3.13-slim AS builder
WORKDIR /app

# Install uv
RUN pip install --upgrade pip uv

# Copy root pyproject and lockfile
COPY pyproject.toml uv.lock ./

# Copy relevant source directories
COPY common-lib/        common-lib/
COPY user-service/      user-service/
COPY meeting-service/   meeting-service/

# Sync only the current service (excluding source install)
RUN uv sync \
      --project user-service \
      --no-install-package user-service \
      --no-install-package meeting-service \
      --no-dev

###############
# FINAL IMAGE #
###############
FROM python:3.13-slim
WORKDIR /app/user-service

# Copy virtual environment
COPY --from=builder /app/.venv /app/.venv

# Copy source files (just this service + shared lib)
COPY --from=builder /app/user-service /app/user-service
COPY --from=builder /app/common-lib/src/common_lib /app/.venv/lib/python3.13/site-packages/common_lib

# Set env to use virtualenv
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Entrypoint
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
