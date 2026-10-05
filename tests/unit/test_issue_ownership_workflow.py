"""The issue-ownership workflow stamps `cursor` without a stored token."""

from __future__ import annotations

from pathlib import Path

import yaml


def test_issue_ownership_workflow_stamps_cursor_with_issues_write(
    project_root: Path,
) -> None:
    path = project_root / ".github" / "workflows" / "issue-ownership.yml"
    raw = path.read_text(encoding="utf-8")
    doc = yaml.safe_load(raw)
    trigger = doc.get("on") or doc[True]

    assert doc["name"] == "Issue ownership"
    assert "opened" in trigger["issues"]["types"]
    assert "workflow_dispatch" in trigger
    assert doc["permissions"]["issues"] == "write"
    assert doc["permissions"]["contents"] == "read"
    assert "cursor" in raw
    assert "secrets." not in raw
    assert "GITHUB_TOKEN" not in raw
    assert "addAssignees" not in raw
    assert "add-assignee" not in raw
    job = doc["jobs"]["stamp-cursor"]
    uses = job["steps"][0]["uses"]
    assert uses.startswith("actions/github-script@")
    pin = uses.split("@", 1)[1]
    assert pin.split()[0] != "v7", "pin the commit SHA, not a floating tag"
