"""jobbot update — uv tool reinstall / Docker hint."""

from __future__ import annotations

from pathlib import Path

import pytest

from jobbot import self_update


def test_update_in_docker_returns_pull_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(self_update, "_in_docker", lambda: True)
    result = self_update.update_jobbot()
    assert result.ok is False
    assert "docker pull" in result.message.casefold()


def test_update_without_uv_points_at_install_script(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(self_update, "_in_docker", lambda: False)
    monkeypatch.setattr(self_update.shutil, "which", lambda _name: None)
    result = self_update.update_jobbot()
    assert result.ok is False
    assert "install.sh" in result.message


def _fake_which(name: str) -> str | None:
    return "/usr/bin/uv" if name == "uv" else None


def test_update_runs_uv_tool_install(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(self_update, "_in_docker", lambda: False)
    monkeypatch.setattr(self_update.shutil, "which", _fake_which)

    calls: list[list[str]] = []

    class _Completed:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd: list[str], **_kwargs: object) -> _Completed:
        calls.append(list(cmd))
        return _Completed()

    monkeypatch.setattr(self_update.subprocess, "run", fake_run)
    monkeypatch.setattr(self_update, "_read_version", lambda: "0.1.0")

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

    class _Completed:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(
        self_update.subprocess,
        "run",
        lambda cmd, **_k: calls.append(list(cmd)) or _Completed(),
    )
    monkeypatch.setattr(self_update, "_read_version", lambda: "0.1.0")

    result = self_update.update_jobbot(source=f"wheel:{wheel}")
    assert result.ok is True
    assert calls[0][-1] == str(wheel)
