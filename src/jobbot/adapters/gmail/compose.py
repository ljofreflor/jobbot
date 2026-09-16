"""Prepare a Gmail draft with the CV attached. HITL: the user presses Send."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from jobbot.adapters.ats.email_apply import EmailApplyDraft, gmail_compose_url
from jobbot.adapters.gmail import selectors
from jobbot.browser.session import BrowserSession
from jobbot.config import JobbotConfig

logger = logging.getLogger("jobbot.gmail")

_UPLOAD_TIMEOUT_MS = 60_000


class GmailComposeError(RuntimeError):
    """Compose could not be prepared (DOM changed, upload not confirmed, …)."""


class GmailAuthRequired(GmailComposeError):
    """Gmail asked for login; the user completes it in the browser window."""


def is_auth_url(url: str) -> bool:
    return "accounts.google.com" in (url or "").casefold()


def attachment_chip_selector(filename: str) -> str:
    return f"text={filename}"


def prepare_gmail_draft(
    page: Any,
    draft: EmailApplyDraft,
    *,
    cv_path: Path | None = None,
    timeout_ms: int = 30_000,
) -> str:
    """
    Open Gmail compose prefilled from `draft` and upload the CV as attachment.

    Leaves the compose window open for review; never clicks Send.
    """
    attachment = cv_path or draft.cv_path
    if attachment is None or not attachment.is_file():
        msg = f"CV to attach not found: {attachment or '(none)'}"
        raise GmailComposeError(msg)

    url = gmail_compose_url(draft)
    page.goto(url, wait_until="domcontentloaded")
    if is_auth_url(page.url):
        msg = "Gmail requires login before composing"
        raise GmailAuthRequired(msg)
    page.wait_for_selector(selectors.COMPOSE_READY, timeout=timeout_ms)
    _attach(page, attachment, timeout_ms=timeout_ms)
    return url


def _attach(page: Any, cv_path: Path, *, timeout_ms: int) -> None:
    file_inputs = page.locator(selectors.FILE_INPUT)
    if file_inputs.count() > 0:
        file_inputs.first.set_input_files(str(cv_path))
    else:
        with page.expect_file_chooser(timeout=timeout_ms) as chooser:
            page.click(selectors.ATTACH_BUTTON)
        chooser.value.set_files(str(cv_path))

    try:
        page.wait_for_selector(
            attachment_chip_selector(cv_path.name),
            timeout=max(timeout_ms, _UPLOAD_TIMEOUT_MS),
        )
    except Exception as exc:  # noqa: BLE001 — Playwright timeout types vary
        msg = f"Attachment {cv_path.name} did not appear in the Gmail draft"
        raise GmailComposeError(msg) from exc


class GmailComposeAdapter:
    """Own Gmail session (persistent profile), same pattern as Indeed/LinkedIn."""

    def __init__(self, config: JobbotConfig, *, cdp_url: str | None = None) -> None:
        from jobbot.browser.cdp import resolve_cdp_url

        self.config = config
        self.profile_dir = config.root / "browser-data" / "gmail"
        self.debug_root = config.output_dir / "debug"
        self.cdp_url = resolve_cdp_url(cdp_url)

    def _session(self) -> BrowserSession:
        return BrowserSession(
            profile_dir=self.profile_dir,
            headless=False,
            slow_mo=100,
            debug_root=self.debug_root,
            cdp_url=self.cdp_url,
        )

    def open_draft_for_review(
        self,
        draft: EmailApplyDraft,
        *,
        cv_path: Path | None = None,
    ) -> str:
        """Attach the CV in a real Gmail draft and hold the window open for review."""
        with self._session() as browser:
            # Attached to the user's own Chrome: never hijack a tab they are using.
            page = browser.context.new_page() if self.cdp_url else browser.page
            try:
                url = prepare_gmail_draft(page, draft, cv_path=cv_path)
            except GmailAuthRequired:
                ok = browser.pause_for_manual(
                    "Gmail requires login. Log in (including 2FA) in the browser window.",
                    is_clear=lambda: not is_auth_url(page.url),
                    timeout_seconds=300,
                )
                if not ok:
                    msg = "Gmail login was not completed"
                    raise GmailComposeError(msg) from None
                url = prepare_gmail_draft(page, draft, cv_path=cv_path)
            except GmailComposeError:
                browser.dump_debug("gmail", "compose-failed", job_id=draft.job_id)
                raise

            browser.pause_for_manual(
                "Draft ready in Gmail with the CV attached.\n"
                "Review recipient, subject, body and attachment, then press Send yourself.\n"
                "JobBot will not send it.",
                timeout_seconds=1_800,
                continue_sentinel=self.review_sentinel(draft.job_id),
            )
            return url

    def review_sentinel(self, job_id: str) -> Path | None:
        """Non-tty runs (agents) hold the window open until this file appears."""
        if sys.stdin.isatty():
            return None
        return self.config.output_dir / "ops" / f"gmail-review-{job_id}.continue"
