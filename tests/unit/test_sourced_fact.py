"""A sourced fact is a confirmation line. The profile stays unchanged."""

from __future__ import annotations

import pytest

from jobbot.cli import run_cli
from jobbot.exit_codes import SUCCESS, VALIDATION_FAILURE
from jobbot.profile.sourced import confirm_sourced_fact


def test_a_declared_source_is_a_confirmation() -> None:
    text = confirm_sourced_fact("Cuatro informes en 2024.", "GitHub")

    assert text == "confirm: Cuatro informes en 2024. (source: github)"


def test_a_blank_fact_or_an_unknown_source_is_refused() -> None:
    with pytest.raises(ValueError, match="missing fact"):
        confirm_sourced_fact("  ", "scholar")
    with pytest.raises(ValueError, match="unknown source"):
        confirm_sourced_fact("Cuatro informes en 2024.", "linkedin")


def test_cli_prints_the_confirmation(capsys) -> None:
    code = run_cli(
        [
            "profile",
            "expand",
            "--text",
            "Cuatro informes en 2024.",
            "--source",
            "portfolio",
        ],
        standalone_mode=False,
    )

    out = capsys.readouterr().out
    assert code == SUCCESS
    assert out.strip() == "confirm: Cuatro informes en 2024. (source: portfolio)"


def test_cli_unknown_source_exits_2(capsys) -> None:
    code = run_cli(
        ["profile", "expand", "--text", "Cuatro informes en 2024.", "--source", "linkedin"],
        standalone_mode=False,
    )

    assert code == VALIDATION_FAILURE
    assert "unknown source" in capsys.readouterr().err
