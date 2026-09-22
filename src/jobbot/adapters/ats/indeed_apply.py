"""Indeed ATS adapter - open apply page (HITL submit)."""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from jobbot.adapters.base import ApplicationPortalAdapter, ApplyMethod, PrefillResult
from jobbot.models.candidate import Candidate
from jobbot.models.job import JobPosting

logger = logging.getLogger("jobbot.ats.indeed")


class IndeedApplyAdapter(ApplicationPortalAdapter):
    """Indeed Apply adapter - opens apply page, stops before submit."""

    @property
    def ats_kind(self) -> str:
        return "indeed"

    def can_handle(self, job: JobPosting) -> bool:
        """Can handle if job has Indeed URL or Indeed as source."""
        if job.source == "indeed":
            return True
        if job.ats_url and "indeed.com" in job.ats_url:
            return True
        return bool(job.url and "indeed.com" in job.url)

    def describe_prefill(self, candidate: Candidate, job: JobPosting) -> PrefillResult:
        """Indeed Apply has its own form fields."""
        # Indeed may prefill from resume on file
        return PrefillResult(
            filled=["Resume from Indeed profile (if exists)"],
            needs_review=[
                "Complete any required fields",
                "Answer screening questions",
                "Review and submit",
            ],
        )

    def get_apply_url(self, job: JobPosting) -> str:
        """Get the Indeed apply URL.
        
        If ats_url is external (Greenhouse, Lever, etc.), return that.
        Otherwise return Indeed Apply URL.
        """
        # If job has external ATS URL, use that
        if job.ats_url and not self._is_indeed_url(job.ats_url):
            return job.ats_url
        
        # If job has Indeed ATS URL already, use it
        if job.ats_url and self._is_indeed_url(job.ats_url):
            return job.ats_url
        
        # Otherwise construct Indeed Apply URL from job URL or source_job_id
        if job.url and "jk=" in job.url:
            # Extract jk from URL
            import re
            match = re.search(r"jk=([a-f0-9]+)", job.url, re.IGNORECASE)
            if match:
                jk = match.group(1)
                host = urlparse(job.url).hostname or "www.indeed.com"
                return f"https://{host}/applystart?jk={jk}"
        
        if job.source_job_id:
            # Use source_job_id as jk
            return f"https://www.indeed.com/applystart?jk={job.source_job_id}"
        
        # Fallback to job URL
        return job.url or ""

    def _is_indeed_url(self, url: str) -> bool:
        """Check if URL is an Indeed URL."""
        parsed = urlparse(url)
        if not parsed.hostname:
            return False
        host = parsed.hostname.lower()
        return "indeed.com" in host

    def open_apply_page(self, candidate: Candidate, job: JobPosting) -> tuple[str, ApplyMethod]:
        """Open Indeed apply page (or external ATS if detected).
        
        Returns (url, method) where method indicates the apply route.
        """
        import webbrowser
        
        url = self.get_apply_url(job)
        
        # Determine if this is external ATS or Indeed Apply
        if job.ats_url and not self._is_indeed_url(job.ats_url):
            method = ApplyMethod.EXTERNAL_ATS
        else:
            method = ApplyMethod.EXTERNAL_ATS  # Indeed Apply is still external form
        
        webbrowser.open(url)
        return url, method
