# Contributing

Thanks for your interest in contributing!

## Local setup
1. Install dependencies: `uv sync --group dev`
2. Apply migrations: `uv run alembic upgrade head`
3. Start app: `uv run uvicorn agendable.app:app --reload`
4. Open `http://127.0.0.1:8000/`

For local OIDC testing and multi-user flows, see the Keycloak setup in `README.md`.

## Quick start
1. Fork the repo and create a branch from `main`:
   - `feature/<short-name>` for features
   - `fix/<short-name>` for bug fixes
2. Keep PRs small and focused.
3. Ensure tests and linting pass before opening a PR.

## Development workflow
- Open a pull request against `main`
- CI must pass before merge
- Prefer squash merges (keeps history clean)

## Code style
- Prefer clarity over cleverness
- Follow existing conventions in the codebase
- Add/adjust tests for behavioral changes

### Project conventions
- Keep FastAPI routes thin; push reusable logic into service/repo/helper modules.
- Use SQLAlchemy 2.0 typed ORM patterns (`Mapped[...]`, `mapped_column`, `DeclarativeBase`).
- Prefer HTMX-first UI updates and progressive enhancement over heavy frontend frameworks.
- For schema changes, include an Alembic migration unless you explicitly document why not needed.

### Layer boundaries
- Entry points (`agendable.cli`, app startup wiring, route handlers) should stay orchestration-focused: parse inputs, call services, shape responses.
- Service modules (`src/agendable/services/`) own business rules and workflow policy (for example retry/backoff decisions, state transitions, and cross-entity flow).
- Repository modules (`src/agendable/db/repos/`) own persistence/query shaping and CRUD helpers; avoid embedding business policy in repositories.
- Integration/adapters (for example `src/agendable/reminders.py`) own provider-specific behavior and error translation (SMTP/Slack/etc.).
- If logic answers "what should happen," it belongs in a service. If it answers "how data is stored/fetched," it belongs in a repository.

## Before opening a PR
For auth/OIDC seam and route-layering changes, a fast local check is:

- `uv run sh -c 'ruff check . && mypy --strict src && pytest -q tests/architecture/test_route_layering.py tests/test_web_smoke.py tests/auth/test_oidc_start.py tests/auth/test_account_linking_oidc_flow.py tests/auth/test_account_linking_profile.py tests/auth/test_oidc_autoprovision.py tests/auth/test_google_calendar_sync_trigger.py'`

Run the same checks CI enforces:

- `uv run ruff check .`
- `uv run mypy --strict src`
- `uv run pytest --cov=agendable --cov-report=term-missing`
- `uv run xenon --max-absolute B --max-modules B --max-average A src/agendable`

If your changes touch auth/OIDC, include the relevant env-var/config notes in your PR description.

## Reporting issues
Please use the issue templates for bug reports and feature requests.
Include reproduction steps and relevant environment details.

## Security
If you believe you’ve found a security vulnerability, please do not open a public issue.
Instead, open a private advisory (if enabled) or contact the maintainer directly.