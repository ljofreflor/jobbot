"""Portal health names a read. It does not search and it does not store."""

from __future__ import annotations

from jobbot.cli import run_cli
from jobbot.companies.health import portal_health
from jobbot.exit_codes import SUCCESS, VALIDATION_FAILURE


def test_robots_is_omitted_even_when_the_status_is_200() -> None:
    assert portal_health(status=200, robots_disallow=True) == "omitted"


def test_a_drop_or_a_block_is_refused_and_200_is_reachable() -> None:
    assert portal_health(status=None) == "refused"
    assert portal_health(status=403) == "refused"
    assert portal_health(status=429) == "refused"
    assert portal_health(status=503) == "refused"
    assert portal_health(status=200) == "reachable"
    assert portal_health(status=404) == "unknown"


def test_cli_prints_the_label_and_does_not_list_jobs(capsys) -> None:
    code = run_cli(["companies", "health", "--status", "200"], standalone_mode=False)

    out = capsys.readouterr().out
    assert code == SUCCESS
    assert out.strip() == "reachable"
    assert "job" not in out.casefold()


def test_cli_robots_is_omitted(capsys) -> None:
    code = run_cli(
        ["companies", "health", "--status", "200", "--robots"],
        standalone_mode=False,
    )

    assert code == SUCCESS
    assert capsys.readouterr().out.strip() == "omitted"


def test_cli_without_an_observation_exits_2(capsys) -> None:
    code = run_cli(["companies", "health"], standalone_mode=False)

    assert code == VALIDATION_FAILURE
    assert "nothing observed" in capsys.readouterr().err
