"""Ready ATS hard link: careers JSON, not the SPA shell. No network."""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from jobbot.adapters.ready.fetch import fetch_ready_posting
from jobbot.adapters.ready.parse import api_url
from jobbot.cli import run_cli
from jobbot.companies.learn import learn_from_job
from jobbot.companies.registry import default_companies_path, load_companies
from jobbot.config import JobbotConfig
from jobbot.jobs.from_url import UnsupportedPortalFetchError
from jobbot.models.job import JobPosting
from jobbot.portals.detect import AtsKind, detect_ats

PAGE = "https://ready-ats-dev.web.app/careers/data-scientist-615?utm=1"
CANONICAL = "https://ready-ats-dev.web.app/careers/data-scientist-615"
FIXTURE = Path("tests/fixtures/ready/career_615.json")


def _workspace(tmp_path: Path, project_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = tmp_path / "data"
    data.mkdir()
    (tmp_path / "output").mkdir()
    (data / "profile.yaml").write_text(
        (project_root / "data" / "profile.example.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    templates = project_root / "templates"
    (tmp_path / ".jobbot.toml").write_text(
        f'[paths]\ntemplates = "{templates}"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("JOBBOT_ROOT", raising=False)

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("socket")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)


def test_ready_host_is_not_every_web_app() -> None:
    assert detect_ats(PAGE) is AtsKind.READY
    assert detect_ats("https://other-app.web.app/careers/data-scientist-615") is AtsKind.UNKNOWN


def test_get_stores_the_json_fixture(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    code = run_cli(
        ["get", PAGE, "--fixture", str(project_root / FIXTURE)],
        standalone_mode=False,
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "Data Scientist" in captured.out
    stored = list((tmp_path / "output" / "jobs").glob("*/job.json"))
    assert len(stored) == 1
    job = json.loads(stored[0].read_text(encoding="utf-8"))
    assert job["title"] == "Data Scientist"
    assert job["location"] == "Chile"
    assert job["remote_type"] == "remote"
    assert job["skills"] == ["Python", "Kedro"]
    assert job["description"]
    assert job["url"] == CANONICAL
    assert "utm" not in job["url"]


def test_without_a_fixture_or_network_nothing_is_invented(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)

    def offline(*_args: object, **_kwargs: object) -> None:
        raise OSError("network")

    monkeypatch.setattr(urllib.request, "urlopen", offline)
    code = run_cli(["get", CANONICAL], standalone_mode=False)
    captured = capsys.readouterr()
    assert code != 0
    assert "not invented" in captured.err
    assert list((tmp_path / "output" / "jobs").glob("*/job.json")) == []


def test_a_taken_down_posting_is_reported_with_its_http_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: urlopen raises HTTPError, so 404 read as Ready not answering."""

    def gone(*_args: object, **_kwargs: object) -> None:
        raise urllib.error.HTTPError(
            api_url("data-scientist-615"), 404, "Not Found", {}, io.BytesIO(b"{}")
        )

    monkeypatch.setattr(urllib.request, "urlopen", gone)
    with pytest.raises(UnsupportedPortalFetchError) as failure:
        fetch_ready_posting(CANONICAL)
    assert "HTTP 404" in str(failure.value)


def test_two_openings_are_one_portal(tmp_path: Path) -> None:
    """Regression: every /careers/<slug> was stored as its own ATS instance."""
    config = JobbotConfig(root=tmp_path)
    for slug in ("data-scientist-615", "backend-616"):
        result = learn_from_job(
            config,
            JobPosting.model_validate(
                {
                    "id": "pending",
                    "source": "ready",
                    "title": "Data Scientist",
                    "company": "Empresa Demo",
                    "url": f"https://ready-ats-dev.web.app/careers/{slug}",
                    "ats_kind": "ready",
                }
            ),
        )
        assert result is not None
        assert result.url == "https://ready-ats-dev.web.app"
    sites = load_companies(default_companies_path(tmp_path)).companies[0].career_sites
    assert [site.url for site in sites] == ["https://ready-ats-dev.web.app"]
