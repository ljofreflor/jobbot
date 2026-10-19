"""A public catalog line that carries contact data or a home path is not shareable."""

from __future__ import annotations

from jobbot.ops.pii_guard import scan_text

_QUEUE_PATH = "share-queue.yaml"


def share_refusal(text: str) -> str | None:
    """The guard's reason, or None. The matched contact value is not returned."""
    findings = scan_text(text or "", _QUEUE_PATH)
    if not findings:
        return None
    return findings[0].reason
