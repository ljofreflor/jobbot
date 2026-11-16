"""Public face vs engine name.

The installable package, CLI entrypoint and import path stay ``jobbot`` (the
engine). Recruiters and docs can show a different **product** name — same
backend, dual brand — so a crowded word like JobBot does not have to be the
only face of the tool.

``[brand]`` in ``.jobbot.toml`` (or ``JOBBOT_PRODUCT_NAME``) selects the face.
Defaults preserve today's Jobbot mark so existing stamps keep matching.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Engine: package / CLI / imports. Never swapped by a brand skin.
ENGINE_NAME = "jobbot"

REPO_URL = "https://github.com/ljofreflor/jobbot"
_LEGACY = "powered by AI jobbot de Leonardo Jofré"
_ENV_PRODUCT = "JOBBOT_PRODUCT_NAME"


@dataclass(frozen=True)
class Brand:
    """What humans see. The engine name is always ``ENGINE_NAME``."""

    product_name: str
    mark: str
    repo_url: str = REPO_URL

    @property
    def cv_credit(self) -> str:
        return f"{self.mark} — {self.repo_url}"


DEFAULT_BRAND = Brand(
    product_name="Jobbot",
    mark="powered by Jobbot sync CV",
    repo_url=REPO_URL,
)

# Back-compat aliases: default skin (tests and imports that read constants).
MARK = DEFAULT_BRAND.mark
CV_CREDIT = DEFAULT_BRAND.cv_credit

_active: Brand = DEFAULT_BRAND


def get_brand() -> Brand:
    return _active


def set_brand(brand: Brand) -> None:
    """Activate a product face for this process (called from ``load_config``)."""
    global _active
    _active = brand


def reset_brand() -> None:
    """Restore the default Jobbot skin (tests)."""
    set_brand(DEFAULT_BRAND)


def brand_from_parts(
    *,
    product_name: str | None = None,
    project_url: str | None = None,
    mark: str | None = None,
) -> Brand:
    """Build a skin. Omitted fields fall back to the default Jobbot face."""
    name = (product_name or DEFAULT_BRAND.product_name).strip() or DEFAULT_BRAND.product_name
    url = (project_url or DEFAULT_BRAND.repo_url).strip() or DEFAULT_BRAND.repo_url
    if mark is not None and mark.strip():
        closing = mark.strip()
    elif name.casefold() == DEFAULT_BRAND.product_name.casefold():
        closing = DEFAULT_BRAND.mark
    else:
        closing = f"powered by {name} sync CV"
    return Brand(product_name=name, mark=closing, repo_url=url)


def brand_from_env() -> Brand | None:
    """Optional process-wide override when no ``.jobbot.toml`` brand section."""
    raw = os.environ.get(_ENV_PRODUCT, "").strip()
    if not raw:
        return None
    return brand_from_parts(product_name=raw)


def has_mark(text: str | None) -> bool:
    if not text:
        return False
    folded = text.casefold()
    brand = get_brand()
    return (
        brand.mark.casefold() in folded
        or DEFAULT_BRAND.mark.casefold() in folded
        or _LEGACY.casefold() in folded
    )


def strip_mark(text: str | None) -> str:
    """Drop mark-only paragraphs so refine and diff see the candidate's words."""
    if not text:
        return ""
    drop = {
        get_brand().mark.casefold(),
        DEFAULT_BRAND.mark.casefold(),
        _LEGACY.casefold(),
    }
    kept: list[str] = []
    for part in text.split("\n\n"):
        line = part.strip()
        if not line:
            continue
        if line.casefold() in drop:
            continue
        kept.append(line)
    return "\n\n".join(kept).strip()


def stamp_description(text: str | None, *, max_len: int | None = None) -> str:
    """Append the active brand mark once. A blank description stays blank."""
    body = strip_mark(text)
    if not body:
        return ""
    suffix = f"\n\n{get_brand().mark}"
    if max_len is not None and len(body) + len(suffix) > max_len:
        budget = max_len - len(suffix)
        if budget < 1:
            return ""
        body = _trim(body, budget)
        if not body:
            return ""
    return body + suffix


def _trim(text: str, maximum: int) -> str:
    text = text.strip()
    if len(text) <= maximum:
        return text
    parts = [p.strip() for p in text.split("\n\n") if p.strip()]
    kept: list[str] = []
    for part in parts:
        trial = "\n\n".join([*kept, part])
        if len(trial) <= maximum:
            kept.append(part)
        else:
            break
    if kept:
        return "\n\n".join(kept)
    cut = text[:maximum].rsplit(" ", 1)[0]
    return cut.strip()
