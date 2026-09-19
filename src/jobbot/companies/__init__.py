"""Company ↔ career platform knowledge: discovery, provenance, candidate → promote."""

from jobbot.companies.discovery import SiteClassification, career_root_url, classify_url
from jobbot.companies.models import (
    CareerSite,
    CareerSiteType,
    CompanyRecord,
    DiscoverySource,
    KnowledgeStatus,
    Observation,
)
from jobbot.companies.recon import ReconResult, make_observation, recon_from_fixture, recon_from_html
from jobbot.companies.registry import (
    CompanyRegistry,
    ObserveOutcome,
    active_career_sites,
    default_companies_path,
    generated_candidates_path,
    load_companies,
    save_companies,
    shareable_payload,
    shared_export_path,
)
from jobbot.companies.urls import PrivateRouteRejected, canonical_key, public_url

__all__ = [
    "CareerSite",
    "CareerSiteType",
    "CompanyRecord",
    "CompanyRegistry",
    "DiscoverySource",
    "KnowledgeStatus",
    "Observation",
    "ObserveOutcome",
    "PrivateRouteRejected",
    "ReconResult",
    "SiteClassification",
    "active_career_sites",
    "canonical_key",
    "career_root_url",
    "classify_url",
    "default_companies_path",
    "generated_candidates_path",
    "load_companies",
    "make_observation",
    "public_url",
    "recon_from_fixture",
    "recon_from_html",
    "save_companies",
    "shareable_payload",
    "shared_export_path",
]
