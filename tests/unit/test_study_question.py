"""A study question names the term. It does not add it to the profile."""

from __future__ import annotations

import pytest

from jobbot.cli import run_cli
from jobbot.exit_codes import SUCCESS, VALIDATION_FAILURE
from jobbot.profile.study import study_question


def test_a_repeated_unknown_term_is_a_question() -> None:
    text = study_question("Ventilación", repeats=3, known=False)

    assert text == "pregunta: estudias Ventilación?"
    assert "skill" not in text


def test_a_known_term_or_a_single_mention_is_not_a_question() -> None:
    assert study_question("Ventilación", repeats=3, known=True) == "already in the profile"
    assert study_question("Ventilación", repeats=1, known=False) == "not repeated"


def test_a_blank_term_or_a_negative_count_is_refused() -> None:
    with pytest.raises(ValueError, match="missing term"):
        study_question("  ", repeats=3, known=False)
    with pytest.raises(ValueError, match="repeats must be >= 0"):
        study_question("Ventilación", repeats=-1, known=False)


def test_cli_prints_the_question_and_does_not_write(capsys) -> None:
    code = run_cli(
        ["profile", "study", "--term", "Ventilación", "--repeats", "3"],
        standalone_mode=False,
    )

    out = capsys.readouterr().out
    assert code == SUCCESS
    assert out.strip() == "pregunta: estudias Ventilación?"


def test_cli_known_term_is_not_a_question(capsys) -> None:
    code = run_cli(
        ["profile", "study", "--term", "Ventilación", "--repeats", "4", "--known"],
        standalone_mode=False,
    )

    assert code == SUCCESS
    assert capsys.readouterr().out.strip() == "already in the profile"


def test_cli_blank_term_exits_2(capsys) -> None:
    code = run_cli(
        ["profile", "study", "--term", "  ", "--repeats", "3"],
        standalone_mode=False,
    )

    assert code == VALIDATION_FAILURE
    assert "missing term" in capsys.readouterr().err
