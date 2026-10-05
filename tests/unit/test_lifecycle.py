"""Cargo-lifecycle diagram: every CLI command in exactly one stage. Offline."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from bs4 import BeautifulSoup

from jobbot.advisory.lifecycle import (
    assign_commands,
    classify_command,
    collect_cli_paths,
    lifecycle_blueprint,
    lifecycle_stages,
    render_lifecycle,
)
from jobbot.ops import pii_guard

_PHONE_LIKE = re.compile(r"\+?\d[\d\s().\-]{7,}\d")


def test_every_command_lands_in_exactly_one_stage() -> None:
    paths = collect_cli_paths()
    stages = lifecycle_stages(paths)
    seen: list[str] = []
    for stage in stages:
        seen.extend(stage.commands)
    assert len(seen) == len(set(seen))
    assert set(seen) == set(paths)
    assert len(paths) == 104


def test_longest_prefix_wins() -> None:
    assert classify_command("linkedin sweep") == "find"
    assert classify_command("linkedin login") == "presence"
    assert classify_command("getonboard search") == "find"
    assert classify_command("getonboard prepare") == "presence"
    assert classify_command("companies signup") == "presence"
    assert classify_command("companies list") == "map"
    assert classify_command("jobs search") == "find"
    assert classify_command("jobs match") == "choose"
    assert classify_command("profile show") == "arrive"
    assert classify_command("profile queries") == "profile"
    assert classify_command("get") == "find"
    assert classify_command("status") == "presence"


def test_unclassified_commands_fail_instead_of_vanishing() -> None:
    with pytest.raises(ValueError, match="unclassified"):
        assign_commands(["no-such-command"], lifecycle_blueprint())


def test_new_prefixed_command_auto_lands() -> None:
    stages = assign_commands(["cv brand-new"], lifecycle_blueprint())
    presence = next(stage for stage in stages if stage.key == "presence")
    assert "cv brand-new" in presence.commands


def test_render_is_accessible_and_shows_commands() -> None:
    figure = render_lifecycle()
    soup = BeautifulSoup(figure, "html.parser")
    svgs = soup.find_all("svg")
    assert len(svgs) == 2
    ids: set[str] = set()
    for svg in svgs:
        assert svg.get("role") == "img"
        assert svg.get("viewbox") or svg.get("viewBox")
        title, desc = svg.find("title"), svg.find("desc")
        assert title is not None and title.get_text(strip=True)
        assert desc is not None
        text = desc.get_text()
        assert "tú envías" in text.casefold()
        labelled = str(svg.get("aria-labelledby", "")).split()
        assert labelled == [title.get("id"), desc.get("id")]
        for node in svg.find_all(id=True):
            assert node["id"] not in ids
            ids.add(node["id"])
    drawn = BeautifulSoup(figure, "html.parser").get_text(" ")
    for path in collect_cli_paths():
        assert path in drawn, path


def test_figure_is_self_contained_hitl_and_clean() -> None:
    figure = render_lifecycle()
    folded = figure.casefold()
    assert "<script" not in folded
    assert "http" not in folded
    assert "href" not in folded
    assert "<image" not in folded
    assert "tú envías" in folded
    assert "por ti" not in folded
    assert pii_guard.scan_text(figure, "asesoria/index.html") == []
    assert not _PHONE_LIKE.search(figure)


def test_figure_names_no_employer(project_root: Path) -> None:
    seed = yaml.safe_load(
        (project_root / "data" / "companies-cl.example.yaml").read_text(encoding="utf-8")
    )
    names = [str(row["name"]) for row in seed["companies"]]
    text = BeautifulSoup(render_lifecycle(), "html.parser").get_text(" ").casefold()
    for name in names:
        assert name.casefold() not in text, name


def test_commands_are_drawn_as_chips_in_both_layouts() -> None:
    soup = BeautifulSoup(render_lifecycle(), "html.parser")
    for svg in soup.find_all("svg"):
        chips = svg.find_all("g", class_="pm-chip")
        assert len(chips) == 104
        labels = {chip.get_text(" ", strip=True) for chip in chips}
        assert "cv advise" in labels
        assert "application apply" in labels
        assert "linkedin sweep" in labels


def test_apply_stage_is_the_hitl_gate() -> None:
    soup = BeautifulSoup(render_lifecycle(), "html.parser")
    gates = soup.find_all("g", class_="lc-gate")
    assert gates
    for gate in gates:
        text = " ".join(gate.get_text(" ").split()).casefold()
        assert "tú envías" in text


def test_caption_names_jobbot_once() -> None:
    soup = BeautifulSoup(render_lifecycle(), "html.parser")
    caption = soup.find("figcaption")
    assert caption is not None
    text = caption.get_text(" ")
    assert text.count("jobbot") == 1
    assert "104" in text


def test_render_is_deterministic() -> None:
    assert render_lifecycle() == render_lifecycle()

