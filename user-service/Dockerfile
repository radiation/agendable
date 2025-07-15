#################
# BUILDER STAGE #
#################
FROM python:3.13-slim AS builder
WORKDIR /app

# Install UV
RUN pip install --upgrade pip \
 && pip install uv

# Copy root-level project metadata and lockfile
COPY pyproject.toml uv.lock ./

# Copy all workspace folders so UV can resolve path-deps
COPY common-lib/ common-lib/
COPY user-service/ user-service/

# Create the service venv & install only its runtime deps
WORKDIR /app/user-service
RUN uv sync --project user-service --no-dev

###############
# FINAL IMAGE #
###############
FROM python:3.13-slim
WORKDIR /app/user-service

# Copy prebuilt venv from the builder
COPY --from=builder /app/user-service/.venv .venv

# Copy only service code
COPY --from=builder /app/user-service/app ./app

# Activate venv
ENV VIRTUAL_ENV=/app/user-service/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

EXPOSE 8000

# Run FastAPI app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
