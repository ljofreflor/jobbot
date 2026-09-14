.PHONY: install test lint format typecheck cv run

install:
	uv sync --group dev
	@echo "Run: uv run playwright install chromium  # when Phase 2 starts"

test:
	uv run pytest

lint:
	uv run ruff check .

format:
	uv run ruff format .

typecheck:
	uv run mypy src

cv:
	uv run jobbot cv build
	uv run jobbot cv build --target ats

run:
	uv run jobbot --help
