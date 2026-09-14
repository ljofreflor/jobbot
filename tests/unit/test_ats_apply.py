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
    fields = prefill_field_map(cand)
    assert fields["email"] == "leo@example.com"
    assert "full_name" in fields


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
