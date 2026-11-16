"""Indeed apply that leaves Indeed, and a challenge that stops the one entry route."""

from __future__ import annotations

from pathlib import Path

import pytest

from jobbot.adapters.ats.indeed_apply import apply_route
from jobbot.adapters.indeed.external import remember_external_landing
from jobbot.adapters.indeed.jobs import card_to_job_posting
from jobbot.cli import run_cli
from jobbot.exit_codes import MANUAL_CHALLENGE

VIEW = "https://cl.indeed.com/viewjob?jk=8a5fab1a7c476a97"


def _card() -> dict[str, str]:
    return {
        "source_job_id": "8a5fab1a7c476a97",
        "url": VIEW,
        "title": "",
        "company": "",
        "location": "",
        "snippet": "",
    }


def _html(extra: str = "") -> str:
    return f"""<!DOCTYPE html><html><body>
    <h1 data-testid="jobsearch-JobInfoHeader-title">Editor</h1>
    <div data-testid="inlineHeader-companyName">Diario</div>
    <div data-testid="jobsearch-JobInfoHeader-locationText">Concepción</div>
    <div id="jobDescriptionText"><p>SEO y WordPress.</p></div>
    {extra}
    </body></html>"""


def test_chile_apply_button_stores_the_external_destination() -> None:
    extra = (
        '<a href="https://cl.indeed.com/rc/clk?jk=8a5fab1a7c476a97'
        '&amp;dest=https%3A%2F%2Fwww.bne.cl%2Foferta%2Fabc%3Futm_source%3Dindeed">'
        "Postular en el sitio de la empresa</a>"
    )
    job = card_to_job_posting(_card(), detail_html=_html(extra), placeholder_id="TMP")

    assert job.ats_url == "https://www.bne.cl/oferta/abc"
    assert job.ats_kind == "bne"
    url, steps = apply_route(job)
    assert steps == ()
    assert "applystart" not in url


def test_applystart_landing_on_bne_skips_indeed_apply() -> None:
    job = card_to_job_posting(_card(), detail_html=_html(), placeholder_id="TMP")
    landed = remember_external_landing(
        job, "https://www.bne.cl/oferta/abc?utm_source=indeed&from=ia"
    )

    assert landed.ats_url == "https://www.bne.cl/oferta/abc"
    assert landed.ats_kind == "bne"
    assert apply_route(landed)[1] == ()


def test_applystart_landing_on_hiringroom_is_not_indeed() -> None:
    job = card_to_job_posting(_card(), detail_html=_html(), placeholder_id="TMP")
    landed = remember_external_landing(
        job, "https://acme.hiringroom.com/jobs/1?from=indeed&utm_medium=cpc"
    )

    assert landed.ats_url == "https://acme.hiringroom.com/jobs/1"
    assert landed.ats_kind != "indeed"
    assert "hiringroom.com" in (landed.ats_url or "")
    assert apply_route(landed)[1] == ()


def test_smartapply_posting_still_uses_applystart() -> None:
    extra = '<a href="https://smartapply.indeed.com/beta/indeedapply/form">Postular ahora</a>'
    job = card_to_job_posting(_card(), detail_html=_html(extra), placeholder_id="TMP")

    assert job.ats_url == "https://cl.indeed.com/applystart?jk=8a5fab1a7c476a97"
    assert job.ats_kind == "indeed"
    url, steps = apply_route(job)
    assert steps == ("applystart",)
    assert url.endswith("/applystart?jk=8a5fab1a7c476a97")


def test_challenge_on_the_entry_page_exits_4_and_opens_nothing(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "output").mkdir()
    (tmp_path / "data" / "profile.yaml").write_text(
        (project_root / "data" / "profile.example.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / ".jobbot.toml").write_text(
        f'[paths]\ntemplates = "{project_root / "templates"}"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("jobbot.cli._fetch_public_html", lambda _url: None)
    monkeypatch.setattr(
        "jobbot.jobs.closure.fetch_posting_text",
        lambda _url, **_k: "<html>still open</html>",
    )
    import jobbot.cli as cli
    from jobbot.db.engine import make_engine, make_session_factory
    from jobbot.jobs.repository import JobRepository
    from jobbot.models.job import JobPosting

    config = cli.load_config()
    session = make_session_factory(make_engine(config.database_path))()
    stored = JobRepository(session).upsert_external(
        JobPosting.model_validate(
            {
                "id": "PENDING",
                "source": "indeed",
                "source_job_id": "8a5fab1a7c476a97",
                "title": "Editor",
                "company": "Diario",
                "url": VIEW,
                "ats_url": "https://cl.indeed.com/applystart?jk=8a5fab1a7c476a97",
                "ats_kind": "indeed",
                "description": "Una descripción.",
            }
        )
    )
    session.commit()
    opened: list[str] = []
    monkeypatch.setattr(
        "jobbot.browser.background.open_url",
        lambda url, **_k: opened.append(url) or (_ for _ in ()).throw(AssertionError(url)),
    )

    def entry(_url: str) -> str:
        return "<html>Verificación adicional requerida cf-turnstile</html>"

    monkeypatch.setattr("jobbot.adapters.indeed.external.read_apply_entry", entry)
    code = run_cli(["application", "apply", stored.id], standalone_mode=False)
    captured = capsys.readouterr()

    assert code == MANUAL_CHALLENGE
    assert opened == []
    assert "No other route was tried." in captured.err
    assert "bypass" not in captured.err.casefold()
