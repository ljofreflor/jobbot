"""Indeed apply target: external ATS, Indeed Apply, or a closed posting."""

from __future__ import annotations

from pathlib import Path

import pytest

from jobbot.adapters.ats.indeed_apply import (
    IndeedApplyAdapter,
    missing_tailored_cv,
    page_asks_for_cv,
    tailored_cv_path,
)
from jobbot.adapters.ats.registry import adapter_for_kind
from jobbot.adapters.indeed.jobs import IndeedJobClosed, card_to_job_posting
from jobbot.models.candidate import Candidate
from jobbot.models.job import JobPosting
from jobbot.portals.detect import AtsKind
from tests.fixtures.profile import sample_profile_dict


def _card(url: str) -> dict[str, str]:
    jk = url.rsplit("jk=", 1)[-1].split("&", 1)[0]
    return {
        "source_job_id": jk,
        "url": url,
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


def test_indeed_adapter_is_registered_like_the_others() -> None:
    adapter = adapter_for_kind(AtsKind.INDEED)
    assert adapter is not None
    assert adapter.name == "indeed"


def test_indeed_apply_url_when_the_posting_stays_on_indeed() -> None:
    url = "https://cl.indeed.com/viewjob?jk=8a5fab1a7c476a97"
    job = card_to_job_posting(_card(url), detail_html=_html(), placeholder_id="TMP")

    assert job.ats_url == "https://cl.indeed.com/applystart?jk=8a5fab1a7c476a97"
    assert job.ats_kind == "indeed"


def test_external_apply_link_wins_over_indeed_apply() -> None:
    url = "https://mx.indeed.com/viewjob?jk=8a5fab1a7c476a97"
    html = _html(
        extra=(
            '<a href="https://jobs.lever.co/acme/role-1">Apply on company site</a>'
        )
    )
    job = card_to_job_posting(_card(url), detail_html=html, placeholder_id="TMP")

    assert job.ats_url == "https://jobs.lever.co/acme/role-1"
    assert job.ats_kind == "lever"


def test_a_closed_posting_is_refused() -> None:
    url = "https://cl.indeed.com/viewjob?jk=8a5fab1a7c476a97"
    html = _html(extra="<p>Ya no acepta aplicaciones.</p>")

    with pytest.raises(IndeedJobClosed):
        card_to_job_posting(_card(url), detail_html=html, placeholder_id="TMP")


def test_open_uses_the_external_ats_when_one_was_stored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: list[str] = []
    monkeypatch.setattr(
        "jobbot.browser.background.open_url", lambda url, **_k: opened.append(url) or url
    )
    job = JobPosting(
        id="J0001",
        source="indeed",
        source_job_id="8a5fab1a7c476a97",
        url="https://cl.indeed.com/viewjob?jk=8a5fab1a7c476a97",
        title="Editor",
        company="Diario",
        ats_url="https://jobs.lever.co/acme/role-1",
        ats_kind="lever",
    )

    IndeedApplyAdapter().open(job)

    assert opened == ["https://jobs.lever.co/acme/role-1"]


def test_prefill_does_not_invent_a_password() -> None:
    candidate = Candidate.model_validate(sample_profile_dict())
    job = JobPosting(
        id="J0001",
        source="indeed",
        url="https://cl.indeed.com/viewjob?jk=8a5fab1a7c476a97",
        title="Editor",
        company="Diario",
    )
    result = IndeedApplyAdapter().prefill(candidate, job, None)  # type: ignore[arg-type]
    text = " ".join(result.filled + result.needs_review).casefold()

    assert "password" not in text
    assert "contraseña" not in text


def test_a_labeled_file_input_is_the_cv_step() -> None:
    html = (
        '<label for="resume">Currículum</label>'
        '<input id="resume" type="file" name="resume">'
    )
    assert page_asks_for_cv(html) is True


def test_a_letter_upload_is_not_the_cv_step() -> None:
    html = (
        '<label for="letter">Cover letter</label>'
        '<input id="letter" type="file" name="letter">'
        '<input type="text" name="phone">'
    )
    assert page_asks_for_cv(html) is False


def test_tailored_cv_prefers_the_package_and_skips_the_base(tmp_path: Path) -> None:
    job = tmp_path / "jobs" / "J0001"
    (job / "application").mkdir(parents=True)
    (job / "application" / "cv.pdf").write_bytes(b"%PDF packaged")
    (job / "cv.pdf").write_bytes(b"%PDF built")
    (tmp_path / "base").mkdir()
    (tmp_path / "base" / "cv.pdf").write_bytes(b"%PDF base")

    chosen = tailored_cv_path(tmp_path, "J0001")

    assert chosen == job / "application" / "cv.pdf"


def test_tailored_cv_uses_the_job_build_when_there_is_no_package(tmp_path: Path) -> None:
    job = tmp_path / "jobs" / "J0001"
    job.mkdir(parents=True)
    (job / "cv.pdf").write_bytes(b"%PDF built")

    assert tailored_cv_path(tmp_path, "J0001") == job / "cv.pdf"


def test_missing_tailored_cv_does_not_offer_the_base(tmp_path: Path) -> None:
    (tmp_path / "base").mkdir()
    (tmp_path / "base" / "cv.pdf").write_bytes(b"%PDF base")

    assert tailored_cv_path(tmp_path, "J0001") is None
    note = missing_tailored_cv("J0001")
    assert note == "Build the CV first: output/jobs/J0001/cv.pdf"
    assert "base" not in note
