"""Indeed apply handoff — open the right page and stop before submit."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

from jobbot.adapters.ats.apply import describe_prefill, open_ats_in_browser
from jobbot.adapters.base import ApplicationPackage, ApplyMethod, PrefillResult
from jobbot.models.candidate import Candidate
from jobbot.models.job import JobPosting


class IndeedApplyAdapter:
    """Open Indeed Apply or the external ATS. Never submits."""

    name = "indeed"

    def detect_method(self, job: JobPosting) -> ApplyMethod:
        if apply_target(job):
            return ApplyMethod.EXTERNAL_ATS
        return ApplyMethod.UNKNOWN

    def prefill(
        self,
        candidate: Candidate,
        job: JobPosting,
        package: ApplicationPackage,
    ) -> PrefillResult:
        _ = package
        return describe_prefill(candidate, job)

    def attach_cv(self, package: ApplicationPackage) -> None:
        """CV attach stays in the Indeed or ATS UI."""
        _ = package

    def open(self, job: JobPosting) -> str | None:
        url = apply_target(job)
        if not url:
            return None
        open_ats_in_browser(url)
        return url


def apply_route(job: JobPosting) -> tuple[str, tuple[str, ...]]:
    """Where apply goes, and the Indeed Apply steps. An external host has no Indeed steps."""
    target = apply_target(job)
    if not target:
        return "", ()
    if _is_indeed_url(target):
        return target, ("applystart",)
    return target, ()


def apply_target(job: JobPosting) -> str | None:
    """External ATS when the posting leaves Indeed; otherwise Indeed Apply."""
    if job.ats_url and not _is_indeed_url(job.ats_url):
        return job.ats_url
    return _applystart(job)


def _applystart(job: JobPosting) -> str | None:
    jk = job.source_job_id
    host: str | None = None
    scheme = "https"
    for candidate in (job.url, job.ats_url):
        if not candidate or not _is_indeed_url(candidate):
            continue
        parsed = urlparse(candidate)
        host = parsed.hostname
        scheme = parsed.scheme or "https"
        if not jk:
            match = re.search(r"[?&]jk=([a-f0-9]+)", candidate, flags=re.I)
            if match:
                jk = match.group(1)
        break
    if not host or not jk:
        return None
    return f"{scheme}://{host}/applystart?jk={jk}"


def _is_indeed_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").casefold()
    return host == "indeed.com" or host.endswith(".indeed.com")


_CV_TOKEN = re.compile(r"\bcv\b|resume|curr[ií]cul", re.IGNORECASE)


def page_asks_for_cv(html: str) -> bool:
    """True when this step has a file input labeled as the CV. A letter upload does not count."""
    soup = BeautifulSoup(html or "", "html.parser")
    for node in soup.find_all("input"):
        if not isinstance(node, Tag):
            continue
        kind = node.get("type")
        if not isinstance(kind, str) or kind.casefold() != "file":
            continue
        if _CV_TOKEN.search(_input_blob(soup, node)):
            return True
    return False


def _input_blob(soup: BeautifulSoup, node: Tag) -> str:
    parts = [node.get(attr) or "" for attr in ("name", "id", "aria-label", "accept")]
    control_id = node.get("id")
    if isinstance(control_id, str) and control_id:
        label = soup.find("label", attrs={"for": control_id})
        if isinstance(label, Tag):
            parts.append(label.get_text(" ", strip=True))
    parent = node.find_parent("label")
    if isinstance(parent, Tag):
        parts.append(parent.get_text(" ", strip=True))
    return " ".join(part for part in parts if isinstance(part, str))


def tailored_cv_path(output_dir: Path, job_id: str) -> Path | None:
    """The packaged PDF, else the job build. A base CV is not this posting's CV."""
    packaged = output_dir / "jobs" / job_id / "application" / "cv.pdf"
    built = output_dir / "jobs" / job_id / "cv.pdf"
    for path in (packaged, built):
        if path.is_file():
            return path
    return None


def missing_tailored_cv(job_id: str) -> str:
    """What to run when neither job PDF exists. Does not point at the base CV."""
    return f"Build the CV first: output/jobs/{job_id}/cv.pdf"
