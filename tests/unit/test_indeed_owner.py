"""Indeed sync types nothing unless the open resume names this workspace."""

from __future__ import annotations

from pathlib import Path

from jobbot.adapters.indeed.client import IndeedAdapter
from jobbot.adapters.indeed.owner import (
    IndeedOwnerMismatch,
    cv_name_verdict,
    refuse_indeed_write,
    write_allowed,
)
from jobbot.browser.cdp import cdp_endpoint
from jobbot.config import JobbotConfig, PathsConfig
from jobbot.models.sync import SyncOperation, SyncOpType, SyncPlan


def test_other_name_is_a_mismatch_and_the_message_hides_it() -> None:
    page = "Marta Soto\nResume"
    assert cv_name_verdict(page, "Ana Ejemplo") == "mismatch"
    message = refuse_indeed_write(page, "Ana Ejemplo")
    assert message is not None
    assert "Marta" not in message
    assert "Soto" not in message
    assert "Nothing was typed" in message


def test_a_blank_resume_is_missing_and_is_not_written() -> None:
    assert cv_name_verdict("", "Ana Ejemplo") == "missing"
    assert cv_name_verdict("Resume", "Ana Ejemplo") == "missing"
    assert refuse_indeed_write("", "Ana Ejemplo") == (
        "Indeed resume has no visible name. Nothing was typed."
    )


def test_the_owner_name_may_continue() -> None:
    assert cv_name_verdict("Ana Ejemplo\nHeadline", "Ana Ejemplo") == "match"
    assert refuse_indeed_write("Ana Ejemplo\nHeadline", "Ana Ejemplo") is None


def test_ipv4_and_ipv6_on_the_same_port_are_different_destinations() -> None:
    v4 = "http://127.0.0.1:9222"
    v6 = "http://[::1]:9222"
    assert cdp_endpoint(v4) != cdp_endpoint(v6)
    checks = {cdp_endpoint(v4): "match"}
    assert write_allowed(checks, v4)
    assert write_allowed(checks, v6) is False


def test_apply_types_nothing_when_the_resume_names_someone_else(
    tmp_path: Path, project_root: Path
) -> None:
    profile = tmp_path / "data" / "profile.yaml"
    profile.parent.mkdir(parents=True)
    profile.write_text(
        (project_root / "data/profile.example.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    adapter = IndeedAdapter(JobbotConfig(root=tmp_path, paths=PathsConfig(output=Path("output"))))

    class _Page:
        url = "https://profile.indeed.com/resume"
        fills: list[str] = []

        def goto(self, url: str, **_: object) -> None:
            self.url = url

        def inner_text(self, _selector: str) -> str:
            return "Marta Soto"

        def fill(self, *_args: object, **_kwargs: object) -> None:
            self.fills.append("filled")

    page = _Page()

    class _Ctx:
        def __init__(self, current: _Page) -> None:
            self.page = current

        def __enter__(self) -> _Ctx:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    adapter._session = lambda: _Ctx(page)  # type: ignore[method-assign]
    plan = SyncPlan(
        target="indeed",
        operations=[
            SyncOperation(op=SyncOpType.ADD, section="skills", field="name", label="python")
        ],
    )
    try:
        adapter.apply_sync_plan(plan, section="skills")
    except IndeedOwnerMismatch as exc:
        assert "Marta" not in str(exc)
        assert "Nothing was typed" in str(exc)
    else:
        raise AssertionError("expected the write to stop")
    assert page.fills == []
