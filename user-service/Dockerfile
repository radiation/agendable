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
      --project agendable \
      --no-install-package meeting-service \
      --no-dev \
 && uv pip install -e common-lib --upgrade --force-reinstall --verbose \
 && uv pip show common-lib \
 && ls -l /app/.venv/lib/python3.13/site-packages/common_lib*

###############
# FINAL IMAGE #
###############
FROM python:3.13-slim
WORKDIR /app/user-service

COPY --from=builder /app/.venv /app/.venv

COPY --from=builder /app/common-lib/src/common_lib \
     /app/.venv/lib/python3.13/site-packages/common_lib

ENV VIRTUAL_ENV=/app/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
ENV PYTHONPATH=/app/user-service

COPY --from=builder /app/user-service/app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
