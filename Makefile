.PHONY: sync lock lint format typecheck test audit check docs build

sync:
	uv sync --all-extras --all-groups

lock:
	uv lock

lint:
	uv run ruff check .

format:
	uv run ruff format .

typecheck:
	uv run pyright

test:
	uv run pytest

audit:
	uv run pip-audit

check: lint typecheck test

docs:
	uv run mkdocs serve

build:
	uv build
