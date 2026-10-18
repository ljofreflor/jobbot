"""A filled vacancy is evidence, not an open job."""

from __future__ import annotations

import io
import urllib.request

import pytest

from jobbot.jobs.closure import closure_evidence, closure_evidence_for_job, fetch_posting_text
from jobbot.models.job import JobPosting


def test_apply_banner_with_ellipsis_is_evidence() -> None:
    html = "We're sorry… the job you are trying to apply for has been filled."
    assert closure_evidence(html) == "the job you are trying to apply for has been filled"


def test_spanish_filled_banner_is_evidence() -> None:
    text = "Title: Un cargo\nCompany: Empresa\n\nEste cargo ya fue cubierto."
    assert closure_evidence(text) == "cargo ya fue cubierto"


def test_html_banner_is_evidence() -> None:
    html = "<div class='banner'>This position is no longer available.</div>"
    assert closure_evidence(html) == "this position is no longer available"


def test_hidden_expire_template_is_not_evidence() -> None:
    """Phenom keeps the filled banner in the DOM and only un-hides it when closed."""
    html = """
    <div ph-page-state="exists" class="job-header-block">Data Scientist Senior</div>
    <!-- Expired job page state -->
    <div ph-page-state="expired" class="hide job-expired-view">
      <h2>We're sorry… the job you are trying to apply for has been filled.</h2>
    </div>
    """
    assert closure_evidence(html) is None


def test_unhidden_expire_view_is_evidence() -> None:
    html = """
    <div ph-page-state="exists" class="hide job-header-block">Data Scientist Senior</div>
    <div ph-page-state="expired" class="job-expired-view">
      <h2>We're sorry… the job you are trying to apply for has been filled.</h2>
    </div>
    """
    assert closure_evidence(html) == "the job you are trying to apply for has been filled"


def test_ordinary_description_is_not_closed() -> None:
    text = "The team closed the books each quarter and filled the warehouse."
    assert closure_evidence(text) is None


def test_live_page_counts_when_the_stored_text_does_not() -> None:
    job = JobPosting(
        id="J1",
        title="Un cargo",
        company="Empresa",
        url="https://careers.example.com/global/en/job/abc/un-cargo",
        description="A normal description of the work.",
    )

    def fetch(url: str) -> str:
        assert "careers.example.com" in url
        return "<p>El cargo ya está cubierto</p>"

    assert closure_evidence_for_job(job, fetch=fetch) == "el cargo ya está cubierto"


def test_unread_page_is_unknown_not_open() -> None:
    job = JobPosting(
        id="J1",
        title="Un cargo",
        company="Empresa",
        url="https://careers.example.com/job/abc",
        description="A normal description.",
    )

    def fetch(_url: str) -> str:
        raise OSError("connection dropped")

    assert closure_evidence_for_job(job, fetch=fetch) is None


def test_get_on_board_spanish_closed_banner_is_evidence() -> None:
    text = "Empleo finalizado - No se reciben más postulantes\n\nBuscamos analista."
    assert closure_evidence(text) == "no se reciben más postulantes"


class _Page(io.BytesIO):
    status = 200

    class headers:  # noqa: N801 — mimics http.client.HTTPMessage
        @staticmethod
        def get_content_charset() -> str:
            return "utf-8"

    def __enter__(self) -> _Page:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


def test_accented_posting_url_is_sent_percent_encoded(monkeypatch: pytest.MonkeyPatch) -> None:
    """`jobs add --url` crashed with 'ascii' codec on …/consultoría-… (urllib sends ASCII)."""
    sent: list[str] = []

    def urlopen(req: urllib.request.Request, timeout: float) -> _Page:
        req.full_url.encode("ascii")
        sent.append(req.full_url)
        return _Page(b"<p>Oferta finalizada</p>")

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)

    page = fetch_posting_text("https://careers.acme.test/job/1/consultoría-remoto#apply")

    assert sent == ["https://careers.acme.test/job/1/consultor%C3%ADa-remoto"]
    assert closure_evidence(page) == "oferta finalizada"


def test_unsendable_posting_url_is_an_os_error() -> None:
    with pytest.raises(OSError, match="cannot be requested"):
        fetch_posting_text("http://[::1")
