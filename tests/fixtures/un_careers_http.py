"""A fake careers.un.org for tests: serves recorded fixtures, records every request."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest

FIXTURES = Path(__file__).resolve().parent / "un_careers"


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@dataclass
class FakeUnCareers:
    """Routes by path: ``/robots.txt``, ``/jobfeed``, ``/api/public/opening/jo/{id}/en``."""

    robots: str = field(default_factory=lambda: fixture_text("robots_spa.html"))
    robots_type: str = "text/html; charset=UTF-8"
    robots_status: int = 200
    feed: str = field(default_factory=lambda: fixture_text("jobfeed.xml"))
    feed_status: int = 200
    details: dict[str, tuple[int, str]] = field(default_factory=dict)
    calls: list[httpx.Request] = field(default_factory=list)

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        path = request.url.path
        if path == "/robots.txt":
            headers = {"content-type": self.robots_type}
            return httpx.Response(self.robots_status, text=self.robots, headers=headers)
        if path == "/jobfeed":
            headers = {"content-type": "text/xml; charset=utf-8"}
            return httpx.Response(self.feed_status, text=self.feed, headers=headers)
        for job_id, (status, text) in self.details.items():
            if path == f"/api/public/opening/jo/{job_id}/en":
                return httpx.Response(status, text=text)
        return httpx.Response(404, text="{}")

    def paths(self) -> list[str]:
        return [request.url.path for request in self.calls]

    @property
    def detail_calls(self) -> list[str]:
        return [p for p in self.paths() if p.startswith("/api/")]


def install(monkeypatch: pytest.MonkeyPatch, fake: FakeUnCareers) -> FakeUnCareers:
    import jobbot.adapters.un_careers.feed as feed

    transport = httpx.MockTransport(fake.handle)

    def client(**kwargs: Any) -> httpx.Client:
        return httpx.Client(**{**kwargs, "transport": transport})

    monkeypatch.setattr(feed, "_client", client)
    monkeypatch.setattr(feed, "pause", lambda _seconds: None)
    return fake
