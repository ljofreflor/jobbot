"""The reviewer keeps or rejects. It does not write a new sentence."""

from __future__ import annotations

import pytest

from jobbot.cli import run_cli
from jobbot.cv.review import review_change
from jobbot.exit_codes import SUCCESS, VALIDATION_FAILURE

_CURRENT = "Cerré 12 turnos."


def test_a_dropped_number_is_rejected() -> None:
    assert review_change(_CURRENT, "Cerré turnos.") == "reject: number"


def test_a_longer_line_of_only_intensifiers_is_rejected() -> None:
    assert review_change(_CURRENT, "Cerré 12 turnos muy.") == "reject: longer"


def test_the_same_facts_are_kept() -> None:
    assert review_change(_CURRENT, "Cerré 12 turnos en 2024.") == "keep"


def test_a_blank_side_is_refused() -> None:
    with pytest.raises(ValueError, match="missing text"):
        review_change("  ", _CURRENT)


def test_cli_prints_the_verdict(capsys) -> None:
    code = run_cli(
        ["cv", "review", "--current", _CURRENT, "--proposed", "Cerré turnos."],
        standalone_mode=False,
    )

    assert code == SUCCESS
    assert capsys.readouterr().out.strip() == "reject: number"


def test_cli_blank_proposed_exits_2(capsys) -> None:
    code = run_cli(
        ["cv", "review", "--current", _CURRENT, "--proposed", "  "],
        standalone_mode=False,
    )

    assert code == VALIDATION_FAILURE
    assert "missing text" in capsys.readouterr().err
