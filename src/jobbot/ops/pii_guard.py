"""Block real PII from entering git (pre-commit guard). Local only, no network."""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import PurePosixPath

# Paths that must never be tracked, even with `git add -f`.
_BLOCKED_PATHS: tuple[tuple[str, str], ...] = (
    (r"^data/profile\.yaml$", "real candidate source of truth"),
    (r"^data/profile\.generated\.yaml$", "derived from private LaTeX CV"),
    (r"^data/profile\.suggested\.yaml$", "derived from market feedback"),
    (r"^data/portals\.yaml$", "learned portals may include real applications"),
    (r"^data/.*\.bak$", "profile backup"),
    (r"^latex/cv\.tex$", "private LaTeX CV (only cv.tex.demo is tracked)"),
    (r"^\.jobbot\.toml$", "local config with private paths"),
    (r"^browser-data/", "browser session data"),
    (r"^output/", "generated artefacts with PII"),
    (r"\.sqlite3?$", "local database"),
    (r"\.db$", "local database"),
    (r"^(?!latex/).*\.pdf$", "PDF CV / attachment"),
    (r"^AGENTS\.md$", "local agent policy, not for remote"),
    (r"^\.cursor/", "local editor/agent config"),
)

# Files allowed to contain example-looking PII (fixtures, templates, this guard).
_ALLOWED_PATHS: tuple[str, ...] = (
    r"^tests/",
    r"^data/.*\.example\.yaml$",
    r"^latex/cv\.tex\.demo$",
    r"^src/jobbot/ops/pii_guard\.py$",
    r"^src/jobbot/portals/email_apply\.py$",
    r"^\.gitignore$",
    r"^uv\.lock$",
)

# Domains that are obviously placeholders.
_ALLOWED_EMAIL_DOMAINS: tuple[str, ...] = (
    "example.com",
    "example.org",
    "example.net",
    "example.cl",
    "empresa.cl",
    "acme.com",
    "localhost",
)

_EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+\-]+@([a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})\b")
_CL_PHONE_RE = re.compile(r"\+\s?56[\s\-.,]*9[\s\-.,]*\d{4}[\s\-.,]*\d{4}")
_RUT_RE = re.compile(r"\b\d{1,2}\.\d{3}\.\d{3}\s*-\s*[\dkK]\b")
_HOME_PATH_RE = re.compile(r"/Users/[A-Za-z0-9._\-]+/")
_IMPORT_HEADER_RE = re.compile(r"#\s*Source:\s*/", re.I)


@dataclass(frozen=True)
class Finding:
    path: str
    reason: str
    detail: str = ""


def is_blocked_path(path: str) -> str | None:
    """Reason why ``path`` must not be committed, or None."""
    norm = str(PurePosixPath(path))
    for pattern, reason in _BLOCKED_PATHS:
        if re.search(pattern, norm):
            return reason
    return None


def is_allowed_content_path(path: str) -> bool:
    norm = str(PurePosixPath(path))
    return any(re.search(pattern, norm) for pattern in _ALLOWED_PATHS)


def scan_text(text: str, path: str) -> list[Finding]:
    """Find likely-real PII in file content (skips fixtures/templates)."""
    if is_allowed_content_path(path):
        return []
    findings: list[Finding] = []
    for match in _EMAIL_RE.finditer(text):
        domain = match.group(1).casefold()
        if domain in _ALLOWED_EMAIL_DOMAINS:
            continue
        findings.append(Finding(path, "real-looking email", match.group(0)))
    if _CL_PHONE_RE.search(text):
        findings.append(Finding(path, "phone number", "+56 9 …"))
    if _RUT_RE.search(text):
        findings.append(Finding(path, "RUT", "nn.nnn.nnn-n"))
    for match in _HOME_PATH_RE.finditer(text):
        findings.append(Finding(path, "absolute home path", match.group(0)))
    if _IMPORT_HEADER_RE.search(text):
        findings.append(Finding(path, "import-latex header with local source path", ""))
    return findings


def redact(text: str) -> str:
    """Replace contact data with placeholders, keeping surrounding text.

    Used wherever text leaves the candidate's own files (failure payloads that
    may become GitHub issues, learned form labels, LLM prompts). Same patterns
    as the commit guard, so a change to what counts as PII lands in both places.
    """
    if not text:
        return text
    out = _EMAIL_RE.sub("[email]", text)
    out = _CL_PHONE_RE.sub("[phone]", out)
    out = _RUT_RE.sub("[id]", out)
    return _HOME_PATH_RE.sub("[path]/", out)


def _git(args: list[str]) -> str:
    proc = subprocess.run(  # noqa: S603
        ["git", *args],
        check=False,
        capture_output=True,
        text=True,
    )
    return proc.stdout


def staged_paths() -> list[str]:
    out = _git(["diff", "--cached", "--name-only", "--diff-filter=ACMR"])
    return [line.strip() for line in out.splitlines() if line.strip()]


def staged_content(path: str) -> str:
    return _git(["show", f":{path}"])


def scan_staged() -> list[Finding]:
    """Scan the git index for blocked paths and PII content."""
    findings: list[Finding] = []
    for path in staged_paths():
        reason = is_blocked_path(path)
        if reason is not None:
            findings.append(Finding(path, f"blocked path ({reason})"))
            continue
        findings.extend(scan_text(staged_content(path), path))
    return findings


def format_report(findings: list[Finding]) -> str:
    lines = ["PII guard blocked this commit:", ""]
    for f in findings:
        detail = f" → {f.detail}" if f.detail else ""
        lines.append(f"  {f.path}: {f.reason}{detail}")
    lines.extend(
        [
            "",
            "Fix: unstage the file (git restore --staged PATH) or replace real data",
            "with an *.example.yaml / fixture value. Never commit real PII.",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    findings = scan_staged()
    if not findings:
        return 0
    print(format_report(findings), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
