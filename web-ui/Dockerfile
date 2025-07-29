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
COPY web-ui/            web-ui/

# Sync only the current service (excluding source install)
RUN uv sync \
      --project web-ui \
      --no-install-package user-service \
      --no-install-package meeting-service \
      --no-install-package web-ui \
      --no-dev

###############
# FINAL IMAGE #
###############
FROM python:3.13-slim
WORKDIR /app/web-ui

# Bring in the venv from the builder
COPY --from=builder /app/.venv /app/.venv

# Copy over just the web-ui source, templates & static assets
COPY --from=builder /app/web-ui /app/web-ui/

# Set env to use virtualenv
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Entrypoint
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
