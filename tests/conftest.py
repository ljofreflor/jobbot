"""Shared pytest fixtures."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from rich.console import Console

from tests.fixtures.cv_pdf import write_sample_cv, write_scanned_cv

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def plain_cli_text(text: str) -> str:
    """Strip ANSI and soft-wrap newlines so CLI asserts survive CI terminals."""
    return _ANSI_RE.sub("", text).replace("\n", "")


@pytest.fixture(autouse=True)
def _stable_cli_console(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep Typer/Rich help and path lines readable under CI's narrow FORCE_COLOR TTY."""
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("COLUMNS", "120")
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    import jobbot.cli as cli

    cli.console = Console(force_terminal=False, no_color=True, width=120, highlight=False)
    cli.err_console = Console(
        stderr=True, force_terminal=False, no_color=True, width=120, highlight=False
    )


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def sample_cv_pdf(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return write_sample_cv(tmp_path_factory.mktemp("cv") / "cv_sample.pdf")


@pytest.fixture(scope="session")
def scanned_cv_pdf(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return write_scanned_cv(tmp_path_factory.mktemp("cv") / "cv_scanned.pdf")
