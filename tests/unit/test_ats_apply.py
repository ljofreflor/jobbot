"""ATS apply plan tests."""

from jobbot.adapters.ats.apply import build_apply_plan, prefill_field_map
from jobbot.adapters.base import ApplyMethod
from jobbot.models.candidate import Candidate, PersonalInfo
from jobbot.models.job import JobPosting


def test_build_apply_plan_from_ats_url() -> None:
    cand = Candidate(
        personal=PersonalInfo(
            name="Leonardo Jofré",
            headline="DS",
            email="leo@example.com",
            linkedin="https://www.linkedin.com/in/leonardojofre",
        )
    )
    job = JobPosting(
        id="J1",
        title="DS",
        company="Acme",
        ats_url="https://boards.greenhouse.io/acme/jobs/1",
        ats_kind="greenhouse",
    )
    plan = build_apply_plan(cand, job)
    assert plan.method == ApplyMethod.EXTERNAL_ATS
    assert plan.ats_kind.value == "greenhouse"
    assert "prefill" in plan.message.casefold()
    fields = prefill_field_map(cand)
    assert fields["email"] == "leo@example.com"
    assert fields["first_name"] == "Leonardo"
    assert fields["last_name"] == "Jofré"
    assert "full_name" in fields


def test_unknown_ats_plan_does_not_claim_prefill() -> None:
    cand = Candidate(personal=PersonalInfo(name="Ana", headline="Editor"))
    job = JobPosting(
        id="J1",
        title="Editor",
        company="Northwind",
        ats_url="https://careers.example-corp.test/job/1",
        ats_kind="unknown",
    )
    plan = build_apply_plan(cand, job)
    assert plan.method == ApplyMethod.EXTERNAL_ATS
    assert "prefill" not in plan.message.casefold()
    assert "cheat sheet" in plan.message.casefold()


def test_four_part_name_keeps_both_surnames() -> None:
    """Regression: the first space used to swallow the second given name."""
    from jobbot.adapters.ats.apply import prefill_sheet_fields, split_personal_name

    given, surnames = split_personal_name("Ada María López Soto")
    assert given == "Ada María"
    assert surnames == "López Soto"
    cand = Candidate(
        personal=PersonalInfo(
            name="Ada María López Soto",
            headline="Editor",
            email="ada@example.com",
            phone="+56 9 1234 5678",
        )
    )
    fields = prefill_field_map(cand)
    assert fields["first_name"] == "Ada María"
    assert fields["last_name"] == "López Soto"
    sheet = prefill_sheet_fields(cand)
    assert "email" not in sheet
    assert "phone" not in sheet
    assert "ada@example.com" not in sheet.values()
    assert sheet["last_name"] == "López Soto"


def test_lever_adapter_detects() -> None:
    from jobbot.adapters.ats.lever import LeverAdapter

    job = JobPosting(
        id="J1",
        title="DS",
        company="Acme",
        ats_url="https://jobs.lever.co/acme/abc",
    )
    adapter = LeverAdapter()
    assert adapter.detect_method(job) == ApplyMethod.EXTERNAL_ATS


def test_getonboard_adapter_prefill_includes_spanish_hint() -> None:
    from jobbot.adapters.ats.getonboard import GetOnBoardAdapter

    cand = Candidate(personal=PersonalInfo(name="Ana", headline="DS"))
    job = JobPosting(
        id="J1",
        title="DS",
        company="Co",
        ats_url="https://www.getonbrd.com/jobs/x",
    )
    result = GetOnBoardAdapter().prefill(cand, job, package=_DummyPackage())
    assert any("español" in item.casefold() for item in result.needs_review)


def test_greenhouse_adapter_detects() -> None:
    from jobbot.adapters.ats.greenhouse import GreenhouseAdapter

    cand = Candidate(personal=PersonalInfo(name="Ana", headline="DS"))
    job = JobPosting(
        id="J1",
        title="DS",
        company="Acme",
        ats_url="https://boards.greenhouse.io/acme/jobs/1",
    )
    adapter = GreenhouseAdapter()
    assert adapter.detect_method(job) == ApplyMethod.EXTERNAL_ATS
    result = adapter.prefill(cand, job, package=_DummyPackage())
    assert "full_name" in result.filled or "email" in result.filled or result.filled


class _DummyPackage:
    @property
    def directory(self):  # noqa: ANN201
        from pathlib import Path

        return Path(".")

    @property
    def cv_pdf(self):  # noqa: ANN201
        return None
