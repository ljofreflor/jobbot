"""Lumesse is recognised from its widget and refused without a network call."""

from __future__ import annotations

import urllib.request
from pathlib import Path

import pytest
import yaml

from jobbot.adapters.lumesse.discover import forbids_fo_rest
from jobbot.cli import run_cli
from jobbot.companies.oneshot import USER_AGENT
from jobbot.portals.detect import AtsKind, detect_ats, detect_ats_in_html

FIXTURES = Path("tests/fixtures/lumesse")
SITE = "https://careers.ifrc.org/lumesse_jobsearch.html"
API = "https://emea3.recruitmentplatform.com/fo/rest/jobs"


def _workspace(tmp_path: Path, project_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = tmp_path / "data"
    data.mkdir()
    (tmp_path / "output").mkdir()
    example = project_root / "data" / "profile.example.yaml"
    raw = yaml.safe_load(example.read_text(encoding="utf-8"))
    (data / "profile.yaml").write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)


def test_discover_refuses_without_opening_a_socket(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("socket")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    code = run_cli(
        [
            "jobs",
            "discover",
            "--source",
            "lumesse",
            "--site",
            "careers.ifrc.org",
            "--query",
            "health",
        ],
        standalone_mode=False,
    )
    captured = capsys.readouterr()
    assert code == 2
    assert "robots.txt" in captured.out
    assert "prohíbe /fo/rest" in captured.out
    assert "2026-10-08" in captured.out
    assert "jobs add --file" in captured.out
    assert "robots.txt de recruitmentplatform.com" in captured.out
    assert "robots.txt de careers.ifrc.org" not in captured.out


def test_an_empty_site_is_rejected(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    code = run_cli(["jobs", "discover", "--source", "lumesse"], standalone_mode=False)
    assert code == 2


def test_widget_html_is_lumesse(project_root: Path) -> None:
    html = (project_root / FIXTURES / "jobsearch_widget.html").read_text(encoding="utf-8")
    kind, evidence = detect_ats_in_html(html)
    assert kind is AtsKind.LUMESSE
    assert "talentlink widget" in evidence


def test_recruitmentplatform_host_is_lumesse() -> None:
    kind = detect_ats("https://emea3.recruitmentplatform.com/apply-app/static/talentportal.js")
    assert kind is AtsKind.LUMESSE


def test_robots_forbids_fo_rest_for_jobbot(project_root: Path) -> None:
    text = (project_root / FIXTURES / "robots.txt").read_text(encoding="utf-8")
    assert forbids_fo_rest(text, API) is True
    parser_agent = USER_AGENT
    assert "jobbot" in parser_agent


def test_companies_learn_records_the_blocked_widget(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    fixture = project_root / FIXTURES / "jobsearch_widget.html"
    code = run_cli(
        [
            "companies",
            "learn",
            SITE,
            "--company",
            "Ejemplo",
            "--fixture",
            str(fixture),
        ],
        standalone_mode=False,
    )
    assert code == 0
    saved = yaml.safe_load((tmp_path / "data" / "companies.yaml").read_text(encoding="utf-8"))
    site = saved["companies"][0]["career_sites"][0]
    assert site["ats"] == "lumesse"
    blob = yaml.safe_dump(site)
    assert "discovery: blocked (robots)" in blob
