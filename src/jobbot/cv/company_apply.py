"""Open an active career site and fill only what ``profile.yaml`` already answers.

Issues #43 / #44. Never invents a password, never accepts terms, never solves
CAPTCHA/2FA, never clicks create/submit. A confirmation is not a receipt.

Account path (local evidence only):
- prior receipt → login only (human types password)
- needs account, no evidence → signup_fill (+ learn gaps)
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from bs4 import BeautifulSoup

from jobbot.companies.models import KnowledgeStatus
from jobbot.companies.signup import AccountNeed, SignupItem, signup_sheet
from jobbot.companies.urls import canonical_key
from jobbot.cv.sync import CompanySyncRow
from jobbot.models.candidate import Candidate
from jobbot.portals.ats_lifecycle import (
    AccountSessionState,
    PortalAction,
    account_session_state,
    next_portal_action,
)
from jobbot.portals.field_diff import NewFieldCandidate, diff_form_fields
from jobbot.portals.field_gap_issue import (
    FieldGapIssueDraft,
    draft_field_gap_issue,
    gaps_from_form,
)
from jobbot.portals.form_learn import FieldKind, FormField, FormKnowledge, learn_form_html

RECEIPT_NAME = "company_portal_receipts.yaml"

# Irreversible or secret questions. A profile value must not be typed into these.
_FORBIDDEN_TOKENS: tuple[str, ...] = (
    "password",
    "contraseña",
    "contrasena",
    "passcode",
    "captcha",
    "recaptcha",
    "2fa",
    "otp",
    "verification code",
    "terms",
    "términos",
    "terminos",
    "privacy",
    "privacidad",
    "consent",
    "consentimiento",
    "i agree",
    "acepto",
)

_RESUME_TOKENS: tuple[str, ...] = ("resume", "cv", "curriculum", "currículum")

_FILLABLE: frozenset[FieldKind] = frozenset(
    {
        FieldKind.TEXT,
        FieldKind.EMAIL,
        FieldKind.PHONE,
        FieldKind.URL,
        FieldKind.NUMBER,
        FieldKind.DATE,
        FieldKind.LONG_TEXT,
    }
)


class MissingAdaptedCvError(ValueError):
    """Form asks for a CV but the job-adapted PDF is missing (chat-first rebuild)."""


@dataclass(frozen=True)
class CompanyApplyIntent:
    """What ``--apply`` may do for one active company row. No browser yet."""

    company_id: str
    company_name: str
    url: str
    mode: str
    sheet: tuple[SignupItem, ...]
    cv_path: Path | None
    note: str
    session_state: AccountSessionState = AccountSessionState.NOT_NEEDED
    job_id: str | None = None
    require_adapted_cv: bool = False


@dataclass(frozen=True)
class CompanyApplyResult:
    """What an apply step did. ``submitted`` is always false."""

    company_id: str
    mode: str
    opened: bool
    filled: tuple[str, ...]
    attached: bool
    receipt_path: Path | None
    submitted: bool
    gap_labels: tuple[str, ...] = ()
    new_fields: tuple[NewFieldCandidate, ...] = ()
    gap_issue: FieldGapIssueDraft | None = None
    form: FormKnowledge | None = None


@dataclass(frozen=True)
class CompanyPortalReceipt:
    """Local evidence copied from a page, never from a confirmation prompt."""

    company_id: str
    url: str
    evidence: str
    sha256: str = ""
    observed_at: datetime | None = None


def resolve_job_adapted_cv(output_dir: Path, job_id: str) -> Path | None:
    """CV adapted to a job (chat-first build). Never falls back to base."""
    for path in (
        output_dir / "jobs" / job_id / "application" / "cv.pdf",
        output_dir / "jobs" / job_id / "cv.pdf",
    ):
        if _attachable_pdf(path) is not None:
            return path
    return None


def company_apply_intent(
    row: CompanySyncRow,
    candidate: Candidate,
    *,
    cv_path: Path | None,
    form: FormKnowledge | None = None,
    has_account_evidence: bool | None = None,
    job_id: str | None = None,
) -> CompanyApplyIntent:
    """Choose login, signup_fill, fill, or skip. Does not open a page."""
    sheet = tuple(signup_sheet(candidate, form=form))
    evidenced = (
        row.session_evidenced if has_account_evidence is None else has_account_evidence
    )

    if row.status is not KnowledgeStatus.ACTIVE or row.action not in {
        "needs_account",
        "update_profile",
    }:
        return CompanyApplyIntent(
            company_id=row.company_id,
            company_name=row.company_name,
            url=row.url,
            mode=PortalAction.SKIP.value,
            sheet=sheet,
            cv_path=_attachable_pdf(cv_path),
            note=row.hint,
            session_state=AccountSessionState.NOT_NEEDED,
            job_id=job_id,
        )

    if row.action == "needs_account":
        session = account_session_state(
            need=row.need if row.need is not AccountNeed.UNKNOWN else AccountNeed.NEEDED,
            has_account_evidence=evidenced,
            has_profile_receipt=False,
        )
        # UNKNOWN without evidence still signup_fill (do not assume away).
        if row.need is AccountNeed.UNKNOWN and not evidenced:
            session = AccountSessionState.NEEDS_SIGNUP
        action = next_portal_action(
            knowledge=row.status,
            session=session,
            sync_action=row.action,
        )
    else:
        # update_profile: fill known fields (Greenhouse) or after account exists.
        session = account_session_state(
            need=row.need,
            has_account_evidence=evidenced,
            has_profile_receipt=evidenced,
        )
        if row.need is AccountNeed.NOT_NEEDED or evidenced:
            action = PortalAction.FILL
            session = (
                AccountSessionState.NOT_NEEDED
                if row.need is AccountNeed.NOT_NEEDED
                else AccountSessionState.PROFILE_PRESENT
            )
        else:
            action = next_portal_action(
                knowledge=row.status,
                session=session,
                sync_action=row.action,
            )

    require_adapted = bool(job_id) and action in {
        PortalAction.SIGNUP_FILL,
        PortalAction.FILL,
    }
    return CompanyApplyIntent(
        company_id=row.company_id,
        company_name=row.company_name,
        url=row.url,
        mode=action.value,
        sheet=sheet,
        cv_path=_attachable_pdf(cv_path),
        note=_note_for(action, row.company_name),
        session_state=session,
        job_id=job_id,
        require_adapted_cv=require_adapted,
    )


def perform_company_apply(
    intent: CompanyApplyIntent,
    candidate: Candidate,
    *,
    page: Any | None,
    output_dir: Path,
    ats: str = "unknown",
) -> CompanyApplyResult:
    """Open + fill when mode allows. Login only opens. Nothing is submitted."""
    if intent.mode == "login":
        if page is None:
            return _empty_result(intent)
        page.goto(intent.url, wait_until="domcontentloaded")
        return CompanyApplyResult(
            company_id=intent.company_id,
            mode=intent.mode,
            opened=True,
            filled=(),
            attached=False,
            receipt_path=None,
            submitted=False,
        )

    if intent.mode not in {"fill", "signup_fill"} or page is None:
        return _empty_result(intent)

    page.goto(intent.url, wait_until="domcontentloaded")
    form = learn_form_html(page.content(), url=intent.url, company=intent.company_name)
    cv_path = intent.cv_path
    if _form_asks_resume(form):
        if intent.require_adapted_cv and intent.job_id:
            adapted = resolve_job_adapted_cv(output_dir, intent.job_id)
            if adapted is None:
                raise MissingAdaptedCvError(
                    f"Form asks for a CV but no adapted PDF at "
                    f"output/jobs/{intent.job_id}/cv.pdf. "
                    "Adapt presentation in Cursor chat, then: "
                    f"jobbot cv build --job {intent.job_id} "
                    "(no API key — chat-first)."
                )
            cv_path = adapted
        elif intent.job_id:
            cv_path = resolve_job_adapted_cv(output_dir, intent.job_id) or cv_path

    filled, attached = _fill_page(page, form, candidate, cv_path)
    receipt = observe_company_presence(
        page.content(),
        candidate,
        company_id=intent.company_id,
        url=intent.url,
        pdf_path=cv_path,
    )
    receipt_path = write_company_receipt(output_dir, receipt) if receipt is not None else None

    gap_labels = tuple(gaps_from_form(form, answered_labels=filled))
    new_fields = tuple(diff_form_fields([form], min_frequency=1)) if form.readable else ()
    gap_issue = draft_field_gap_issue(
        company=intent.company_name,
        portal_url=intent.url,
        ats=ats,
        gap_labels=gap_labels,
        new_fields=new_fields,
        job_id=intent.job_id,
    )
    return CompanyApplyResult(
        company_id=intent.company_id,
        mode=intent.mode,
        opened=True,
        filled=filled,
        attached=attached,
        receipt_path=receipt_path,
        submitted=False,
        gap_labels=gap_labels,
        new_fields=new_fields,
        gap_issue=gap_issue,
        form=form,
    )


def observe_company_presence(
    html: str,
    candidate: Candidate,
    *,
    company_id: str,
    url: str,
    pdf_path: Path | None = None,
) -> CompanyPortalReceipt | None:
    """Receipt only when visible page text contains a profile fact.

    Input values are ignored, so fields we just typed are not evidence, and a
    confirmation prompt never reaches this function.
    """
    text = _visible_text(html)
    folded = text.casefold()
    personal = candidate.personal
    shown: list[str] = []
    name = (personal.name or "").strip()
    email = str(personal.email or "").strip()
    if name and name.casefold() in folded:
        shown.append(name)
    if email and email.casefold() in folded:
        shown.append(email)
    if not shown:
        return None
    sha = ""
    if (
        pdf_path is not None
        and pdf_path.is_file()
        and pdf_path.name.casefold() in folded
    ):
        sha = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    return CompanyPortalReceipt(
        company_id=company_id,
        url=url,
        evidence=f"page shows {shown[0]}",
        sha256=sha,
        observed_at=datetime.now(UTC),
    )


def company_receipts_path(output_dir: Path) -> Path:
    return output_dir / "cv" / RECEIPT_NAME


def load_company_receipts(output_dir: Path) -> dict[str, CompanyPortalReceipt]:
    """Read stored page evidence. Missing file means there is no evidence."""
    path = company_receipts_path(output_dir)
    if not path.is_file():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    items = raw.get("receipts", []) if isinstance(raw, dict) else []
    if not isinstance(items, list):
        return {}
    found: dict[str, CompanyPortalReceipt] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        evidence = str(item.get("evidence") or "").strip()
        if not url or not evidence:
            continue
        when_raw = item.get("observed_at")
        observed: datetime | None
        if isinstance(when_raw, datetime):
            observed = when_raw
        elif isinstance(when_raw, str) and when_raw.strip():
            observed = datetime.fromisoformat(when_raw)
        else:
            observed = None
        receipt = CompanyPortalReceipt(
            company_id=str(item.get("company_id") or ""),
            url=url,
            evidence=evidence,
            sha256=str(item.get("sha256") or ""),
            observed_at=observed,
        )
        found[canonical_key(url)] = receipt
    return found


def has_receipt_for(output_dir: Path, url: str) -> bool:
    """True when local page evidence exists for this career URL."""
    return canonical_key(url) in load_company_receipts(output_dir)


def write_company_receipt(output_dir: Path, receipt: CompanyPortalReceipt) -> Path:
    """Persist one page observation. Callers must not use this for a bare yes."""
    existing = load_company_receipts(output_dir)
    existing[canonical_key(receipt.url)] = receipt
    path = company_receipts_path(output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "receipts": [
            {
                "company_id": item.company_id,
                "url": item.url,
                "evidence": item.evidence,
                "sha256": item.sha256,
                "observed_at": (
                    item.observed_at.isoformat() if item.observed_at is not None else None
                ),
            }
            for item in existing.values()
        ]
    }
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return path


def _empty_result(intent: CompanyApplyIntent) -> CompanyApplyResult:
    return CompanyApplyResult(
        company_id=intent.company_id,
        mode=intent.mode,
        opened=False,
        filled=(),
        attached=False,
        receipt_path=None,
        submitted=False,
    )


def _note_for(action: PortalAction, company_name: str) -> str:
    if action is PortalAction.LOGIN:
        return (
            f"Account evidence exists for {company_name}. "
            "Open login only — you type the password. "
            "jobbot browser login --apply"
        )
    if action is PortalAction.SIGNUP_FILL:
        return (
            f"jobbot companies signup {company_name} --apply — fill known fields + CV (#44). "
            "You type the password, accept terms, and confirm create. "
            "Unanswered fields become learned gaps (issue HITL)."
        )
    if action is PortalAction.FILL:
        return (
            "Opens the career URL, fills fields profile.yaml already answers, "
            "and may attach the built CV. You submit. A yes is not a receipt."
        )
    return "skipped"


def _form_asks_resume(form: FormKnowledge) -> bool:
    if not form.readable:
        return False
    return any(
        field.kind is FieldKind.FILE or _is_resume_label(field.label)
        for field in form.fields
    )


def _fill_page(
    page: Any,
    form: FormKnowledge,
    candidate: Candidate,
    cv_path: Path | None,
) -> tuple[tuple[str, ...], bool]:
    if not form.readable:
        return (), False
    answers = {
        item.label.casefold(): item.value
        for item in signup_sheet(candidate, form=form)
        if item.value and not _forbidden_label(item.label)
    }
    filled: list[str] = []
    for field in form.fields:
        if field.kind is FieldKind.FILE or _blocked_field(field):
            continue
        if _is_resume_label(field.label):
            continue
        value = answers.get(field.label.casefold(), "")
        selector = _selector(field)
        if not value or selector is None:
            continue
        page.fill(selector, value)
        filled.append(field.label)
    return tuple(filled), _attach_cv(page, form, cv_path)


def _attach_cv(page: Any, form: FormKnowledge, cv_path: Path | None) -> bool:
    path = _attachable_pdf(cv_path)
    if path is None:
        return False
    files = [
        field
        for field in form.fields
        if field.kind is FieldKind.FILE and not _forbidden_label(field.label)
    ]
    if not files:
        return False
    selector = _selector(files[0])
    if selector is None:
        return False
    locator = page.locator(selector)
    target = locator.first if hasattr(locator, "first") else locator
    target.set_input_files(str(path))
    return True


def _attachable_pdf(path: Path | None) -> Path | None:
    if path is None or not path.is_file() or path.suffix.casefold() != ".pdf":
        return None
    if not path.read_bytes()[:5].startswith(b"%PDF"):
        return None
    return path


def _blocked_field(field: FormField) -> bool:
    if _forbidden_label(field.label) or _forbidden_label(field.name):
        return True
    return field.kind not in _FILLABLE and field.kind is not FieldKind.FILE


def _forbidden_label(label: str) -> bool:
    folded = label.casefold()
    return any(token in folded for token in _FORBIDDEN_TOKENS)


def _is_resume_label(label: str) -> bool:
    folded = label.casefold()
    return any(token in folded for token in _RESUME_TOKENS)


def _selector(field: FormField) -> str | None:
    name = field.name
    if not name or any(char in name for char in "\"'\\[]"):
        return None
    if field.kind is FieldKind.LONG_TEXT:
        return f'textarea[name="{name}"]'
    return f'[name="{name}"]'


def _visible_text(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup.find_all(["script", "style", "input", "textarea", "select", "option"]):
        tag.decompose()
    return " ".join(soup.get_text(" ", strip=True).split())
