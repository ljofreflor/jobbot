"""A routed fake web for `jobs check-open`: recorded pages by URL, every request kept."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from jobbot.adapters.workday.cxs import HttpResponse

FIXTURES = Path(__file__).resolve().parent / "check_open"
WORKDAY = Path(__file__).resolve().parent / "workday"
WORKDAY_HOST = "https://paho.wd5.myworkdayjobs.com"
WORKDAY_PATH = "/job/Off-Site/National-PAHO-Consultant---Comunicaciones_Req-06070"
WORKDAY_URL = f"{WORKDAY_HOST}/pahocareers{WORKDAY_PATH}"
WORKDAY_API = f"{WORKDAY_HOST}/wday/cxs/paho/pahocareers{WORKDAY_PATH}"
PAGE_URL = "https://careers.acme.test/jobs/1234-analista-de-datos"


def page(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def workday(name: str) -> str:
    return (WORKDAY / name).read_text(encoding="utf-8")


@dataclass
class FakeWeb:
    """Answers by exact URL; robots.txt is absent (404) unless routed; anything else 599."""

    routes: dict[str, list[HttpResponse]] = field(default_factory=dict)
    calls: list[tuple[str, dict[str, str]]] = field(default_factory=list)

    def route(self, url: str, status: int, text: str = "") -> FakeWeb:
        """Successive calls to one URL get successive answers; the last one repeats."""
        self.routes.setdefault(url, []).append(HttpResponse(status, text))
        return self

    def __call__(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        body: bytes | None,
        timeout: float,
    ) -> HttpResponse:
        self.calls.append((url, dict(headers)))
        answers = self.routes.get(url)
        if answers:
            return answers.pop(0) if len(answers) > 1 else answers[0]
        if url.endswith("/robots.txt"):
            return HttpResponse(404, "")
        return HttpResponse(599, "unrouted")

    def urls(self) -> list[str]:
        return [url for url, _ in self.calls if not url.endswith("/robots.txt")]
