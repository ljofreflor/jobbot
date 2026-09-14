"""Helpers for attaching to a user-launched Chrome (CDP) — HITL, no CAPTCHA bypass."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

DEFAULT_CDP_URL = "http://127.0.0.1:9222"
DEFAULT_CDP_PORT = 9222


def resolve_cdp_url(
    explicit: str | None = None,
    *,
    env: dict[str, str] | None = None,
) -> str | None:
    """Prefer CLI/explicit, then JOBBOT_CDP_URL. Empty string means disabled."""
    if explicit is not None:
        return explicit.strip() or None
    env_map = env if env is not None else os.environ
    raw = env_map.get("JOBBOT_CDP_URL")
    if raw is None:
        return None
    return raw.strip() or None


def find_chrome_executable() -> Path | None:
    mac = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if mac.is_file():
        return mac
    which = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chrome")
    return Path(which) if which else None


def chrome_debug_argv(
    *,
    profile_dir: Path,
    port: int = DEFAULT_CDP_PORT,
    start_url: str = "https://cl.indeed.com/",
    chrome: Path | None = None,
) -> list[str]:
    """Argv to launch a normal Chrome with remote debugging (user owns the window)."""
    exe = chrome or find_chrome_executable()
    if exe is None:
        msg = "Google Chrome not found; install it or pass chrome=…"
        raise FileNotFoundError(msg)
    return [
        str(exe),
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        start_url,
    ]


def cdp_http_url(port: int = DEFAULT_CDP_PORT) -> str:
    return f"http://127.0.0.1:{port}"
