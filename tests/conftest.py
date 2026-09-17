"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fixtures.cv_pdf import write_sample_cv, write_scanned_cv


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def sample_cv_pdf(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return write_sample_cv(tmp_path_factory.mktemp("cv") / "cv_sample.pdf")


@pytest.fixture(scope="session")
def scanned_cv_pdf(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return write_scanned_cv(tmp_path_factory.mktemp("cv") / "cv_scanned.pdf")
