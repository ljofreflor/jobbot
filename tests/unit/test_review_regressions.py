"""Integration boundaries found by the repository review (offline)."""

import pytest

from jobbot.config import JobbotConfig
from jobbot.models.candidate import Candidate
from tests.fixtures.profile import sample_profile_dict


def test_sdk_resolves_paths(tmp_path, monkeypatch):
    from jobbot.sdk.cv_api import CvApi

    captured = {}

    def build(**kwargs):
        captured.update(kwargs)
        return [tmp_path / "cv.pdf"]

    monkeypatch.setattr("jobbot.sdk.cv_api.build_cv", build)
    CvApi(JobbotConfig(root=tmp_path), Candidate.model_validate(sample_profile_dict())).build()
    assert captured["output_dir"] == tmp_path / "output"
    assert captured["templates_dir"] == tmp_path / "templates"


@pytest.mark.parametrize("mode", ["file", "root"])
def test_sdk_loads_local_config(tmp_path, mode):
    from jobbot.sdk.client import JobBotClient

    path = tmp_path / ".jobbot.toml"
    path.write_text('[paths]\nprofile="custom/profile.yaml"\n')
    config = JobBotClient.__new__(JobBotClient)._load_config(
        path if mode == "file" else None, tmp_path if mode == "root" else None
    )
    assert config.profile_path == tmp_path / "custom/profile.yaml"


def test_sdk_default_style(tmp_path, monkeypatch):
    from jobbot.db.engine import make_engine, make_session_factory
    from jobbot.jobs.repository import JobRepository
    from jobbot.models.job import JobPosting
    from jobbot.sdk.cv_api import CvApi

    config = JobbotConfig(root=tmp_path)
    engine = make_engine(config.database_path)
    with make_session_factory(engine)() as session:
        job = JobRepository(session).upsert_external(
            JobPosting(id="J0001", title="Role", company="Example")
        )
        session.commit()
    engine.dispose()
    monkeypatch.setattr("jobbot.sdk.cv_api.build_cv", lambda **kwargs: [tmp_path / "cv.pdf"])
    api = CvApi(config, Candidate.model_validate(sample_profile_dict()))
    assert api.build_for_job_id(job.id) == tmp_path / "cv.pdf"


def test_pdf_missing_retries(tmp_path):
    from jobbot.cv.build import should_rebuild_job_cv

    profile = tmp_path / "profile.yaml"
    profile.touch()
    (tmp_path / "cv_ats.txt").touch()
    assert should_rebuild_job_cv(tmp_path, profile)


def test_language_symbols_are_distinct():
    from jobbot.jobs.normalization import normalize_skill

    assert len({normalize_skill(s) for s in ["C", "C++", "C#"]}) == 3


@pytest.mark.parametrize(
    "path", [".local/profile.yaml", ".local/browser-data/Preferences", ".local/output/cv_ats.txt"]
)
def test_private_local_tree_is_blocked(path):
    from jobbot.ops.pii_guard import is_blocked_path

    assert is_blocked_path(path)


def test_resume_photo_is_not_cv():
    from jobbot.adapters.ats.apply_fill import _cv_file_field
    from jobbot.portals.form_learn import FieldKind, FormField

    photo = FormField(name="pic", label="Resume photo", kind=FieldKind.FILE, accepts=["image/png"])
    cv = FormField(name="cv", label="CV", kind=FieldKind.FILE, accepts=["application/pdf"])
    assert _cv_file_field([photo, cv]) == cv
    assert _cv_file_field([cv, cv.model_copy(update={"name": "cv2"})]) is None


def test_no_identity_is_not_ready():
    from jobbot.browser.sessions import (
        AccountExpectation,
        SessionStatus,
        _signed_in_verdict,
        site_spec,
    )

    status, _ = _signed_in_verdict(
        site_spec("gmail"),
        "https://mail.google.com/mail/u/0/",
        "gmail",
        account=AccountExpectation(email="a@example.com"),
        page_text=None,
    )
    assert status != SessionStatus.READY


def test_preparation_preserves_interview(tmp_path):
    from jobbot.applications.manager import ApplicationRepository
    from jobbot.db.engine import make_engine, make_session_factory
    from jobbot.models.application import ApplicationStatus

    engine = make_engine(tmp_path / "jobs.sqlite")
    with make_session_factory(engine)() as session:
        repo = ApplicationRepository(session)
        repo.upsert_for_job("J0001", status=ApplicationStatus.INTERVIEW)
        result = repo.upsert_for_job(
            "J0001",
            status=ApplicationStatus.PREPARED,
            package_dir="new-package",
            preserve_progress=True,
        )
        assert result.status == ApplicationStatus.INTERVIEW
        assert result.package_dir == "new-package"
    engine.dispose()


def test_ats_apply_builds_before_attaching(tmp_path, project_root, monkeypatch):
    from jobbot.adapters.ats.apply_fill import ApplyFillResult
    from jobbot.cli import run_cli
    from tests.unit.test_application_apply_cdp import CDP, _workspace

    stored, cv = _workspace(tmp_path, project_root, monkeypatch)
    built = []

    def build(config, candidate, job):
        built.append(job.id)
        source = cv.parent.parent / "cv.pdf"
        source.write_bytes(b"%PDF CURRENT")

    def fill(*args, **kwargs):
        kwargs["cv_path"] = kwargs["prepare_cv"]()
        assert built == [stored.id]
        assert kwargs["cv_path"].read_bytes() == b"%PDF CURRENT"
        return ApplyFillResult(url="https://example.com", readable=True)

    monkeypatch.setattr("jobbot.cli._build_job_cv", build)
    monkeypatch.setattr("jobbot.adapters.ats.apply_fill.open_and_fill_over_cdp", fill)
    assert (
        run_cli(
            ["application", "apply", stored.id, "--apply", "--yes", "--cdp", CDP],
            standalone_mode=False,
        )
        == 0
    )


@pytest.mark.parametrize(
    "label,allowed",
    [
        ("Google Account: Candidate (a@example.com)", True),
        ("Google Account: Other (b@example.com)", False),
        ("Google Account", False),
    ],
)
def test_gmail_identity_before_compose(label, allowed):
    from jobbot.adapters.gmail.compose import GmailIdentityError, _verify_gmail_account

    class Control:
        def wait_for(self, **kwargs):
            pass

        def get_attribute(self, name):
            return label

    class Page:
        url = "https://mail.google.com/mail/u/0/#inbox"

        def goto(self, url, **kwargs):
            assert "compose" not in url

        def locator(self, selector):
            assert "SignOutOptions" in selector
            return Control()

    if allowed:
        _verify_gmail_account(Page(), "a@example.com")
    else:
        with pytest.raises(GmailIdentityError):
            _verify_gmail_account(Page(), "a@example.com")


@pytest.mark.parametrize("attach", [True, False])
def test_gmail_wrong_account_never_creates_draft(tmp_path, monkeypatch, attach):
    from contextlib import contextmanager
    from types import SimpleNamespace

    from jobbot.adapters.gmail.compose import GmailComposeAdapter, GmailIdentityError

    candidate = Candidate.model_validate(sample_profile_dict())
    monkeypatch.setattr("jobbot.profile.loader.load_profile", lambda _: candidate)
    adapter = GmailComposeAdapter(JobbotConfig(root=tmp_path))

    @contextmanager
    def session():
        yield SimpleNamespace(page=object())

    monkeypatch.setattr(adapter, "_session", session)
    adapter.cdp_url = None

    def reject(*args):
        raise GmailIdentityError("wrong account")

    monkeypatch.setattr("jobbot.adapters.gmail.compose._verify_gmail_account", reject)

    def forbid(*args):
        pytest.fail("created a draft before verifying the account")

    monkeypatch.setattr(adapter, "_prepare_verified", forbid)
    with pytest.raises(GmailIdentityError):
        adapter.open_draft_for_review(SimpleNamespace(job_id="J0001"), attach_cv=attach)


def test_sdk_cannot_bypass_owner_check(tmp_path):
    from jobbot.config import load_config
    from jobbot.sdk.client import JobBotClient
    from jobbot.workspace import WorkspaceOwnerError

    (tmp_path / ".jobbot.toml").write_text('[paths]\nprofile="data/profile.yaml"\n')
    profile = tmp_path / "data/profile.yaml"
    profile.parent.mkdir()
    profile.write_text("personal:\n  name: Candidate One\n")
    load_config(root=tmp_path)
    profile.write_text("personal:\n  name: Candidate Two\n")
    with pytest.raises(WorkspaceOwnerError):
        JobBotClient.__new__(JobBotClient)._load_config(None, tmp_path)
