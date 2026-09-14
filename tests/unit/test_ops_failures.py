"""Local ops failure observability."""

from __future__ import annotations

from pathlib import Path

import pytest

from jobbot.config import JobbotConfig, PathsConfig
from jobbot.db.engine import make_engine, make_session_factory
from jobbot.exit_codes import GENERIC_FAILURE, SUCCESS, UI_CHANGED
from jobbot.ops.failures import (
    capture_cli_failure,
    failure_fingerprint,
    get_failure,
    list_failures,
    mark_status,
    normalize_message,
    record_failure,
    should_record_cli_failure,
)
from jobbot.ops.loop import LoopTickResult, run_loop, run_loop_tick
from jobbot.ops.redact import host_only_url, redact_context, redact_text


def _config(tmp_path: Path) -> JobbotConfig:
    return JobbotConfig(
        root=tmp_path,
        paths=PathsConfig(
            profile=Path("data/profile.yaml"),
            database=Path("data/jobbot.sqlite"),
            output=Path("output"),
        ),
    )


def test_fingerprint_stable_across_numeric_noise() -> None:
    a = failure_fingerprint(
        component="getonboard",
        error_class="RuntimeError",
        message="job J0016 failed after 12 retries",
    )
    b = failure_fingerprint(
        component="getonboard",
        error_class="RuntimeError",
        message="job J0099 failed after 3 retries",
    )
    assert a == b
    assert len(a) == 16


def test_normalize_message_collapses_noise() -> None:
    assert "j0016" not in normalize_message("see J0016 path /tmp/x")
    assert "<id>" in normalize_message("see J0016")


def test_redact_strips_secrets_and_url_query() -> None:
    text = redact_text("OPENAI_API_KEY=sk-abc1234567890 token=sekrit Bearer abc.def")
    assert "sekrit" not in text
    assert "sk-abc" not in text or "redacted" in text.lower()
    assert "Bearer <redacted>" in text or "redacted" in text.lower()
    assert host_only_url("https://example.com/apply?token=secret#x") == (
        "https://example.com/apply"
    )
    ctx = redact_context({"ats_url": "https://boards.greenhouse.io/x?key=1", "note": "ok"})
    assert "key=" not in str(ctx["ats_url"])
    assert ctx["note"] == "ok"


def test_record_and_list_failure(tmp_path: Path) -> None:
    config = _config(tmp_path)
    engine = make_engine(config.database_path)
    session = make_session_factory(engine)()
    try:
        rec = record_failure(
            session,
            config=config,
            exit_code=UI_CHANGED,
            argv=["jobbot", "linkedin", "sweep", "hiring"],
            error_class="UIChanged",
            message="selector not found",
            context={"url": "https://www.linkedin.com/feed?session=abc"},
        )
        assert rec.id == "F0001"
        assert rec.component == "linkedin"
        assert rec.fingerprint
        mirror = config.output_dir / "ops" / "failures" / "F0001.json"
        assert mirror.is_file()
        listed = list_failures(session, status="new")
        assert len(listed) == 1
        assert get_failure(session, "F0001") is not None
        updated = mark_status(session, "F0001", "fixed")
        assert updated is not None
        assert updated.status == "fixed"
        assert list_failures(session, status="new") == []
    finally:
        session.close()


def test_should_not_record_success_or_ops() -> None:
    assert not should_record_cli_failure(["jobbot", "profile", "validate"], SUCCESS)
    assert not should_record_cli_failure(["jobbot", "ops", "failures"], GENERIC_FAILURE)
    assert should_record_cli_failure(["jobbot", "probe-exit", "5"], UI_CHANGED)


def test_capture_cli_failure_ui_changed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    config = _config(tmp_path)
    rec = capture_cli_failure(
        UI_CHANGED,
        argv=["jobbot", "probe-exit", "5"],
        config=config,
    )
    assert rec is not None
    assert rec.id == "F0001"
    assert rec.exit_code == UI_CHANGED


def test_run_cli_records_ui_changed_exit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail-first regression: nonzero CLI exits must land in ops_failures."""
    from jobbot.cli import run_cli

    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    code = run_cli(["probe-exit", str(UI_CHANGED)], standalone_mode=False)
    assert code == UI_CHANGED
    engine = make_engine(tmp_path / "data" / "jobbot.sqlite")
    session = make_session_factory(engine)()
    try:
        rows = list_failures(session, status="new")
        assert len(rows) == 1
        assert rows[0].exit_code == UI_CHANGED
        assert rows[0].id == "F0001"
    finally:
        session.close()


def test_loop_tick_records_and_continues(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = _config(tmp_path)
    calls = {"n": 0}

    def boom(_cfg: JobbotConfig) -> None:
        calls["n"] += 1
        raise RuntimeError("boom for observability")

    monkeypatch.setitem(
        __import__("jobbot.ops.loop", fromlist=["_RUNNERS"])._RUNNERS,
        "getonboard-prepare",
        boom,
    )
    tick = run_loop_tick("getonboard-prepare", config=config)
    assert not tick.ok
    assert tick.failure is not None
    assert tick.failure.id == "F0001"

    sleeps: list[float] = []
    ticks: list[bool] = []

    def on_tick(result: LoopTickResult) -> None:
        ticks.append(result.ok)

    code = run_loop(
        "getonboard-prepare",
        interval_sec=0.01,
        fail_fast=False,
        max_ticks=3,
        config=config,
        sleep_fn=sleeps.append,
        on_tick=on_tick,
    )
    assert code == GENERIC_FAILURE
    assert calls["n"] >= 3
    assert ticks == [False, False, False]
    assert len(sleeps) == 2  # sleep between ticks, not after last
