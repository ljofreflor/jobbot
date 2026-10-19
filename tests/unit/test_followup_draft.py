"""A follow-up draft uses only the given facts. It is never sent."""

from __future__ import annotations

import pytest

from jobbot.applications.followup import followup_draft
from jobbot.cli import run_cli
from jobbot.exit_codes import SUCCESS, VALIDATION_FAILURE


def test_one_sent_followup_names_only_the_given_facts() -> None:
    text = followup_draft("Servicio Neutro", "Analista", sent=1)

    assert text == "Escribo por Analista en Servicio Neutro. Sigo disponible si hay novedades."
    assert "@" not in text


def test_two_sent_followups_is_the_cap() -> None:
    assert followup_draft("Servicio Neutro", "Analista", sent=2) is None
    assert followup_draft("Servicio Neutro", "Analista", sent=3) is None


def test_a_blank_fact_or_a_negative_count_is_refused() -> None:
    with pytest.raises(ValueError, match="missing fact"):
        followup_draft("  ", "Analista", sent=0)
    with pytest.raises(ValueError, match="sent must be >= 0"):
        followup_draft("Servicio Neutro", "Analista", sent=-1)


def test_cli_prints_the_draft_and_does_not_send(capsys) -> None:
    code = run_cli(
        [
            "applications",
            "followup",
            "--company",
            "Servicio Neutro",
            "--title",
            "Analista",
            "--sent",
            "0",
        ],
        standalone_mode=False,
    )

    out = capsys.readouterr().out
    assert code == SUCCESS
    assert "Escribo por Analista en Servicio Neutro." in out
    assert "@" not in out
    assert "mailto" not in out.casefold()


def test_cli_cap_prints_no_draft(capsys) -> None:
    code = run_cli(
        [
            "applications",
            "followup",
            "--company",
            "Servicio Neutro",
            "--title",
            "Analista",
            "--sent",
            "2",
        ],
        standalone_mode=False,
    )

    out = capsys.readouterr().out
    assert code == SUCCESS
    assert out.strip() == "cap reached"
    assert "Escribo" not in out


def test_cli_missing_fact_exits_2(capsys) -> None:
    code = run_cli(
        [
            "applications",
            "followup",
            "--company",
            "Servicio Neutro",
            "--title",
            "  ",
            "--sent",
            "0",
        ],
        standalone_mode=False,
    )

    assert code == VALIDATION_FAILURE
    assert "missing fact" in capsys.readouterr().err
