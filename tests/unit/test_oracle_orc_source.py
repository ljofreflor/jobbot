"""Oracle Recruiting Cloud search: siteNumber, pages, closing date. No network."""

from __future__ import annotations

import json
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
import yaml

from jobbot.adapters.oracle_orc.parse import apply_detail, job_from_row
from jobbot.cli import run_cli
from jobbot.companies.discovery import career_root_url
from jobbot.portals.detect import AtsKind

FIXTURES = Path("tests/fixtures/oracle_orc")
END = datetime(2099, 10, 21, 3, 59, tzinfo=UTC)
JOB_URL = (
    "https://acme.fa.em2.oraclecloud.com/hcmUI/CandidateExperience/es/sites/CX_1/job/123"
)


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


def _install(monkeypatch: pytest.MonkeyPatch, fetch: object) -> None:
    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("socket")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    monkeypatch.setattr("jobbot.adapters.oracle_orc.discover.fetch_public", fetch)
    monkeypatch.setattr("jobbot.adapters.oracle_orc.discover.pause", lambda: None)


def _finder(url: str) -> str:
    return parse_qs(urlsplit(url).query)["finder"][0]


def _site(host: str, number: str, company: str, company_id: str) -> dict[str, object]:
    return {
        "id": company_id,
        "name": company,
        "career_sites": [
            {
                "url": f"https://{host}/hcmUI/CandidateExperience/en/sites/{number}",
                "domain": host,
                "site_type": "ats_instance",
                "ats": "oracle",
                "status": "active",
            }
        ],
    }


def test_dry_run_uses_the_finder_and_writes_nothing(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    payload = {
        "version": 1,
        "companies": [_site("acme.fa.em2.oraclecloud.com", "CX_1", "Acme", "acme")],
    }
    (tmp_path / "data" / "companies.yaml").write_text(
        yaml.safe_dump(payload, allow_unicode=True),
        encoding="utf-8",
    )
    page = (project_root / FIXTURES / "requisitions_page1.json").read_text(encoding="utf-8")
    detail = (project_root / FIXTURES / "requisition_detail.json").read_text(encoding="utf-8")
    calls: list[str] = []

    def fetch(url: str) -> tuple[int, str, str]:
        calls.append(url)
        if "JobRequisitionDetails" in url:
            return 200, detail, url
        return 200, page, url

    _install(monkeypatch, fetch)
    code = run_cli(
        ["jobs", "discover", "--source", "oracle_orc", "--query", "health", "--dry-run"],
        standalone_mode=False,
    )
    captured = capsys.readouterr()
    finder = _finder(calls[0])
    assert code == 0
    assert "siteNumber=CX_1" in finder
    assert 'keyword="health"' in finder
    assert "Health advisor" in captured.out
    assert "Santiago" in captured.out
    assert "Nothing written." in captured.out
    listed = json.loads(page)["items"][0]["requisitionList"][0]
    job = job_from_row(listed, host="acme.fa.em2.oraclecloud.com", site="CX_1", company="Acme")
    assert job is not None
    assert "/hcmUI/CandidateExperience/en/sites/CX_1/job/100" in (job.url or "")
    assert job.remote_type == "remote"
    assert list((tmp_path / "output" / "jobs").glob("*/job.json")) == []


def test_three_offsets_cover_sixty(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    root = project_root / FIXTURES
    pages = {
        "offset=0": (root / "requisitions_page_offset0.json").read_text(encoding="utf-8"),
        "offset=25": (root / "requisitions_page_offset25.json").read_text(encoding="utf-8"),
        "offset=50": (root / "requisitions_page_offset50.json").read_text(encoding="utf-8"),
    }
    detail = (root / "requisition_detail.json").read_text(encoding="utf-8")
    calls: list[str] = []

    def fetch(url: str) -> tuple[int, str, str]:
        calls.append(url)
        if "JobRequisitionDetails" in url:
            return 200, detail, url
        finder = _finder(url)
        for key, body in pages.items():
            if finder.endswith(key):
                return 200, body, url
        raise AssertionError(finder)

    _install(monkeypatch, fetch)
    code = run_cli(
        [
            "jobs",
            "discover",
            "--source",
            "oracle_orc",
            "--site",
            "acme.fa.em2.oraclecloud.com/CX_1",
            "--query",
            "health",
            "--limit",
            "100",
            "--dry-run",
        ],
        standalone_mode=False,
    )
    assert code == 0
    finders = [_finder(url) for url in calls if "JobRequisitions" in url]
    assert any(item.endswith("offset=0") for item in finders)
    assert any(item.endswith("offset=25") for item in finders)
    assert any(item.endswith("offset=50") for item in finders)
    assert not any("offset=75" in item for item in finders)


def test_end_date_is_kept_and_an_expired_one_is_not_stored(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = project_root / FIXTURES
    detail = json.loads((root / "requisition_detail.json").read_text(encoding="utf-8"))
    row = json.loads((root / "requisitions_page1.json").read_text(encoding="utf-8"))
    job = job_from_row(
        row["items"][0]["requisitionList"][0],
        host="acme.fa.em2.oraclecloud.com",
        site="CX_1",
        company="Acme",
    )
    assert job is not None
    assert apply_detail(job, detail).closes_at == END
    _workspace(tmp_path, project_root, monkeypatch)
    page = json.dumps(
        {
            "items": [
                {
                    "TotalJobsCount": 1,
                    "requisitionList": [row["items"][0]["requisitionList"][1]],
                }
            ]
        }
    )
    expired = (root / "requisition_detail_expired.json").read_text(encoding="utf-8")

    def fetch(url: str) -> tuple[int, str, str]:
        if "JobRequisitionDetails" in url:
            return 200, expired, url
        return 200, page, url

    _install(monkeypatch, fetch)
    code = run_cli(
        [
            "jobs",
            "discover",
            "--source",
            "oracle_orc",
            "--site",
            "acme.fa.em2.oraclecloud.com/CX_1",
            "--query",
            "health",
        ],
        standalone_mode=False,
    )
    assert code == 0
    assert list((tmp_path / "output" / "jobs").glob("*/job.json")) == []


def test_learning_keeps_the_site_number(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert "sites/CX_1" in career_root_url(JOB_URL, AtsKind.ORACLE)
    _workspace(tmp_path, project_root, monkeypatch)

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("socket")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    code = run_cli(
        ["companies", "learn", JOB_URL, "--company", "Acme"],
        standalone_mode=False,
    )
    assert code == 0
    saved = yaml.safe_load((tmp_path / "data" / "companies.yaml").read_text(encoding="utf-8"))
    url = saved["companies"][0]["career_sites"][0]["url"]
    assert "sites/CX_1" in url


def test_a_403_does_not_drop_the_other_site(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    payload = {
        "version": 1,
        "companies": [
            _site("acme.fa.em2.oraclecloud.com", "CX_1", "Acme", "acme"),
            _site("beta.fa.em2.oraclecloud.com", "CX_2", "Beta", "beta"),
        ],
    }
    (tmp_path / "data" / "companies.yaml").write_text(
        yaml.safe_dump(payload, allow_unicode=True),
        encoding="utf-8",
    )
    page = (project_root / FIXTURES / "requisitions_page_offset0.json").read_text(encoding="utf-8")
    detail = (project_root / FIXTURES / "requisition_detail.json").read_text(encoding="utf-8")

    def fetch(url: str) -> tuple[int, str, str]:
        if "acme.fa.em2.oraclecloud.com" in url:
            return 403, "", url
        if "JobRequisitionDetails" in url:
            return 200, detail, url
        return 200, page, url

    _install(monkeypatch, fetch)
    code = run_cli(
        ["jobs", "discover", "--source", "oracle_orc", "--query", "health"],
        standalone_mode=False,
    )
    assert code == 0
    stored = list((tmp_path / "output" / "jobs").glob("*/job.json"))
    assert len(stored) == 1
    saved = json.loads(stored[0].read_text(encoding="utf-8"))
    assert saved["source_job_id"] == "beta.fa.em2.oraclecloud.com/CX_2:1"


def test_a_site_without_a_number_exits_2(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
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
            "oracle_orc",
            "--site",
            "acme.fa.em2.oraclecloud.com",
            "--query",
            "health",
        ],
        standalone_mode=False,
    )
    assert code == 2
