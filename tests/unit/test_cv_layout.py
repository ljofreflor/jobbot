"""A LaTeX log reports overfull boxes. The command does not compile or write."""

from __future__ import annotations

from pathlib import Path

from jobbot.cli import run_cli
from jobbot.cv.layout import layout_findings, pages_written
from jobbot.exit_codes import SUCCESS, VALIDATION_FAILURE

_LOG = """\
Overfull \\hbox (785.2pt too wide) in paragraph at lines 12--13
Underfull \\hbox (badness 10000) in paragraph at lines 1--2
Output written on cv.pdf (2 pages, 45678 bytes).
"""


def test_overfull_hbox_is_a_finding_and_underfull_is_not() -> None:
    assert layout_findings(_LOG) == ["overfull 785.2pt"]
    assert pages_written(_LOG) == 2


def test_one_page_and_a_clean_log() -> None:
    log = "Output written on cv.pdf (1 page, 100 bytes).\n"

    assert layout_findings(log) == []
    assert pages_written(log) == 1


def test_an_unfinished_log_has_no_page_count() -> None:
    assert pages_written("no output\n") is None


def test_cli_prints_the_finding_and_does_not_write(tmp_path: Path, capsys) -> None:
    log = tmp_path / "cv.log"
    log.write_text(_LOG, encoding="utf-8")
    before = log.read_bytes()

    code = run_cli(["cv", "layout", str(log)], standalone_mode=False)

    out = capsys.readouterr().out
    assert code == SUCCESS
    assert "overfull 785.2pt" in out
    assert "pages: 2" in out
    assert "Underfull" not in out
    assert log.read_bytes() == before
    assert list(tmp_path.iterdir()) == [log]


def test_missing_log_exits_2(tmp_path: Path, capsys) -> None:
    missing = tmp_path / "absent.log"

    code = run_cli(["cv", "layout", str(missing)], standalone_mode=False)

    assert code == VALIDATION_FAILURE
    assert "log not found" in capsys.readouterr().err
    assert not missing.exists()
