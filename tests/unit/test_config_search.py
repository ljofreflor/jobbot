"""[search] coercion names the field and does not treat the string false as true."""

from __future__ import annotations

from pathlib import Path

import pytest

from jobbot.cli import run_cli
from jobbot.config import ConfigError, load_config
from jobbot.exit_codes import VALIDATION_FAILURE


def test_string_false_and_numeric_age_are_coerced(tmp_path: Path) -> None:
    (tmp_path / ".jobbot.toml").write_text(
        '[search]\nallow_remote = "false"\nmax_age_days = "14"\n',
        encoding="utf-8",
    )
    config = load_config(tmp_path)
    assert config.search.allow_remote is False
    assert config.search.max_age_days == 14


def test_bad_age_names_the_field_and_hides_the_path(tmp_path: Path) -> None:
    (tmp_path / ".jobbot.toml").write_text(
        '[search]\nmax_age_days = "no"\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError) as caught:
        load_config(tmp_path)
    message = str(caught.value)
    assert message == "invalid config: search.max_age_days"
    assert str(tmp_path) not in message
    assert "no" not in message


def test_cli_rejects_a_bad_search_value(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / ".jobbot.toml").write_text(
        '[search]\nmax_age_days = "no"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    code = run_cli(["profile", "validate"], standalone_mode=False)
    err = capsys.readouterr().err
    assert code == VALIDATION_FAILURE
    assert "search.max_age_days" in err
    assert str(tmp_path) not in err
