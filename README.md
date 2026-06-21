# Daily commands
uv run ruff format .

# Lint and auto-fix
uv run ruff check . --fix

# Type check (strict!)
uv run pyright

# Run tests with coverage
uv run pytest

# Full check (run before commit)
uv run ruff format . && uv run ruff check . && uv run pyright && uv run pytest