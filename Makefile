.PHONY: install test lint format typecheck cv run hooks pii-check pre-commit capabilities coverage coverage-main architecture

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

architecture:
	@command -v dot >/dev/null || (echo "Graphviz required: brew install graphviz"; exit 1)
	uv sync --group docs
	uv run python scripts/render_architecture.py

test:
	uv run pytest

coverage:
	uv run pytest tests/unit --cov=jobbot --cov-report=term-missing:skip-covered --cov-fail-under=80

coverage-main:
	uv run pytest tests/unit --junitxml=junit.xml --cov=jobbot --cov-report=term-missing:skip-covered --cov-fail-under=80
	uv run python -m jobbot.ops.test_gate junit.xml --min-pass-rate 0.95

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
