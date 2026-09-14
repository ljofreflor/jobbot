"""Parse ExternalProfile from HTML fixtures or live pages."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from jobbot.models.external_profile import (
    ExternalEducation,
    ExternalExperience,
    ExternalProfile,
)


def parse_indeed_profile_html(html: str) -> ExternalProfile:
    headline = _meta(html, "headline") or _tag_text(html, "h1")
    summary = _meta(html, "summary") or _section(html, "summary")
    location = _meta(html, "location")
    skills = _list_items(html, "skills")
    experience = _experiences(html)
    education = _educations(html)
    return ExternalProfile(
        source="indeed",
        headline=headline,
        summary=summary,
        location=location,
        experience=experience,
        education=education,
        skills=skills,
        captured_at=datetime.now(UTC),
    )


def parse_linkedin_profile_html(html: str) -> ExternalProfile:
    headline = _meta(html, "headline") or _tag_text(html, "h1")
    summary = _meta(html, "about") or _section(html, "about")
    location = _meta(html, "location")
    skills = _list_items(html, "skills")
    return ExternalProfile(
        source="linkedin",
        headline=headline,
        summary=summary,
        location=location,
        experience=_experiences(html),
        education=_educations(html),
        skills=skills,
        captured_at=datetime.now(UTC),
    )


def load_external_from_file(path: Path, source: str) -> ExternalProfile:
    html = path.read_text(encoding="utf-8")
    if source == "indeed":
        return parse_indeed_profile_html(html)
    return parse_linkedin_profile_html(html)


def _meta(html: str, name: str) -> str | None:
    match = re.search(
        rf'data-testid="{re.escape(name)}"[^>]*>(.*?)</',
        html,
        flags=re.I | re.S,
    )
    if match:
        return _clean(match.group(1))
    match = re.search(
        rf'<meta\s+name="{re.escape(name)}"\s+content="([^"]+)"',
        html,
        flags=re.I,
    )
    return match.group(1).strip() if match else None


def _tag_text(html: str, tag: str) -> str | None:
    match = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", html, flags=re.I | re.S)
    return _clean(match.group(1)) if match else None


def _section(html: str, section_id: str) -> str | None:
    match = re.search(
        rf'id="{re.escape(section_id)}"[^>]*>(.*?)</section>',
        html,
        flags=re.I | re.S,
    )
    return _clean(match.group(1)) if match else None


def _list_items(html: str, section_id: str) -> list[str]:
    match = re.search(
        rf'id="{re.escape(section_id)}"[^>]*>(.*?)</(?:ul|section|div)>',
        html,
        flags=re.I | re.S,
    )
    if not match:
        return []
    items = re.findall(r"<li[^>]*>(.*?)</li>", match.group(1), flags=re.I | re.S)
    return [_clean(x) for x in items]


def _experiences(html: str) -> list[ExternalExperience]:
    blocks = re.findall(
        r'data-testid="experience-item"(.*?)</article>',
        html,
        flags=re.I | re.S,
    )
    result: list[ExternalExperience] = []
    for block in blocks:
        result.append(
            ExternalExperience(
                title=_attr_or_class(block, "title"),
                company=_attr_or_class(block, "company"),
                location=_attr_or_class(block, "location"),
                description=_attr_or_class(block, "description"),
            )
        )
    return result


def _educations(html: str) -> list[ExternalEducation]:
    blocks = re.findall(
        r'data-testid="education-item"(.*?)</article>',
        html,
        flags=re.I | re.S,
    )
    result: list[ExternalEducation] = []
    for block in blocks:
        result.append(
            ExternalEducation(
                degree=_attr_or_class(block, "degree"),
                institution=_attr_or_class(block, "institution"),
            )
        )
    return result


def _attr_or_class(block: str, name: str) -> str | None:
    match = re.search(
        rf'data-testid="{re.escape(name)}"[^>]*>(.*?)</',
        block,
        flags=re.I | re.S,
    )
    return _clean(match.group(1)) if match else None


def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()
