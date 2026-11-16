"""The front door is named before the portal commands. Those commands stay callable."""

from __future__ import annotations

from jobbot.cli import run_cli
from jobbot.exit_codes import SUCCESS


def test_help_names_the_front_door_before_indeed(capsys) -> None:
    code = run_cli(["--help"], standalone_mode=False)

    text = capsys.readouterr().out
    assert code == SUCCESS
    assert text.index("profile") < text.index("indeed")
    assert text.index("cv") < text.index("indeed")
    assert text.index("get") < text.index("indeed")
    assert text.index("capture") < text.index("indeed")


def test_indeed_stays_callable(capsys) -> None:
    code = run_cli(["indeed", "--help"], standalone_mode=False)

    assert code == SUCCESS
    assert "Indeed" in capsys.readouterr().out
