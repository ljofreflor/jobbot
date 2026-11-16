"""The style registry names the templates JobBot can compile. It does not compile."""

from __future__ import annotations

from jobbot.cli import run_cli
from jobbot.cv.renderer import registered_styles
from jobbot.exit_codes import SUCCESS


def test_registered_styles_are_moderncv_then_plain() -> None:
    assert registered_styles() == [
        ("moderncv", "cv_moderncv.tex.j2"),
        ("plain", "cv.tex.j2"),
    ]


def test_cli_lists_those_styles_and_does_not_compile(capsys) -> None:
    code = run_cli(["cv", "styles"], standalone_mode=False)

    out = capsys.readouterr().out
    assert code == SUCCESS
    assert "moderncv cv_moderncv.tex.j2" in out
    assert "plain cv.tex.j2" in out
    assert "banking" not in out
