"""Ready ATS hard link: careers JSON, not the SPA shell. No network."""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import pytest

from jobbot.cli import run_cli
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
