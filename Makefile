.PHONY: install test lint format typecheck cv run hooks pii-check pre-commit capabilities

install:
	uv sync --group dev
	@echo "Run: uv run playwright install chromium  # when Phase 2 starts"
	@echo "Run: make hooks  # enable the pre-commit hook (PII guard + tests)"

hooks:
	git config core.hooksPath .githooks
	@echo "Pre-commit enabled (.githooks/pre-commit): PII guard + unit tests"
	@echo "Work in progress with a red suite: JOBBOT_SKIP_TESTS=1 git commit ..."

pii-check:
	uv run python -m jobbot.ops.pii_guard

pre-commit:
	./.githooks/pre-commit

capabilities:
	uv run jobbot ops capabilities --write

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
