"""Parse LinkedIn recruiter posts into job-shaped records (no invention)."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlparse

from jobbot.jobs.parsing import extract_skills_from_text
from jobbot.models.job import JobPosting
from jobbot.portals.detect import AtsKind, detect_ats, extract_http_urls, first_external_ats_url
from jobbot.portals.email_apply import first_apply_email, mailto_url
from jobbot.portals.redirect import expand_url_map

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
class PostVacancy:
    """One labelled vacancy link inside a recruiter post ("Lead Data Scientist: <url>")."""

    title: str
    url: str
    ats_kind: AtsKind = AtsKind.UNKNOWN


@dataclass(frozen=True)
class LinkedInPostCandidate:
    """One recruiter post before it becomes a JobPosting."""

    post_id: str
    text: str
    author: str | None = None
    post_url: str | None = None
    ats_url: str | None = None
    ats_kind: AtsKind = AtsKind.UNKNOWN
    posted_at: datetime | None = None
    vacancies: tuple[PostVacancy, ...] = ()


# LinkedIn activity ids carry their creation time in the high bits: ms = id >> 22.
_ACTIVITY_ID_RE = re.compile(r"(?:activity|share|ugcPost)[-:](\d{15,25})", re.IGNORECASE)
_LINKEDIN_EPOCH_START = datetime(2005, 1, 1, tzinfo=UTC)


def posted_at_from_url(url: str | None) -> datetime | None:
    """
    Publication date of a post, read from the activity id in its own URL.

    Works for `/posts/…-activity-<id>-xxxx`, `/posts/…-share-<id>-xxxx` and
    `feed/update/urn:li:{activity,share,ugcPost}:<id>`, which share the same id encoding.
    Returns None for anything else (e.g. the author-profile fallback), so a post is
    never given an invented date.
    """
    match = _ACTIVITY_ID_RE.search(url or "")
    if match is None:
        return None
    try:
        moment = datetime.fromtimestamp((int(match.group(1)) >> 22) / 1000, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None
    if moment < _LINKEDIN_EPOCH_START:
        return None
    return moment


_FEED_HEADERS = ("publicación en el feed", "publicacion en el feed", "feed post")
_CHROME_LINE = re.compile(
    r"^(?:•\s*\d+\S*|seguir|follow|recomendar|editado.*"
    r"|\d+\s*(?:min|h|d|sem|mes(?:es)?|año(?:s)?)\b.*)$",
    re.IGNORECASE,
)
_CHROME_WINDOW = 5

# Engagement UI around the post: exact lines LinkedIn renders, never post content.
_ENGAGEMENT_LINE = re.compile(
    r"^(?:\d+[\d.,\s]*"
    r"(?:reacci(?:ón|on|ones)|comentario(?:s)?|comment(?:s)?|reaction(?:s)?|"
    r"veces compartido|compartido(?:s)?|repost(?:s)?)"
    r"|recomendar|comentar|compartir|enviar|like|comment|share|send|repost"
    r"|ver traducción|ver traduccion|see translation"
    r"|\d+[\d.,\s]*$"
    r"|.{0,40}\ben linkedin\.com$)$",
    re.IGNORECASE,
)


def strip_engagement_chrome(lines: list[str]) -> list[str]:
    """Drop reaction / comment / share lines that LinkedIn paints around a post."""
    return [line for line in lines if not _ENGAGEMENT_LINE.match(line.strip())]


def strip_feed_chrome(text: str) -> tuple[str | None, str]:
    """
    Split LinkedIn's card header from the actual post body.

    Returns (author, body). Author is the name LinkedIn shows above the post;
    only the first few lines are cleaned so bullet content in the post survives,
    while engagement lines are dropped wherever they appear.
    """
    lines = [line.strip() for line in text.splitlines()]
    if not lines or lines[0].casefold() not in _FEED_HEADERS:
        return None, "\n".join(strip_engagement_chrome(lines)).strip()
    rest = [line for line in lines[1:] if line]
    if not rest:
        return None, ""
    author = rest[0]
    head = [line for line in rest[1 : 1 + _CHROME_WINDOW] if not _CHROME_LINE.match(line)]
    body = strip_engagement_chrome(head + rest[1 + _CHROME_WINDOW :])
    return author, "\n".join(body).strip()


def is_data_relevant(text: str) -> bool:
    lowered = text.casefold()
    return any(hint in lowered for hint in _DATA_ROLE_HINTS)


# A post offering several roles lists them as "🔹 Lead Data Scientist: <url>". Cards keep one
# bullet per line, but a collapsed paragraph puts them all on one, so split on both.
_VACANCY_SEGMENT_RE = re.compile(r"[\r\n]+|(?=[🔹🔸🔷🔶🟢🟣▪◾◽•])")
_VACANCY_LINE_RE = re.compile(
    r"^(?P<label>[^\n]{4,90}?)\s*[:\-–—]\s*(?P<url>https?://\S+)",
)
_VACANCY_LABEL_TRIM_RE = re.compile(r"^[^\w(¿¡]+|[\s\-–—:]+$")

# Words that make a label a job title. Without one, a labelled link is just a link
# ("Learn more: …", "Our careers page: …") and never becomes a vacancy.
_ROLE_WORDS = (
    "scientist",
    "engineer",
    "consultant",
    "analyst",
    "developer",
    "architect",
    "specialist",
    "researcher",
    "manager",
    "administrator",
    "cient[íi]fic",
    "ingenier",
    "analista",
    "desarrollador",
    "arquitect",
    "especialista",
    "investigador",
    "jefe",
    "l[íi]der",
)
_ROLE_WORD_RE = re.compile("|".join(_ROLE_WORDS), re.IGNORECASE)


def split_vacancy_links(text: str, url_map: dict[str, str] | None = None) -> list[PostVacancy]:
    """
    Labelled vacancy links in a post, in the order the recruiter listed them.

    ``url_map`` carries each link's resolved destination. A link that still points at
    LinkedIn is dropped: the post's own roles are only appliable through the external
    page, and storing a lnkd.in URL would teach the portal registry a shortener.
    """
    resolved_by_raw = url_map or {}
    out: list[PostVacancy] = []
    seen: set[str] = set()
    for segment in _VACANCY_SEGMENT_RE.split(text or ""):
        match = _VACANCY_LINE_RE.match(segment.strip())
        if match is None:
            continue
        label = _VACANCY_LABEL_TRIM_RE.sub("", match.group("label")).strip()
        if not label or not _ROLE_WORD_RE.search(label):
            continue
        raw_url = match.group("url").rstrip(".,;:)")
        url = resolved_by_raw.get(raw_url, raw_url)
        kind = detect_ats(url)
        if kind == AtsKind.LINKEDIN or _is_linkedin_shortener(url):
            continue
        if url in seen:
            continue
        seen.add(url)
        out.append(PostVacancy(title=label, url=url, ats_kind=kind))
    return out


def _is_linkedin_shortener(url: str) -> bool:
    host = (urlparse(url if "://" in url else f"https://{url}").hostname or "").casefold()
    return host == "lnkd.in" or host.endswith(".lnkd.in")


def parse_post_blob(
    blob: str,
    *,
    author: str | None = None,
    post_url: str | None = None,
    mailto_urls: Sequence[str] | None = None,
    extra_urls: Sequence[str] | None = None,
) -> LinkedInPostCandidate:
    """
    Parse a single post body (fixture or scraped text).

    `extra_urls` are the card's anchors: they feed ATS detection without entering
    the description, which must read like the advert the recruiter wrote.
    """
    header_author, text = strip_feed_chrome(blob.strip())
    author = author or header_author
    url_map = expand_url_map(extract_http_urls(text) + [u for u in (extra_urls or []) if u])
    urls = _both_ends(url_map)
    vacancies = split_vacancy_links(text, url_map)
    ats_url, ats_kind = first_external_ats_url(urls)
    if ats_url is None:
        email = first_apply_email(text)
        if email:
            ats_url = mailto_url(email)
            ats_kind = AtsKind.EMAIL
    if ats_url is None and mailto_urls:
        # Address only reachable through the post's mailto link, not its text.
        first = next((m for m in mailto_urls if "@" in m), None)
        if first:
            ats_url = first if first.startswith("mailto:") else mailto_url(first)
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
        posted_at=posted_at_from_url(post_url),
        vacancies=tuple(vacancies),
    )


def _both_ends(url_map: dict[str, str]) -> list[str]:
    """Raw and resolved URLs, deduped, in the order they appeared."""
    out: list[str] = []
    seen: set[str] = set()
    for raw, resolved in url_map.items():
        for candidate in (raw, resolved):
            if candidate and candidate not in seen:
                seen.add(candidate)
                out.append(candidate)
    return out


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
    company = employer_from_post(post.text, post.ats_url, author=post.author)
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
        posted_at=post.posted_at,
        skills=extract_skills_from_text(post.text),
        ats_url=post.ats_url,
        ats_kind=post.ats_kind.value if post.ats_url else None,
        note=note,
    )


def post_to_jobs(post: LinkedInPostCandidate) -> list[JobPosting]:
    """
    One JobPosting per vacancy the post lists, or a single job for the whole post.

    A recruiter offering five roles behind five links is five applications: collapsing
    them leaves four unreachable, since a job carries one apply URL.
    """
    if len(post.vacancies) < 2:
        return [post_to_job(post)]
    company = employer_from_post(post.text, post.vacancies[0].url, author=post.author)
    skills = extract_skills_from_text(post.text)
    jobs: list[JobPosting] = []
    for vacancy in post.vacancies:
        note = f"ats={vacancy.ats_kind.value}"
        if post.post_url:
            note = f"{note} post={post.post_url}"
        jobs.append(
            JobPosting(
                id="PENDING",
                source="linkedin_post",
                source_job_id=_vacancy_source_id(vacancy.url),
                url=vacancy.url,
                title=vacancy.title,
                company=company,
                description=post.text,
                raw_description=post.text,
                posted_at=post.posted_at,
                skills=skills,
                ats_url=vacancy.url,
                ats_kind=vacancy.ats_kind.value,
                note=note,
            )
        )
    return jobs


def _vacancy_source_id(url: str) -> str:
    """Keyed on the vacancy page, so the same role found twice stays one job."""
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]  # noqa: S324 — id only


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


# Legal forms and industry words: alone they never identify one employer.
_GENERIC_NAME_TOKENS: frozenset[str] = frozenset(
    {
        "chile",
        "colombia",
        "consulting",
        "corp",
        "digital",
        "global",
        "group",
        "labs",
        "latam",
        "llc",
        "ltda",
        "services",
        "solutions",
        "technologies",
        "technology",
    }
)


def employer_from_post(text: str, apply_url: str | None, *, author: str | None) -> str:
    """
    Employer behind a recruiter post, preferring corroborated evidence.

    Whoever writes a hiring post is usually a recruiter, not the company, so the author
    is a poor employer name — but it is the only one available most of the time. When the
    post names a company *and* the apply URL carries that name, the two agree and the
    employer is a fact; otherwise the author stands, as before.
    """
    named = _guess_company(text)
    if named and apply_url and _apply_url_names(apply_url, named):
        return named
    return author or named or "Unknown company"


def _apply_url_names(url: str, company: str) -> bool:
    """Whether the apply host (or mail domain) carries the company's name."""
    from jobbot.companies.urls import slugify

    raw = url.strip()
    if raw.casefold().startswith("mailto:"):
        host = raw.partition("@")[2]
    else:
        host = urlparse(raw if "://" in raw else f"https://{raw}").hostname or ""
    flattened = re.sub(r"[^a-z0-9]", "", host.casefold())
    slug = slugify(company)
    if len(slug) >= 4 and slug.replace("-", "") in flattened:
        return True
    tokens = [t for t in slug.split("-") if len(t) >= 5 and t not in _GENERIC_NAME_TOKENS]
    return any(token in flattened for token in tokens)
