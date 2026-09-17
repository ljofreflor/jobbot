"""Torre discovery: structured requirements in, no third-party names out."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from jobbot.adapters.torre.jobs import (
    API_SEARCH,
    TorreJobSource,
    job_from_api_item,
    search_opportunities,
)
from jobbot.config import JobbotConfig
from jobbot.jobs.sources import JobSearchQuery
from jobbot.portals.detect import AtsKind


@pytest.fixture
def payload(project_root: Path) -> dict[str, Any]:
    raw = (project_root / "tests" / "fixtures" / "torre_search.json").read_text(encoding="utf-8")
    return json.loads(raw)


class FakeFetcher:
    """Records the request and replays the fixture: no network in tests."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def post_json(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((url, body))
        return self.payload


def test_search_asks_for_the_role_and_maps_every_result(payload: dict[str, Any]) -> None:
    fetcher = FakeFetcher(payload)

    items = search_opportunities("analista de datos", size=3, fetcher=fetcher)

    url, body = fetcher.calls[0]
    assert url.startswith(API_SEARCH)
    assert body["skill/role"]["text"] == "analista de datos"
    assert "remote" not in body, "remote is a filter the user asks for, not a default"
    assert len(items) == 4


def test_remote_flag_becomes_a_filter(payload: dict[str, Any]) -> None:
    fetcher = FakeFetcher(payload)

    search_opportunities("analista", remote=True, fetcher=fetcher)

    assert fetcher.calls[0][1]["remote"] == {"term": True}


def test_requirements_come_from_the_payload_not_from_prose(payload: dict[str, Any]) -> None:
    job = job_from_api_item(payload["results"][0])

    assert job.skills == ["SQL", "Python", "Data visualization"]
    # The required experience is part of what the portal states.
    assert "3 plus years" in job.description
    assert job.title == "Analista de Datos"
    assert job.company == "Estudio Neutro"


def test_a_posting_never_carries_the_names_of_the_people_behind_it(
    payload: dict[str, Any],
) -> None:
    """`members` are third parties: PII that must not enter the local store."""
    for item in payload["results"]:
        job = job_from_api_item(item)
        blob = " ".join(
            str(part)
            for part in (job.description, job.raw_description, job.company, job.note, job.url)
        )
        for member in item.get("members") or []:
            assert member["name"] not in blob
            assert member["username"] not in blob


def test_the_url_is_the_public_post(payload: dict[str, Any]) -> None:
    job = job_from_api_item(payload["results"][0])

    assert job.url == "https://torre.ai/post/aB1cD2eF-estudio-neutro-analista-de-datos"
    assert job.ats_kind == AtsKind.TORRE.value
    assert job.source == "torre"
    assert job.source_job_id == "aB1cD2eF"


def test_an_opportunity_hosted_on_an_ats_points_at_that_ats(payload: dict[str, Any]) -> None:
    job = job_from_api_item(payload["results"][1])

    assert job.url == "https://boards.greenhouse.io/clinicaneutra/jobs/4455"
    assert job.ats_kind == AtsKind.GREENHOUSE.value


def test_remote_and_location_are_read_from_place(payload: dict[str, Any]) -> None:
    remote_job = job_from_api_item(payload["results"][0])
    onsite_job = job_from_api_item(payload["results"][1])

    assert remote_job.remote_type == "fully_remote"
    assert remote_job.location == "Remote / anywhere"
    assert onsite_job.remote_type == "on_site"
    assert onsite_job.location == "Santiago, Chile"


def test_a_country_restricted_remote_role_names_its_countries(
    payload: dict[str, Any],
) -> None:
    """place.location holds objects, so the raw dicts used to reach the table."""
    job = job_from_api_item(payload["results"][3])

    assert job.location == "United States, Canada"
    assert "{" not in (job.location or ""), "a serialized dict leaked into the location"
    assert "{" not in job.description
    # A remote role tied to countries is not open to anywhere.
    assert job.remote_type == "remote_countries"


def test_dates_travel_so_freshness_can_filter(payload: dict[str, Any]) -> None:
    job = job_from_api_item(payload["results"][0])

    assert job.posted_at is not None
    assert job.posted_at.year == 2026
    assert job.posted_at.month == 9


def test_an_unparsable_date_is_dropped_not_guessed(payload: dict[str, Any]) -> None:
    job = job_from_api_item(payload["results"][2])

    assert job.posted_at is None


def test_a_result_without_organization_still_yields_a_usable_job(
    payload: dict[str, Any],
) -> None:
    job = job_from_api_item(payload["results"][2])

    assert job.title == "Redactor de Contenidos"
    assert job.company
    assert job.skills == []
    assert job.url.endswith("mN5oP6qR-sin-organizacion")


def test_compensation_is_reported_when_the_portal_shows_it(payload: dict[str, Any]) -> None:
    job = job_from_api_item(payload["results"][0])

    assert "USD$" in job.description
    assert "3000" in job.description.replace(".0", "")


def test_source_learns_the_portal_once(
    payload: dict[str, Any], tmp_path: Path, project_root: Path
) -> None:
    config = JobbotConfig(root=tmp_path)
    (tmp_path / "data").mkdir(exist_ok=True)
    source = TorreJobSource(config, fetcher=FakeFetcher(payload))

    jobs = source.search_jobs(JobSearchQuery(query="analista de datos", limit=3))

    assert len(jobs) == 4
    from jobbot.portals.registry import default_portals_path, load_registry

    registry = load_registry(default_portals_path(tmp_path))
    assert [p.domain for p in registry.portals] == ["torre.ai"]
    assert registry.portals[0].ats_kind == AtsKind.TORRE
