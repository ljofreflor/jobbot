"""jobbot update — uv tool reinstall / Docker hint."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jobbot import self_update
from jobbot.exit_codes import GENERIC_FAILURE, SUCCESS


def test_update_in_docker_returns_pull_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(self_update, "_in_docker", lambda: True)
    result = self_update.update_jobbot()
    assert result.ok is False
    assert "docker pull" in result.message.casefold()


def test_dockerenv_file_is_the_only_docker_signal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A k8s/devcontainer cgroup must not block updating a uv-tool install."""
    dockerenv = tmp_path / "dockerenv"
    monkeypatch.setattr(self_update, "_DOCKERENV", dockerenv)
    assert self_update._in_docker() is False
    dockerenv.write_text("", encoding="utf-8")
    assert self_update._in_docker() is True


def test_update_without_uv_points_at_install_script(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(self_update, "_in_docker", lambda: False)
    monkeypatch.setattr(self_update.shutil, "which", lambda _name: None)
    monkeypatch.setattr(self_update, "_home", lambda: tmp_path)
    result = self_update.update_jobbot()
    assert result.ok is False
    assert "install.sh" in result.message
    assert "main" in result.message


def _fake_which(name: str) -> str | None:
    return "/usr/bin/uv" if name == "uv" else None


class _Completed:
    returncode = 0
    stdout = ""
    stderr = ""


def test_update_defaults_to_production_main(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(self_update, "_in_docker", lambda: False)
    monkeypatch.setattr(self_update.shutil, "which", _fake_which)
    monkeypatch.delenv("JOBBOT_REF", raising=False)
    monkeypatch.delenv("JOBBOT_REPO", raising=False)
    monkeypatch.delenv("JOBBOT_SOURCE", raising=False)

    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_kwargs: object) -> _Completed:
        calls.append(list(cmd))
        return _Completed()

    monkeypatch.setattr(self_update.subprocess, "run", fake_run)
    monkeypatch.setattr(self_update, "_read_version", lambda: "0.1.0")
    monkeypatch.setattr(self_update, "_path_install_stamp", lambda: None)

    result = self_update.update_jobbot()
    assert result.ok is True
    assert calls
    pkg = calls[0][-1]
    assert pkg == "git+https://github.com/ljofreflor/jobbot@main"
    assert "develop" not in pkg
    assert result.already_latest is False
    assert "PATH" in result.message or "production" in result.message.casefold()


def test_update_runs_uv_tool_install(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(self_update, "_in_docker", lambda: False)
    monkeypatch.setattr(self_update.shutil, "which", _fake_which)

    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_kwargs: object) -> _Completed:
        calls.append(list(cmd))
        return _Completed()

    monkeypatch.setattr(self_update.subprocess, "run", fake_run)
    monkeypatch.setattr(self_update, "_read_version", lambda: "0.1.0")
    monkeypatch.setattr(self_update, "_path_install_stamp", lambda: None)

    result = self_update.update_jobbot(ref="main")
    assert result.ok is True
    assert calls
    assert calls[0][:4] == ["/usr/bin/uv", "tool", "install", "--force"]
    assert calls[0][-1].startswith("git+https://github.com/ljofreflor/jobbot@main")


def test_update_from_wheel_source(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(self_update, "_in_docker", lambda: False)
    monkeypatch.setattr(self_update.shutil, "which", _fake_which)
    wheel = tmp_path / "jobbot-0.1.0-py3-none-any.whl"
    wheel.write_bytes(b"fake")

    calls: list[list[str]] = []

    monkeypatch.setattr(
        self_update.subprocess,
        "run",
        lambda cmd, **_k: calls.append(list(cmd)) or _Completed(),
    )
    monkeypatch.setattr(self_update, "_read_version", lambda: "0.1.0")
    monkeypatch.setattr(self_update, "_path_install_stamp", lambda: None)

    result = self_update.update_jobbot(source=f"wheel:{wheel}")
    assert result.ok is True
    assert calls[0][-1] == str(wheel)


def test_update_finds_uv_next_to_the_jobbot_executable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """uv-tool shims often keep ~/.local/bin off PATH; uv still lives beside jobbot."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    uv = bindir / "uv"
    uv.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    uv.chmod(0o755)
    jobbot = bindir / "jobbot"
    jobbot.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    jobbot.chmod(0o755)

    def which(name: str) -> str | None:
        if name == "jobbot":
            return str(jobbot)
        return None

    monkeypatch.setattr(self_update, "_in_docker", lambda: False)
    monkeypatch.setattr(self_update.shutil, "which", which)
    monkeypatch.setattr(self_update, "_home", lambda: tmp_path / "empty-home")

    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_kwargs: object) -> _Completed:
        calls.append(list(cmd))
        return _Completed()

    monkeypatch.setattr(self_update.subprocess, "run", fake_run)
    monkeypatch.setattr(self_update, "_read_version", lambda: "0.1.0")
    monkeypatch.setattr(self_update, "_path_install_stamp", lambda: None)

    result = self_update.update_jobbot()
    assert result.ok is True
    assert calls[0][0] == str(uv)


def test_already_on_latest_production_is_ok(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    data_home = tmp_path / "share"
    _write_tool_stamp(data_home, commit="abc123def")
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
    monkeypatch.setattr(self_update, "_in_docker", lambda: False)
    monkeypatch.setattr(self_update.shutil, "which", _fake_which)
    monkeypatch.setattr(self_update.subprocess, "run", lambda *_a, **_k: _Completed())
    monkeypatch.setattr(self_update, "_read_version", lambda: "0.1.0")

    result = self_update.update_jobbot()
    assert result.ok is True
    assert result.already_latest is True
    assert "already" in result.message.casefold()
    assert "main" in result.message.casefold()
    assert result.version_line == "0.1.0"


def test_stamp_changes_when_production_moves(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    data_home = tmp_path / "share"
    _write_tool_stamp(data_home, commit="oldcommit")
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
    monkeypatch.setattr(self_update, "_in_docker", lambda: False)
    monkeypatch.setattr(self_update.shutil, "which", _fake_which)

    def fake_run(cmd: list[str], **_kwargs: object) -> _Completed:
        _write_tool_stamp(data_home, commit="newcommit")
        return _Completed()

    monkeypatch.setattr(self_update.subprocess, "run", fake_run)
    monkeypatch.setattr(self_update, "_read_version", lambda: "0.1.1")

    result = self_update.update_jobbot()
    assert result.ok is True
    assert result.already_latest is False
    assert "Updated" in result.message


def test_cli_update_exits_nonzero_without_uv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from jobbot.cli import run_cli

    monkeypatch.setattr(self_update, "_in_docker", lambda: False)
    monkeypatch.setattr(self_update.shutil, "which", lambda _name: None)
    monkeypatch.setattr(self_update, "_home", lambda: tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()

    code = run_cli(["update"], standalone_mode=False)
    assert code == GENERIC_FAILURE


def test_cli_update_already_latest_is_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from jobbot.cli import run_cli

    monkeypatch.setattr(
        "jobbot.cli.update_jobbot",
        lambda **_k: self_update.UpdateResult(
            ok=True,
            message="Already on latest production (main).",
            version_line="0.1.0",
            already_latest=True,
        ),
    )
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()

    code = run_cli(["update"], standalone_mode=False)
    assert code == SUCCESS
    out = capsys.readouterr().out.casefold()
    assert "already" in out


def _write_tool_stamp(data_home: Path, *, commit: str) -> None:
    dist = (
        data_home
        / "uv"
        / "tools"
        / "jobbot"
        / "lib"
        / "python3.12"
        / "site-packages"
        / "jobbot-0.1.0.dist-info"
    )
    dist.mkdir(parents=True, exist_ok=True)
    payload = {
        "url": "https://github.com/ljofreflor/jobbot",
        "vcs_info": {
            "vcs": "git",
            "commit_id": commit,
            "requested_revision": "main",
        },
    }
    (dist / "direct_url.json").write_text(json.dumps(payload), encoding="utf-8")
