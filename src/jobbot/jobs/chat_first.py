"""Chat-first JD parse: optional LLM structured extract, grounded in the text.

Uses the same ``jobbot[llm]`` + ``OPENAI_API_KEY`` path as ``cv advise --llm``.
JobBot cannot spend Cursor IDE subscription tokens; the API key is the client's.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Protocol

from jobbot.jobs.normalization import fold_text
from jobbot.jobs.parsing import parse_job_text
from jobbot.jobs.preprocess import preprocess_job_text
from jobbot.models.job import JobPosting
from jobbot.ops.pii_guard import redact

logger = logging.getLogger("jobbot.jobs.chat_first")

DEFAULT_MODEL = "gpt-4o-mini"
MODEL_ENV = "JOBBOT_LLM_MODEL"

_SYSTEM = (
    "Extract structured fields from ONE job description.\n"
    "Rules:\n"
    "- Use ONLY facts present in the JD text. Do not invent skills or employers.\n"
    "- skills: short tool/domain names the JD itself asks for (e.g. LLMs, Python).\n"
    "- Ignore LinkedIn chrome: Publicado, hashtags, reaction counts, mailto lines.\n"
    "- title and company are separate fields.\n"
    "Respond ONLY JSON:\n"
    '{"title":"…","company":"…","location":"…|null","seniority":"…|null",'
    '"skills":["…"],"requirements":["…"]}\n'
)


class ChatModelLike(Protocol):
    def invoke(self, input: Any) -> Any: ...


@dataclass(frozen=True)
class ChatFirstResult:
    job: JobPosting
    mode: str  # deterministic | llm
    preprocessed: str


def parse_job_chat_first(
    text: str,
    *,
    job_id: str,
    source: str = "manual",
    url: str | None = None,
    use_llm: bool = True,
    chat_model: ChatModelLike | None = None,
) -> ChatFirstResult:
    """Preprocess, optionally LLM-extract, else improved deterministic parse."""
    cleaned = preprocess_job_text(text)
    if use_llm:
        extracted = _llm_extract(cleaned, chat_model=chat_model)
        if extracted is not None:
            job = _job_from_extract(
                extracted,
                cleaned,
                job_id=job_id,
                source=source,
                url=url,
                original=text,
            )
            return ChatFirstResult(job=job, mode="llm", preprocessed=cleaned)
    job = parse_job_text(cleaned, job_id=job_id, source=source, url=url)
    if job.raw_description != text:
        job.raw_description = text
    return ChatFirstResult(job=job, mode="deterministic", preprocessed=cleaned)


def llm_available() -> bool:
    if not os.environ.get("OPENAI_API_KEY"):
        return False
    try:
        import langchain_openai  # noqa: F401
    except ImportError:
        return False
    return True


def _llm_extract(
    cleaned: str,
    *,
    chat_model: ChatModelLike | None,
) -> dict[str, Any] | None:
    model = chat_model
    if model is None:
        if not llm_available():
            return None
        try:
            model = _build_chat_model()
        except RuntimeError as exc:
            logger.debug("chat-first LLM unavailable: %s", exc)
            return None
    prompt = (
        f"{_SYSTEM}\n--- JD ---\n{redact(cleaned)[:12000]}\n--- end ---\n"
    )
    try:
        raw = model.invoke(prompt)
    except Exception as exc:  # noqa: BLE001 — fall back to deterministic
        logger.warning("chat-first LLM call failed: %s", exc)
        return None
    return _parse_extract(_message_content(raw))


def _build_chat_model() -> ChatModelLike:
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        msg = "LangChain extras not installed. Run: uv sync --extra llm"
        raise RuntimeError(msg) from exc
    if not os.environ.get("OPENAI_API_KEY"):
        msg = "OPENAI_API_KEY not set"
        raise RuntimeError(msg)
    model: ChatModelLike = ChatOpenAI(
        model=os.environ.get(MODEL_ENV, DEFAULT_MODEL),
        temperature=0.0,
    )
    return model


def _message_content(raw: Any) -> str:
    content = getattr(raw, "content", raw)
    if isinstance(content, list):
        parts = [
            str(item["text"]) if isinstance(item, dict) and "text" in item else str(item)
            for item in content
        ]
        return "\n".join(parts)
    return str(content)


def _parse_extract(text: str) -> dict[str, Any] | None:
    body = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", body, re.S)
    if fence:
        body = fence.group(1)
    start, end = body.find("{"), body.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(body[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _job_from_extract(
    data: dict[str, Any],
    cleaned: str,
    *,
    job_id: str,
    source: str,
    url: str | None,
    original: str,
) -> JobPosting:
    """Build a JobPosting; drop skills/requirements not grounded in the JD text."""
    folded = fold_text(cleaned)
    title = str(data.get("title") or "").strip() or "Untitled"
    company = str(data.get("company") or "").strip() or "Unknown"
    location_raw = data.get("location")
    location = str(location_raw).strip() if location_raw else None
    seniority_raw = data.get("seniority")
    seniority = str(seniority_raw).strip().casefold() if seniority_raw else None
    skills = _grounded_list(data.get("skills"), folded)
    requirements = _grounded_list(data.get("requirements"), folded, allow_long=True)
    return JobPosting(
        id=job_id,
        source=source,
        url=url,
        title=title,
        company=company,
        location=location or None,
        description=cleaned.strip(),
        raw_description=original,
        requirements=requirements,
        skills=skills,
        seniority=seniority,
    )


def _grounded_list(
    raw: object,
    folded_source: str,
    *,
    allow_long: bool = False,
) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        text = str(item).strip()
        if not text:
            continue
        if not allow_long and len(text.split()) > 6:
            continue
        needle = fold_text(text)
        # Every token of a short skill should appear; long reqs need a 4-char stem.
        if allow_long:
            ok = any(
                fold_text(word) in folded_source
                for word in re.findall(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]{4,}", text)
            )
        else:
            ok = needle in folded_source or all(
                fold_text(word) in folded_source for word in text.split() if len(word) > 2
            )
        if not ok:
            continue
        key = needle
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out
