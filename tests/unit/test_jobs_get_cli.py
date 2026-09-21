"""CLI tests for jobbot get command (Indeed hard links)."""

from pathlib import Path


def test_get_indeed_job_dry_run_shows_summary(
    tmp_path: Path,
    project_root: Path,
    monkeypatch,
    capsys,
) -> None:
    """Dry-run fetches and shows job, writes nothing."""
    from jobbot.cli import run_cli

    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "profile.yaml").write_text(
        (project_root / "data" / "profile.example.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    fixture = project_root / "tests" / "fixtures" / "jobs" / "indeed_viewjob_data_scientist.html"

    run_cli(
        [
            "jobs",
            "get",
            "https://cl.indeed.com/viewjob?jk=8a5fab1a7c476a97",
            "--fixture",
            str(fixture),
        ],
        standalone_mode=False,
    )

    captured = capsys.readouterr()
    output = captured.out + captured.err

    assert "data scientist senior" in output.lower()
    assert "acme corp" in output.lower()
    assert "santiago" in output.lower()
    assert "dry-run" in output.lower()
    assert "nothing written" in output.lower()


def test_get_indeed_job_with_apply_stores_job(
    tmp_path: Path,
    project_root: Path,
    monkeypatch,
    capsys,
) -> None:
    """--apply stores the job and assigns an ID."""
    import json
    
    from jobbot.cli import run_cli

    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "profile.yaml").write_text(
        (project_root / "data" / "profile.example.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    fixture = project_root / "tests" / "fixtures" / "jobs" / "indeed_viewjob_data_scientist.html"

    run_cli(
        [
            "jobs",
            "get",
            "https://cl.indeed.com/viewjob?jk=8a5fab1a7c476a97&tk=tracking",
            "--fixture",
            str(fixture),
            "--apply",
        ],
        standalone_mode=False,
    )

    captured = capsys.readouterr()
    output = captured.out + captured.err

    assert "stored" in output.lower() or "✓" in output
    assert "j0" in output.lower()

    # Verify job was written to JSON
    job_json = tmp_path / "output" / "jobs" / "J0001" / "job.json"
    assert job_json.exists()
    
    job_data = json.loads(job_json.read_text(encoding="utf-8"))
    assert job_data["source"] == "indeed"
    assert job_data["source_job_id"] == "8a5fab1a7c476a97"
    assert "https://cl.indeed.com/viewjob?jk=8a5fab1a7c476a97" in job_data["url"]
    assert "Data Scientist" in job_data["title"]
    assert job_data["company"] == "Acme Corp"


def test_get_strips_tracking_params_and_stores_canonical(
    tmp_path: Path,
    project_root: Path,
    monkeypatch,
    capsys,
) -> None:
    """Tracking params are stripped; canonical URL is stored."""
    import json
    
    from jobbot.cli import run_cli

    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "profile.yaml").write_text(
        (project_root / "data" / "profile.example.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    fixture = project_root / "tests" / "fixtures" / "jobs" / "indeed_viewjob_data_scientist.html"

    run_cli(
        [
            "jobs",
            "get",
            "https://cl.indeed.com/viewjob?jk=abc123&tk=track&from=email&xpse=test",
            "--fixture",
            str(fixture),
            "--apply",
        ],
        standalone_mode=False,
    )

    # Verify canonical URL was stored
    job_json = tmp_path / "output" / "jobs" / "J0001" / "job.json"
    assert job_json.exists()
    
    job_data = json.loads(job_json.read_text(encoding="utf-8"))
    
    # Canonical URL has only jk
    assert job_data["url"] == "https://cl.indeed.com/viewjob?jk=abc123"
    assert "tk=" not in job_data["url"]
    assert "from=" not in job_data["url"]
    assert "xpse=" not in job_data["url"]


def test_get_invalid_indeed_url_fails(
    tmp_path: Path,
    project_root: Path,
    monkeypatch,
    capsys,
) -> None:
    """Invalid Indeed URL is rejected."""
    from jobbot.cli import run_cli

    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "profile.yaml").write_text(
        (project_root / "data" / "profile.example.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    # Missing jk parameter - this will be caught by is_indeed_viewjob_url check
    # which returns False, so it falls through to "not implemented" error
    run_cli(
        ["jobs", "get", "https://cl.indeed.com/viewjob?other=param"],
        standalone_mode=False,
    )

    captured = capsys.readouterr()
    output = captured.out + captured.err
    
    # The URL looks like Indeed but has no jk, so it's treated as "not implemented"
    assert "not implemented" in output.lower() or "workaround" in output.lower()


def test_get_unsupported_portal_gives_helpful_error(
    tmp_path: Path,
    project_root: Path,
    monkeypatch,
    capsys,
) -> None:
    """Unsupported portal shows workaround message."""
    from jobbot.cli import run_cli

    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "profile.yaml").write_text(
        (project_root / "data" / "profile.example.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    run_cli(
        ["jobs", "get", "https://example.com/jobs/123"],
        standalone_mode=False,
    )

    captured = capsys.readouterr()
    output = captured.out + captured.err
    
    assert "not implemented" in output.lower() or "workaround" in output.lower()
    assert "jobs add --file" in output.lower()
