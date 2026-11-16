"""A post is email, a new portal host, or unknown. The local registry is not written."""

from __future__ import annotations

from pathlib import Path

import pytest

from jobbot.cli import run_cli
from jobbot.exit_codes import VALIDATION_FAILURE


def _workspace(tmp_path: Path, project_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "output").mkdir()
    (tmp_path / ".jobbot.toml").write_text(
        f'[paths]\ntemplates = "{project_root / "templates"}"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)


def test_mailto_is_email_and_not_a_portal(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    post = tmp_path / "post.txt"
    post.write_text("Enviá el CV a postulaciones@example.com\n", encoding="utf-8")

    code = run_cli(["postulate", "--fixture", str(post)], standalone_mode=False)

    out = capsys.readouterr().out
    assert code == 0
    assert "route: email" in out
    assert "contributions: 0" in out
    assert "@" not in out
    assert not (tmp_path / "data" / "portals.yaml").exists()


def test_an_unknown_greenhouse_host_is_one_contribution(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    url = "https://boards.eu.greenhouse.io/servicio/jobs/1"
    post = tmp_path / "post.txt"
    post.write_text(f"Postulá en {url}\n", encoding="utf-8")

    code = run_cli(["postulate", "--fixture", str(post)], standalone_mode=False)

    out = capsys.readouterr().out
    assert code == 0
    assert "route: portal" in out
    assert f"contribution: boards.eu.greenhouse.io greenhouse {url}" in out
    assert not (tmp_path / "data" / "portals.yaml").exists()


def test_a_seed_host_is_not_contributed_again(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    post = tmp_path / "post.txt"
    post.write_text(
        "Postulá en https://boards.greenhouse.io/servicio/jobs/1\n",
        encoding="utf-8",
    )

    code = run_cli(["postulate", "--fixture", str(post)], standalone_mode=False)

    out = capsys.readouterr().out
    assert code == 0
    assert "route: portal" in out
    assert "contributions: 0" in out


def test_a_post_without_a_route_stays_unknown(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    post = tmp_path / "post.txt"
    post.write_text("El equipo publica un aviso sin enlace.\n", encoding="utf-8")

    code = run_cli(["postulate", "--fixture", str(post)], standalone_mode=False)

    out = capsys.readouterr().out
    assert code == 0
    assert "route: unknown" in out
    assert "contributions: 0" in out


def test_without_a_fixture_the_post_is_not_read(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)

    code = run_cli(["postulate"], standalone_mode=False)

    assert code == VALIDATION_FAILURE
    assert "the post was not read" in capsys.readouterr().err
