# Repository Guidelines

## Project Structure & Module Organization
`app/` contains the runtime code. Keep HTTP and startup wiring in `app/main.py`, provider integrations in `app/integrations/`, orchestration logic in `app/services/`, persistence in `app/db/`, request/response models in `app/schemas/`, and admin routes/auth in `app/web/`. Server-rendered admin templates live in `templates/admin/`. Put setup and operational docs in `docs/`. Mirror production modules with tests under `tests/` using files such as `tests/test_scheduler.py`.

## Build, Test, and Development Commands
Install locally with `pip install -e .[dev]`.
Run the app with `uvicorn app.main:app --reload`.
Run the full test suite with `pytest`.
Start the containerized stack with `docker compose up --build`.
Use `GET /health` and `/admin/login` for quick verification after boot when `WEB_ADMIN_PASSWORD` is configured.

## Coding Style & Naming Conventions
Target Python 3.11+ and follow the existing style: 4-space indentation, type hints on public functions, and small async service methods. Use `snake_case` for functions, variables, and modules; `PascalCase` for classes; and keep test names in the `test_<behavior>` form. There is no formatter configured in this repo today, so match surrounding code closely and keep imports grouped and readable.

## Testing Guidelines
Tests use `pytest` with `pytest-asyncio` (`asyncio_mode = auto`). Add or update tests whenever changing scheduler flows, webhook handling, admin routes, or persistence logic. Prefer focused unit tests with small stubs over broad integration fixtures. Run `pytest tests/test_main.py tests/test_scheduler.py` when touching request handling or orchestration behavior.

## Commit & Pull Request Guidelines
Recent commits use short, imperative, sentence-case subjects such as `Add web admin console for browser operations` and `Refresh Telegram messages for plain text delivery`. Keep commits scoped to one change. Pull requests should summarize behavior changes, note any `.env` or deployment impact, link the relevant issue, and include screenshots when modifying `templates/admin/` or admin UX.

## Security & Configuration Tips
Do not commit real secrets; start from `.env.example`. Verify changes that affect trusted senders, webhook validation, outbound email policy, or calendar mutation boundaries with tests and a short manual check through `/health` and the relevant workflow.
