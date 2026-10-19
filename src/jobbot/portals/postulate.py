"""Classify a post's apply route. A contribution is a host this checkout does not already know."""

from __future__ import annotations

from dataclasses import dataclass

from jobbot.adapters.linkedin.sweep import parse_post_blob
from jobbot.config import JobbotConfig
from jobbot.portals.detect import AtsKind
from jobbot.portals.knowledge import seed_portals_path
from jobbot.portals.registry import default_portals_path, domain_from_url, load_registry


@dataclass(frozen=True)
class PortalContribution:
    domain: str
    ats_kind: str
    example_url: str


@dataclass(frozen=True)
class PostulatePlan:
    route: str
    contributions: tuple[PortalContribution, ...]


def known_portal_domains(config: JobbotConfig) -> set[str]:
    """Hosts already in the local registry or the tracked seed."""
    domains: set[str] = set()
    for path in (default_portals_path(config.root), seed_portals_path()):
        registry = load_registry(path)
        domains.update(entry.domain.casefold() for entry in registry.portals)
    return domains


def plan_postulate(text: str, *, known_domains: set[str]) -> PostulatePlan:
    """Email, a portal host, or unknown. LinkedIn and a known host add no contribution."""
    post = parse_post_blob(text)
    if post.ats_kind == AtsKind.EMAIL:
        return PostulatePlan("email", ())
    url = post.ats_url or ""
    if not url or post.ats_kind == AtsKind.LINKEDIN:
        return PostulatePlan("unknown", ())
    domain = domain_from_url(url)
    if not domain or domain.casefold() in known_domains:
        return PostulatePlan("portal", ())
    kind = post.ats_kind.value if post.ats_kind != AtsKind.UNKNOWN else "unknown"
    return PostulatePlan(
        "portal",
        (PortalContribution(domain, kind, url),),
    )


def render_plan(plan: PostulatePlan) -> list[str]:
    lines = [f"route: {plan.route}"]
    if not plan.contributions:
        lines.append("contributions: 0")
        return lines
    for item in plan.contributions:
        lines.append(f"contribution: {item.domain} {item.ats_kind} {item.example_url}")
    return lines
