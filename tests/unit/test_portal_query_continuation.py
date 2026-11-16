"""One failed portal query does not cancel the queries that still run."""

from __future__ import annotations

import pytest
import typer

from jobbot.cli import _run_portal_queries
from jobbot.exit_codes import GENERIC_FAILURE
from jobbot.models.job import JobPosting


def _job() -> JobPosting:
    return JobPosting(id="J0001", title="Coordinador", company="Servicio Neutro", description="")


def test_one_failed_query_keeps_the_rest(capsys: pytest.CaptureFixture[str]) -> None:
    calls: list[str] = []

    def search(text: str) -> list[JobPosting]:
        calls.append(text)
        if text == "primera":
            raise RuntimeError("down")
        return [_job()]

    found = _run_portal_queries(["primera", "segunda"], search, portal="Torre")

    assert calls == ["primera", "segunda"]
    assert [job.company for job in found] == ["Servicio Neutro"]
    err = capsys.readouterr().err
    assert "search failed for primera" in err
    assert "the rest finished" in err
    assert "every search failed" not in err


def test_every_failed_query_exits(capsys: pytest.CaptureFixture[str]) -> None:
    def search(_text: str) -> list[JobPosting]:
        raise RuntimeError("down")

    with pytest.raises(typer.Exit) as raised:
        _run_portal_queries(["primera", "segunda"], search, portal="Get on Board")

    assert raised.value.exit_code == GENERIC_FAILURE
    err = capsys.readouterr().err
    assert "every search failed" in err
    assert "the rest finished" not in err
