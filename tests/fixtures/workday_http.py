"""A fake Workday host for tests: serves recorded CXS fixtures, records every request."""

from __future__ import annotations

import copy
import json
import socket
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from jobbot.adapters.workday.cxs import HttpResponse

FIXTURES = Path(__file__).resolve().parent / "workday"
SITE_URL = "https://paho.wd5.myworkdayjobs.com/en-US/pahocareers"
API = "https://paho.wd5.myworkdayjobs.com/wday/cxs/paho/pahocareers"
OPEN_PATH = "/job/Off-Site/National-PAHO-Consultant---Comunicaciones_Req-06070"


def load_json(name: str) -> dict[str, Any]:
    data = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@dataclass
class Call:
    method: str
    url: str
    headers: dict[str, str]
    body: dict[str, Any] | None


@dataclass
class FakeWorkday:
    """Routes by URL. ``pages`` answers successive search offsets; details by path."""

    robots: str | None = None
    robots_status: int = 200
    pages: list[dict[str, Any]] = field(default_factory=list)
    search_status: int = 200
    details: dict[str, tuple[int, str]] = field(default_factory=dict)
    calls: list[Call] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.robots is None:
            self.robots = fixture_text("robots.txt")

    def detail(self, path: str, payload: Mapping[str, Any], status: int = 200) -> None:
        self.details[path] = (status, json.dumps(payload))

    def __call__(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        body: bytes | None,
        timeout: float,
    ) -> HttpResponse:
        parsed = json.loads(body) if body else None
        self.calls.append(Call(method, url, dict(headers), parsed))
        if url.endswith("/robots.txt"):
            return HttpResponse(self.robots_status, self.robots or "")
        if method == "POST" and url.endswith("/jobs"):
            if self.search_status != 200:
                return HttpResponse(self.search_status, fixture_text("error_403_s22.json"))
            offset = int((parsed or {}).get("offset", 0))
            index = offset // 20
            page = self.pages[index] if index < len(self.pages) else self.pages[0]
            return HttpResponse(200, json.dumps(page))
        for path, (status, text) in self.details.items():
            if url.endswith(path):
                return HttpResponse(status, text)
        return HttpResponse(404, fixture_text("error_404.json"))

    @property
    def cxs_calls(self) -> list[Call]:
        return [c for c in self.calls if "/wday/cxs/" in c.url]


def paged_search(total: int, *, per_page: int = 20) -> list[dict[str, Any]]:
    """``total`` postings over pages of 20, cloned from the recorded row (later pages say 0)."""
    row = load_json("search_page1.json")["jobPostings"][1]
    pages: list[dict[str, Any]] = []
    for start in range(0, total, per_page):
        items = []
        for n in range(start, min(total, start + per_page)):
            item = copy.deepcopy(row)
            item["externalPath"] = f"/job/Off-Site/Consultant-{n:03d}_Req-{n:05d}"
            item["bulletFields"] = [f"Req-{n:05d}"]
            item["title"] = f"Consultant {n:03d}"
            items.append(item)
        pages.append({"total": total if start == 0 else 0, "jobPostings": items, "facets": []})
    return pages


def serve_every_detail(fake: FakeWorkday, page: dict[str, Any]) -> None:
    """One recorded detail, retitled per search row, so every row has a readable detail."""
    for row in page["jobPostings"]:
        payload = load_json("detail_open.json")
        info = payload["jobPostingInfo"]
        info["title"] = row["title"]
        info["externalUrl"] = "https://paho.wd5.myworkdayjobs.com/pahocareers" + row["externalPath"]
        fake.detail(row["externalPath"], payload)


def install(monkeypatch: pytest.MonkeyPatch, fake: FakeWorkday) -> FakeWorkday:
    import jobbot.adapters.workday.cxs as cxs

    monkeypatch.setattr(cxs, "urllib_runner", fake)
    monkeypatch.setattr(cxs, "pause", lambda _seconds: None)
    return fake


def forbid_sockets(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("tests must not open a socket")

    monkeypatch.setattr(socket.socket, "connect", refuse)
