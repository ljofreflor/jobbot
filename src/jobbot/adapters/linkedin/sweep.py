"""Parse LinkedIn recruiter posts into job-shaped records (no invention)."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from jobbot.jobs.parsing import extract_skills_from_text
from jobbot.models.job import JobPosting
from jobbot.portals.detect import AtsKind, extract_http_urls, first_external_ats_url
from jobbot.portals.email_apply import first_apply_email, mailto_url
from jobbot.portals.redirect import expand_urls

# Roles / themes relevant to this candidate's data career (title-agnostic filter)
_DATA_ROLE_HINTS = (
    "data scientist",
    "data science",
    "machine learning",
    "ml engineer",
    "mlops",
    "analytics",
    "analítica",
    "analitica",
    "científico de datos",
    "cientifico de datos",
    "estadíst",
    "estadist",
    "causal",
    "experimentation",
    "a/b test",
    "ab test",
    "data engineer",
    "bi ",
    "business intelligence",
    "applied scientist",
    "research scientist",
    "hiring",
    "we're hiring",
    "estamos buscando",
    "buscamos",
    "vacante",
    "oferta",
)


@dataclass(frozen=True)
class LinkedInPostCandidate:
    """One recruiter post before it becomes a JobPosting."""

    post_id: str
    text: str
    author: str | None = None
    post_url: str | None = None
    ats_url: str | None = None
    ats_kind: AtsKind = AtsKind.UNKNOWN


def is_data_relevant(text: str) -> bool:
    lowered = text.casefold()
    return any(hint in lowered for hint in _DATA_ROLE_HINTS)


def parse_post_blob(
    blob: str,
    *,
    author: str | None = None,
    post_url: str | None = None,
) -> LinkedInPostCandidate:
    """Parse a single post body (fixture or scraped text)."""
    text = blob.strip()
    urls = expand_urls(extract_http_urls(text))
    ats_url, ats_kind = first_external_ats_url(urls)
    if ats_url is None:
        email = first_apply_email(text)
        if email:
            ats_url = mailto_url(email)
            ats_kind = AtsKind.EMAIL
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]  # noqa: S324 — id only
    post_id = digest
    if post_url:
        post_id = hashlib.sha1(post_url.encode("utf-8")).hexdigest()[:12]  # noqa: S324
    return LinkedInPostCandidate(
        post_id=post_id,
        text=text,
        author=author,
        post_url=post_url,
        ats_url=ats_url,
        ats_kind=ats_kind,
    )


def parse_posts_fixture(text: str) -> list[LinkedInPostCandidate]:
    """Split a multi-post fixture separated by '---' lines."""
    chunks = re.split(r"\n-{3,}\n", text.strip())
    out: list[LinkedInPostCandidate] = []
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        author = None
        post_url = None
        body_lines: list[str] = []
        for line in chunk.splitlines():
            if line.lower().startswith("author:"):
                author = line.split(":", 1)[1].strip()
            elif line.lower().startswith("url:"):
                post_url = line.split(":", 1)[1].strip()
            else:
                body_lines.append(line)
        body = "\n".join(body_lines).strip()
        if body:
            out.append(parse_post_blob(body, author=author, post_url=post_url))
    return out


def post_to_job(post: LinkedInPostCandidate, *, job_id: str = "PENDING") -> JobPosting:
    """Map a post to JobPosting; description is the post body (JD = anuncio)."""
    title = _guess_title(post.text) or "Role from LinkedIn post"
    company = post.author or _guess_company(post.text) or "Unknown company"
    note = None
    if post.ats_url:
        note = f"ats={post.ats_kind.value}"
    return JobPosting(
        id=job_id,
        source="linkedin_post",
        source_job_id=post.post_id,
        url=post.post_url,
        title=title,
        company=company,
        description=post.text,
        raw_description=post.text,
        skills=extract_skills_from_text(post.text),
        ats_url=post.ats_url,
        ats_kind=post.ats_kind.value if post.ats_url else None,
        note=note,
    )


def _guess_title(text: str) -> str | None:
    patterns = [
        (
            r"(?i)(?:hiring|buscamos|looking for|we(?:'re| are) looking for)\s+"
            r"(?:a|an|un|una)?\s*([^\n.!?]{8,80})"
        ),
        r"(?i)(?:role|puesto|cargo)\s*[:\-]\s*([^\n]{5,80})",
        r"(?i)\b((?:senior |staff |lead )?data scientist[^\n.!?]{0,40})",
        r"(?i)\b((?:senior |staff )?machine learning engineer[^\n.!?]{0,40})",
        r"(?i)\b((?:senior )?data engineer[^\n.!?]{0,40})",
    ]
    for pat in patterns:
        match = re.search(pat, text)
        if match:
            return re.sub(r"\s+", " ", match.group(1)).strip(" -:")[:120]
    return None


def _guess_company(text: str) -> str | None:
    match = re.search(r"(?i)(?:at|en|@)\s+([A-ZÁÉÍÓÚÑ][\w&.\- ]{1,40})", text)
    if match:
        return match.group(1).strip()[:80]
    return None
