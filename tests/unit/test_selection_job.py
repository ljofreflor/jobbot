"""Job-specific achievement selection tests."""

from pathlib import Path

from jobbot.cv.selection import select_for_job
from jobbot.jobs.parsing import parse_job_text
from jobbot.models.candidate import Candidate
from tests.fixtures.profile import sample_profile_dict


def test_select_for_job_prefers_overlapping_achievements(project_root: Path) -> None:
    candidate = Candidate.model_validate(sample_profile_dict())
    job = parse_job_text(
        (project_root / "tests/fixtures/jobs/senior_ds_retail.txt").read_text(encoding="utf-8"),
        job_id="J0001",
    )
    selection = select_for_job(candidate, job)
    assert selection.job_id == "J0001"
    ids = {a.id for a in selection.selected_achievements}
    assert "meli-share-of-wallet" in ids
    selected = next(a for a in selection.selected_achievements if a.id == "meli-share-of-wallet")
    assert selected.reason
