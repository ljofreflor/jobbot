"""LaTeX escaping tests."""

from jobbot.cv.latex import escape_latex


def test_escape_ampersand() -> None:
    assert escape_latex("R&D") == r"R\&D"


def test_escape_percent_underscore() -> None:
    assert r"\%" in escape_latex("100%")
    assert r"\_" in escape_latex("snake_case")


def test_escape_backslash() -> None:
    assert r"\textbackslash{}" in escape_latex(r"path\to")
