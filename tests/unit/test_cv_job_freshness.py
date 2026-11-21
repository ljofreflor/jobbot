"""A job CV on disk is stale once profile.yaml is newer than it."""

from __future__ import annotations

import os
from pathlib import Path

from jobbot.cv.build import should_rebuild_job_cv


def test_missing_cv_is_rebuilt(tmp_path: Path) -> None:
    profile = tmp_path / "profile.yaml"
    profile.write_text("name: Ana\n", encoding="utf-8")
    assert should_rebuild_job_cv(tmp_path / "job", profile) is True


def test_existing_cv_older_than_profile_is_rebuilt(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    pdf = job_dir / "cv.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    profile = tmp_path / "profile.yaml"
    profile.write_text("name: Ana\n", encoding="utf-8")
    os.utime(pdf, (1_000, 1_000))
    os.utime(profile, (2_000, 2_000))
    assert should_rebuild_job_cv(job_dir, profile) is True


def test_cv_newer_than_profile_is_kept(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    pdf = job_dir / "cv.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    profile = tmp_path / "profile.yaml"
    profile.write_text("name: Ana\n", encoding="utf-8")
    os.utime(profile, (1_000, 1_000))
    os.utime(pdf, (2_000, 2_000))
    assert should_rebuild_job_cv(job_dir, profile) is False


def test_failed_rebuild_cannot_reuse_previous_pdf(
    tmp_path: Path,
    project_root: Path,
    monkeypatch,
) -> None:
    from jobbot.applications.manager import (
        FilesystemApplicationPackage,
        prepare_application_package,
    )
    from jobbot.config import JobbotConfig, PathsConfig
    from jobbot.cv.build import build_adapted_cv
    from jobbot.models.candidate import Candidate
    from jobbot.models.job import JobPosting
    from jobbot.models.match import JobMatch
    from tests.fixtures.profile import sample_profile_dict

    config = JobbotConfig(root=tmp_path, paths=PathsConfig(templates=project_root / "templates"))
    job = JobPosting(id="J0001", title="Role", company="Example")
    job_dir = config.output_dir / "jobs" / job.id
    job_dir.mkdir(parents=True)
    old_pdf = job_dir / "cv.pdf"
    old_pdf.write_bytes(b"%PDF OLD PROFILE")
    config.profile_path.parent.mkdir(parents=True)
    config.profile_path.write_text("changed", encoding="utf-8")
    os.utime(old_pdf, (1, 1))
    # Include a package prepared on an earlier run.
    package_dir = prepare_application_package(job, config.output_dir)

    def fail_compile(*args):
        # XeLaTeX can leave a partial PDF before reporting a failure.
        old_pdf.write_bytes(b"%PDF PARTIAL")
        raise RuntimeError("compiler failed")

    monkeypatch.setattr("jobbot.cv.build._compile_xelatex", fail_compile)
    written = build_adapted_cv(
        config,
        Candidate.model_validate(sample_profile_dict()),
        job,
        JobMatch(job_id=job.id, score=0),
    )
    prepare_application_package(job, config.output_dir)

    assert job_dir / "cv_ats.txt" in written
    assert not old_pdf.exists()
    assert not (package_dir / "cv.pdf").exists()
    assert FilesystemApplicationPackage(package_dir).cv_pdf is None
