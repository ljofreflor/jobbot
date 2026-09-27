.PHONY: install test lint format typecheck cv run hooks pii-check docs-serve docs-build

install:
	uv sync --group dev
	@echo "Run: uv run playwright install chromium  # when Phase 2 starts"
	@echo "Run: make hooks  # enable the PII pre-commit guard"

hooks:
	git config core.hooksPath .githooks
	@echo "PII guard enabled (.githooks/pre-commit)"

pii-check:
	uv run python -m jobbot.ops.pii_guard

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

docs-serve:
	uv run --group docs mkdocs serve

docs-build:
	uv run --group docs mkdocs build --strict
