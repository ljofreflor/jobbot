"""Draft (and optionally open) GitHub issues for novel / unanswered portal fields.

Gaps are good news: we learned a question. JobBot never invents the answer and
never writes ``profile.yaml``. Closing the loop is HITL — same spirit as
``ops failure issue`` — with assignee ``cursoragent``.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from jobbot.portals.ats_lifecycle import FieldGapState, field_gap_state
from jobbot.portals.field_diff import NewFieldCandidate
from jobbot.portals.form_learn import FormKnowledge

CURSOR_ASSIGNEE = "cursoragent"
CURSOR_LABEL = "cursor"


@dataclass(frozen=True)
class FieldGapIssueDraft:
    """Ready-to-review GitHub issue. Nothing is created until HITL confirm."""

    title: str
    body: str
    labels: tuple[str, ...]
    assignee: str
    gap_labels: tuple[str, ...]
    state: FieldGapState


GhRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]


def draft_field_gap_issue(
    *,
    company: str,
    portal_url: str,
    ats: str,
    gap_labels: Sequence[str],
    new_fields: Sequence[NewFieldCandidate] | None = None,
    job_id: str | None = None,
) -> FieldGapIssueDraft | None:
    """Build an issue draft from unanswered labels and/or NewFieldCandidates.

    Returns None when there is nothing to learn (no gaps).
    """
    labels = tuple(dict.fromkeys(label.strip() for label in gap_labels if label.strip()))
    novel = list(new_fields or [])
    if not labels and not novel:
        return None

    short = labels[0] if labels else novel[0].labels_seen[0]
    if len(short) > 48:
        short = short[:45] + "…"
    title = f"[product:portals] New form field(s) at {company}: {short}"

    lines = [
        "## Portal field gaps (do not invent answers)",
        "",
        f"- **company:** {company}",
        f"- **portal:** {portal_url}",
        f"- **ats:** `{ats}`",
    ]
    if job_id:
        lines.append(f"- **job:** `{job_id}`")
    lines.extend(
        [
            "",
            "Observed questions that `profile.yaml` does not answer. "
            "Extend the baseline (HITL promote) or document as portal-only.",
            "",
            "### Unanswered labels",
            "",
        ]
    )
    if labels:
        lines.extend(f"- {label}" for label in labels)
    else:
        lines.append("- (none beyond NewFieldCandidate set)")
    if novel:
        lines.extend(["", "### NewFieldCandidate (vs profile schema)", ""])
        for cand in novel:
            seen = ", ".join(cand.labels_seen[:5])
            lines.append(
                f"- `{cand.kind.value}` — {seen} "
                f"(portals={cand.frequency}, required_ratio={cand.required_ratio:.0%})"
            )
    lines.extend(
        [
            "",
            "### Checklist",
            "",
            "- [ ] Decide: add to profile schema vs portal-only",
            "- [ ] If profile: confirm fact with the candidate (never invent)",
            "- [ ] Regression: form fixture still maps or stays as gap",
            "",
            f"Lifecycle: `{FieldGapState.GAP.value}` → "
            f"`{FieldGapState.ISSUE_OPEN.value}` → "
            f"`{FieldGapState.PROFILE_EXTENDED.value}` | "
            f"`{FieldGapState.PORTAL_ONLY.value}`",
        ]
    )
    return FieldGapIssueDraft(
        title=title,
        body="\n".join(lines) + "\n",
        labels=(CURSOR_LABEL, "enhancement"),
        assignee=CURSOR_ASSIGNEE,
        gap_labels=labels,
        state=field_gap_state(unanswered=True),
    )


def gaps_from_form(
    form: FormKnowledge,
    *,
    answered_labels: Sequence[str],
) -> list[str]:
    """Labels on a readable form that were not filled from the profile."""
    if not form.readable:
        return []
    answered = {label.casefold() for label in answered_labels}
    out: list[str] = []
    for field in form.fields:
        label = field.label.strip()
        if not label:
            continue
        if label.casefold() in answered:
            continue
        # Password / terms are HITL by design, not profile gaps to promote.
        folded = label.casefold()
        if any(tok in folded for tok in ("password", "contraseña", "terms", "términos", "acepto")):
            continue
        out.append(label)
    return out


def create_field_gap_issue(
    draft: FieldGapIssueDraft,
    *,
    runner: GhRunner | None = None,
) -> str:
    """Create the GitHub issue via ``gh``. Caller must have confirmed HITL."""
    run = runner or _default_gh_runner
    cmd = [
        "gh",
        "issue",
        "create",
        "--title",
        draft.title,
        "--body",
        draft.body,
        "--assignee",
        draft.assignee,
    ]
    for label in draft.labels:
        cmd.extend(["--label", label])
    proc = run(cmd)
    if proc.returncode != 0:
        # Assignee may be unavailable; retry with label-only ownership signal.
        if draft.assignee:
            retry = [
                "gh",
                "issue",
                "create",
                "--title",
                draft.title,
                "--body",
                draft.body,
            ]
            for label in draft.labels:
                retry.extend(["--label", label])
            proc = run(retry)
        if proc.returncode != 0:
            msg = (proc.stderr or proc.stdout or "gh issue create failed").strip()
            raise RuntimeError(msg)
    return (proc.stdout or "").strip()


def _default_gh_runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=False, capture_output=True, text=True)  # noqa: S603
