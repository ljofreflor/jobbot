"""Indeed adapter — login, inspect, pull, full resume sync from profile.yaml."""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from rich.console import Console

from jobbot.adapters.diff_engine import build_sync_plan, load_snapshot, save_snapshot
from jobbot.adapters.html_parse import parse_indeed_profile_html
from jobbot.adapters.indeed import selectors
from jobbot.adapters.indeed.package import (
    build_indeed_sync_package,
    render_sync_package_markdown,
)
from jobbot.adapters.indeed.resume_edit import (
    DOCUMENT_ONLY_MESSAGE,
    PREFERENCES_TAB_MISSING,
    IndeedUiChanged,
    apply_full_resume_from_candidate,
    apply_resume_sections,
    ensure_structured_editor,
    open_resume,
    parse_resume_page_text,
    preferences_tab_missing,
    record_editor_state,
    resume_editor_state,
    wait_for_resume_render,
)
from jobbot.browser.debug import inspect_page
from jobbot.browser.session import BrowserSession
from jobbot.config import JobbotConfig, load_config
from jobbot.models.external_profile import ExternalProfile
from jobbot.models.sync import SyncPlan, SyncResult
from jobbot.profile.loader import load_profile

logger = logging.getLogger("jobbot.indeed")
console = Console()

_MARKETING_HEADLINE_MARKERS = (
    "siguiente paso",
    "ready for your next",
    "get started",
    "sign in",
    "iniciar sesión",
)


class IndeedAdapter:
    def __init__(
        self,
        config: JobbotConfig,
        *,
        cdp_url: str | None = None,
    ) -> None:
        self.config = config
        self.profile_dir = config.browser_profile_dir("indeed")
        self.debug_root = config.output_dir / "debug"
        from jobbot.browser.cdp import resolve_cdp_url

        self.cdp_url = resolve_cdp_url(cdp_url)

    @classmethod
    def from_config(
        cls,
        config: JobbotConfig | None = None,
        *,
        cdp_url: str | None = None,
    ) -> IndeedAdapter:
        return cls(config or load_config(), cdp_url=cdp_url)

    def _session(self) -> BrowserSession:
        return BrowserSession(
            profile_dir=self.profile_dir,
            headless=False,
            slow_mo=100,
            debug_root=self.debug_root,
            cdp_url=self.cdp_url,
        )

    def _wait_logged_in(self, browser: BrowserSession) -> bool:
        if not _is_auth_url(browser.page.url):
            return True
        return browser.pause_for_manual(
            "Indeed requires login. Complete it in the browser window.",
            is_clear=lambda: not _is_auth_url(browser.page.url),
            timeout_seconds=300,
        )

    def login(self, *, continue_url: str | None = None) -> None:
        """HITL Indeed login. Prefer email / magic link; never type a password.

        ``continue_url`` is the link from Indeed's email (magic link / verify).
        Paste it from your phone mail into this command on the desktop session.
        JobBot cannot force Indeed to offer magic link — only open what they sent.
        """
        with self._session() as browser:
            if continue_url:
                target = normalize_indeed_continue_url(continue_url)
                console.print(
                    "[bold]Opening Indeed continue / magic link[/bold] "
                    "(HITL; JobBot does not invent credentials)."
                )
                browser.page.goto(target, wait_until="domcontentloaded")
            else:
                browser.page.goto(selectors.INDEED_LOGIN, wait_until="domcontentloaded")
                console.print(
                    "[bold]Indeed login (HITL)[/bold]\n"
                    "1. Prefer [bold]email / magic link / código[/bold] if Indeed shows it.\n"
                    "2. JobBot [bold]never[/bold] types your password or solves CAPTCHA.\n"
                    "3. If the mail arrives on your phone, copy the link and run:\n"
                    "   [dim]jobbot indeed login --continue-url 'PEGAR_LINK'[/dim]"
                )
            ok = browser.pause_for_manual(
                "Finish Indeed sign-in in the browser (magic link, OTP, or CAPTCHA). "
                "Password stays yours.",
                is_clear=lambda: not _is_auth_url(browser.page.url),
                timeout_seconds=300,
            )
            if not ok:
                console.print("[red]Login not completed in time.[/red]")
                return
            browser.page.goto(selectors.INDEED_HOME, wait_until="domcontentloaded")
            console.print("[green]Indeed login flow finished. Session persisted.[/green]")

    def session_valid(self) -> bool:
        try:
            with self._session() as browser:
                browser.page.goto(selectors.INDEED_HOME, wait_until="domcontentloaded")
                return _session_authenticated(browser.page)
        except Exception as exc:  # noqa: BLE001
            logger.warning("session check failed: %s", exc)
            return False

    def inspect(self) -> None:
        with self._session() as browser:
            browser.page.goto(selectors.INDEED_RESUME, wait_until="domcontentloaded")
            self._wait_logged_in(browser)
            inspect_page(browser.page, console)

    def prepare_package(self) -> Path:
        """Write markdown package of profile.yaml → Indeed fields (no portal write)."""
        candidate = load_profile(self.config.profile_path)
        package = build_indeed_sync_package(candidate)
        out = self.config.output_dir / "indeed" / "sync_package.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_sync_package_markdown(package), encoding="utf-8")
        return out

    def pull_profile(self) -> ExternalProfile:
        with self._session() as browser:
            browser.page.goto(selectors.INDEED_RESUME, wait_until="domcontentloaded")
            if not self._wait_logged_in(browser):
                browser.dump_debug("indeed", "pull_login_timeout")
                msg = "Indeed login required before pull"
                raise RuntimeError(msg)
            if _is_auth_url(browser.page.url):
                browser.page.goto(selectors.INDEED_RESUME, wait_until="domcontentloaded")
            wait_for_resume_render(browser.page)
            html = browser.page.content()
            if preferences_tab_missing(str(browser.page.url), html):
                raise IndeedUiChanged(PREFERENCES_TAB_MISSING)
            if resume_editor_state(browser.page.url, html) == "document_only":
                raise IndeedUiChanged(DOCUMENT_ONLY_MESSAGE)
            body = browser.page.inner_text("body")
            try:
                profile = parse_indeed_profile_html(html)
            except Exception:
                browser.dump_debug("indeed", "pull_profile")
                raise
            parsed = parse_resume_page_text(body)
            if parsed.get("summary") and not profile.summary:
                profile.summary = str(parsed["summary"])
            if parsed.get("skills") and not profile.skills:
                raw_skills = parsed["skills"]
                if isinstance(raw_skills, list):
                    profile.skills = [str(s) for s in raw_skills]
                else:
                    profile.skills = []
            if _looks_like_marketing_headline(profile.headline):
                profile.headline = None
            if not profile.headline and not profile.summary and not profile.experience:
                candidate = load_profile(self.config.profile_path)
                browser.dump_debug("indeed", "pull_sparse")
                console.print(
                    "[yellow]Indeed resume DOM was sparse; snapshot may be incomplete.[/yellow]"
                )
                return ExternalProfile(
                    source="indeed",
                    headline=None,
                    summary=profile.summary,
                    location=candidate.personal.location_line(),
                    experience=profile.experience,
                    education=profile.education,
                    skills=profile.skills,
                    captured_at=datetime.now(UTC),
                )
            return profile

    def pull_and_save(self) -> Path:
        try:
            profile = self.pull_profile()
        except IndeedUiChanged:
            record_editor_state(self.config.output_dir, "document_only")
            raise
        record_editor_state(self.config.output_dir, "structured")
        return save_snapshot(profile, self.config.output_dir)

    def build_sync_plan(self, *, section: str | None = "headline") -> SyncPlan:
        candidate = load_profile(self.config.profile_path)
        external = load_snapshot(self.config.output_dir, "indeed")
        if external is None:
            external = self.pull_profile()
            save_snapshot(external, self.config.output_dir)
        sec = None if section in (None, "all") else section
        return build_sync_plan("indeed", candidate, external, section=sec)

    def apply_sync_plan(self, plan: SyncPlan, *, section: str = "all") -> SyncResult:
        """Apply profile.yaml → Indeed Resume editor (add-mostly; prefer reconcile for mirror)."""
        if not plan.actionable:
            return SyncResult(target="indeed", verified=True, message="No changes required.")

        candidate = load_profile(self.config.profile_path)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        before_path = self.config.output_dir / "snapshots" / "indeed" / f"before-sync-{stamp}.json"
        external = load_snapshot(self.config.output_dir, "indeed")
        if external:
            before_path.write_text(external.model_dump_json(indent=2), encoding="utf-8")

        with self._session() as browser:
            browser.page.goto(selectors.INDEED_RESUME, wait_until="domcontentloaded")
            if not self._wait_logged_in(browser):
                return SyncResult(
                    target="indeed",
                    applied=[],
                    verified=False,
                    message="Login required; sync aborted.",
                )

            console.print(
                "[bold]Applying Indeed Resume from profile.yaml[/bold] "
                "(no PDF upload; publications are not synced to Recognitions)."
            )
            ensure_structured_editor(browser.page)
            if section in (None, "", "all"):
                edit = apply_full_resume_from_candidate(browser.page, candidate)
            else:
                edit = apply_resume_sections(browser.page, candidate, {section})
            console.print(
                f"summary={edit.summary} headline={edit.headline} "
                f"experiences+={edit.experiences_added} skills+={edit.skills_added} "
                f"education+={edit.education_added}"
            )
            for err in edit.errors:
                console.print(f"[yellow]{err}[/yellow]")

            return self._snapshot_after(browser, candidate, plan, stamp, edit_verified=True)

    def apply_reconcile(self) -> SyncResult:
        """Full mirror: update/add/delete Indeed Resume to match profile.yaml."""
        from jobbot.adapters.indeed.reconcile import reconcile_resume_to_candidate

        candidate = load_profile(self.config.profile_path)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        with self._session() as browser:
            browser.page.goto(selectors.INDEED_RESUME, wait_until="domcontentloaded")
            if not self._wait_logged_in(browser):
                return SyncResult(
                    target="indeed",
                    applied=[],
                    verified=False,
                    message="Login required; reconcile aborted.",
                )
            console.print(
                "[bold]Reconciling Indeed Resume → full mirror of profile.yaml[/bold]\n"
                "Publications stay in profile only (not Indeed Recognitions)."
            )
            ensure_structured_editor(browser.page)
            result = reconcile_resume_to_candidate(browser.page, candidate)
            console.print(
                f"summary={result.summary} headline={result.headline} "
                f"exp ~{result.experiences_updated}/+{result.experiences_added}"
                f"/-{result.experiences_deleted} "
                f"edu ~{result.education_updated}/+{result.education_added}"
                f"/-{result.education_deleted} "
                f"skills +{result.skills_added}/-{result.skills_removed}"
            )
            for err in result.errors:
                console.print(f"[yellow]{err}[/yellow]")
            verified = bool(
                result.summary
                or result.experiences_updated
                or result.experiences_added
                or result.education_updated
                or result.education_added
            )
            msg = (
                f"Indeed reconcile finished. "
                f"exp~{result.experiences_updated}+{result.experiences_added}"
                f"-{result.experiences_deleted} "
                f"edu~{result.education_updated}+{result.education_added}"
                f"-{result.education_deleted} "
                f"skills+{result.skills_added}-{result.skills_removed} "
                f"errors={len(result.errors)}"
            )
            # empty plan placeholder for SyncResult.applied
            plan = SyncPlan(target="indeed", operations=[])
            snap = self._snapshot_after(browser, candidate, plan, stamp, edit_verified=verified)
            return SyncResult(
                target="indeed",
                applied=snap.applied,
                verified=verified,
                message=msg,
            )

    def _snapshot_after(
        self,
        browser: BrowserSession,
        candidate: object,
        plan: SyncPlan,
        stamp: str,
        *,
        edit_verified: bool,
    ) -> SyncResult:
        from jobbot.models.candidate import Candidate

        assert isinstance(candidate, Candidate)
        open_resume(browser.page)
        wait_for_resume_render(browser.page)
        body = browser.page.inner_text("body")
        parsed = parse_resume_page_text(body)
        skills_val = parsed.get("skills")
        skills = [str(s) for s in skills_val] if isinstance(skills_val, list) else []
        summary_val = parsed.get("summary")
        summary = str(summary_val) if isinstance(summary_val, str) and summary_val else None
        rendered = parse_indeed_profile_html(browser.page.content())
        read_headline = rendered.headline
        if _looks_like_marketing_headline(read_headline):
            read_headline = None
        # A resume that did not render is not a resume that lost its history.
        # Copied rows are kept, and they do not count as a verified read.
        previous = load_snapshot(self.config.output_dir, "indeed")
        reused_previous = False
        if rendered.experience:
            experience = rendered.experience
        elif previous and previous.experience:
            experience = previous.experience
            reused_previous = True
        else:
            experience = []
        if rendered.education:
            education = rendered.education
        elif previous and previous.education:
            education = previous.education
            reused_previous = True
        else:
            education = []
        if skills:
            stored_skills = skills
        elif previous and previous.skills:
            stored_skills = previous.skills
            reused_previous = True
        else:
            stored_skills = []
        observed = ExternalProfile(
            source="indeed",
            headline=read_headline,
            summary=summary,
            location=candidate.personal.location_line(),
            experience=experience,
            education=education,
            skills=stored_skills,
            captured_at=datetime.now(UTC),
        )
        save_snapshot(observed, self.config.output_dir)
        after_path = self.config.output_dir / "snapshots" / "indeed" / f"after-sync-{stamp}.json"
        after_path.write_text(observed.model_dump_json(indent=2), encoding="utf-8")
        verified = bool(edit_verified and read_headline is not None and not reused_previous)
        return SyncResult(
            target="indeed",
            applied=list(plan.actionable),
            verified=verified,
            message="Snapshot saved.",
        )


# A greeting marks a signed-in Indeed page. The name after the comma is never kept.
_GREETING = re.compile(r"\b(?:hola|hi|hello),\s+\S+", re.IGNORECASE)


def indeed_session_authenticated(
    *,
    url: str,
    html: str,
    cookie_names: Sequence[str],
) -> bool:
    """True only with an account menu, a greeting, or a confirmed session cookie.

    The visitor cookie ``CTK`` is present on a logged-out browser and is not
    a session. ``SOCK`` and ``SHOE`` were observed on a signed-in profile.
    """
    if _is_auth_url(url):
        return False
    names = {name.casefold() for name in cookie_names}
    if "sock" in names or "shoe" in names:
        return True
    if _GREETING.search(html or ""):
        return True
    lowered = (html or "").casefold()
    return any(marker in lowered for marker in ("account-menu", "cerrar sesión", "sign out"))


def _session_authenticated(page: object) -> bool:
    url = str(getattr(page, "url", ""))
    try:
        html = str(page.content())  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        html = ""
    names: list[str] = []
    try:
        context = page.context  # type: ignore[attr-defined]
        cookies = context.cookies()
        names = [str(cookie.get("name", "")) for cookie in cookies if isinstance(cookie, dict)]
    except Exception:  # noqa: BLE001
        names = []
    return indeed_session_authenticated(url=url, html=html, cookie_names=names)


def _is_auth_url(url: str) -> bool:
    u = url.lower()
    return any(x in u for x in ("/auth", "login", "signin", "secure.indeed.com/account"))


def normalize_indeed_continue_url(url: str) -> str:
    """Accept only Indeed auth / continue links (magic link from email)."""
    raw = url.strip()
    if not raw:
        raise ValueError("Empty continue URL")
    # Accidental double-paste from iOS share / mail clients.
    second = raw.find("https://", 8)
    if second > 0:
        raw = raw[:second]
    lowered = raw.casefold()
    host_ok = any(
        h in lowered
        for h in (
            "indeed.com/",
            "secure.indeed.com",
            "smartredirect.indeed.com",
        )
    )
    if not host_ok or "://" not in raw:
        raise ValueError(
            f"Continue URL must be an Indeed link from the sign-in email (got {raw!r})"
        )
    return raw


def _looks_like_marketing_headline(headline: str | None) -> bool:
    if not headline:
        return True
    h = headline.strip().casefold()
    if h.startswith("¿") or h.endswith("?"):
        return True
    return any(m in h for m in _MARKETING_HEADLINE_MARKERS)
