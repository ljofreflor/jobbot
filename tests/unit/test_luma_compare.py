"""Luma workshop vs this advisory service: generated comparison table. Offline."""

from __future__ import annotations

from bs4 import BeautifulSoup

from jobbot.advisory.compare import (
    LUMA_EVENT_TITLE,
    LUMA_EVENT_URL,
    comparison_commands,
    luma_comparison_rows,
    render_comparison,
)


def test_comparison_rows_cover_the_three_mini_agents_and_refuse_por_ti() -> None:
    rows = luma_comparison_rows()
    workshop = " ".join(row.workshop.casefold() for row in rows)
    ours = " ".join(row.ours.casefold() for row in rows)
    assert "afina tu cv" in workshop
    assert "vacantes" in workshop
    assert "postulaciones" in workshop
    assert "por ti" in workshop
    assert "por ti" not in ours
    assert "tú envías" in ours
    assert "no invento" in ours


def test_comparison_commands_are_real_cli_paths() -> None:
    from jobbot.cli import app
    from jobbot.ops.capabilities import collect_commands

    known = {entry.path for entry in collect_commands(app)}
    commands = comparison_commands()
    assert commands
    for command in commands:
        assert command in known, command


def test_rendered_table_is_accessible_and_cites_luma() -> None:
    soup = BeautifulSoup(render_comparison(), "html.parser")
    table = soup.find("table", class_="compare")
    assert table is not None
    caption = table.find("caption")
    assert caption is not None
    link = caption.find("a")
    assert link is not None
    assert link.get("href") == LUMA_EVENT_URL
    rel = link.get("rel") or []
    assert "noopener" in rel and "noreferrer" in rel
    assert LUMA_EVENT_TITLE in link.get_text()
    assert "utm_" not in str(link.get("href"))
    headers = [th.get_text(strip=True) for th in table.find("thead").find_all("th")]
    assert headers == ["El taller", "Acá"]
    body_rows = table.find("tbody").find_all("tr")
    assert len(body_rows) == len(luma_comparison_rows())
    for tr, row in zip(body_rows, luma_comparison_rows(), strict=True):
        assert tr.find("th", attrs={"scope": "row"}).get_text() == row.workshop
        assert tr.find("td").get_text() == row.ours
        assert row.workshop not in tr.find("td").get_text()
