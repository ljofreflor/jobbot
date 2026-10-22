"""An interview question names the gap. It does not answer it."""

from __future__ import annotations

import pytest

from jobbot.cli import run_cli
from jobbot.exit_codes import SUCCESS, VALIDATION_FAILURE
from jobbot.profile.interview import gap_question


def test_a_gap_is_one_question_and_not_an_answer() -> None:
    text = gap_question("permiso de trabajo")

    assert text == "pregunta: ¿qué evidencia hay de permiso de trabajo?"
    assert "respuesta" not in text


def test_a_blank_gap_is_refused() -> None:
    with pytest.raises(ValueError, match="missing gap"):
        gap_question("  ")


def test_cli_prints_the_question(capsys) -> None:
    code = run_cli(
        ["profile", "interview", "--gap", "permiso de trabajo"],
        standalone_mode=False,
    )

    out = capsys.readouterr().out
    assert code == SUCCESS
    assert out.strip() == "pregunta: ¿qué evidencia hay de permiso de trabajo?"


def test_cli_blank_gap_exits_2(capsys) -> None:
    code = run_cli(["profile", "interview", "--gap", "  "], standalone_mode=False)

    assert code == VALIDATION_FAILURE
    assert "missing gap" in capsys.readouterr().err
