"""Base vs job-adapted CV distance to the JD."""

from __future__ import annotations

from pathlib import Path

from jobbot.cv.fit import compare_base_vs_adapted_cv
from jobbot.jobs.parsing import parse_job_text
from jobbot.matching.scoring import format_adaptation_fit_report
from jobbot.matching.similarity import AdaptationFit, compare_adaptation_fit
from jobbot.models.candidate import Candidate
from jobbot.models.job import JobPosting
from tests.fixtures.profile import sample_profile_dict

_ALIGNED_JD = (
    "Title: Senior Data Scientist\n"
    "Company: Andes Analytics\n"
    "Location: Santiago, Chile\n"
    "\n"
    "Buscamos Senior Data Scientist con causal inference, machine learning, "
    "forecasting y experimentación en retail. Python, SQL, PyTorch, "
    "scikit-learn, A/B tests, survival models, customer analytics, GCP, AWS, "
    "MLOps y APIs.\n"
    "\n"
    "Requirements:\n"
    "- Python and SQL\n"
    "- Causal inference and machine learning\n"
    "- Experimentación / RCT\n"
)

_FRONTEND_JD = (
    "Title: Junior Frontend Engineer\n"
    "Company: Pixel Labs\n"
    "Location: Remote\n"
    "\n"
    "React, TypeScript, CSS, accessibility, design systems, Storybook, "
    "Jest and Playwright for UI testing. No data science stack.\n"
)


def test_compare_adaptation_fit_adapted_beats_base_on_aligned_jd(
    project_root: Path,
) -> None:
    candidate = Candidate.model_validate(sample_profile_dict())
    job = parse_job_text(_ALIGNED_JD, job_id="J0910")
    templates = project_root / "templates"
    fit = compare_base_vs_adapted_cv(candidate, job, templates)
    assert fit.mode == "bag"
    assert fit.adapted_beats_base
    assert fit.adapted_score >= fit.base_score
    assert fit.delta >= 0


def test_mocked_bert_path_marks_mode_bert(project_root: Path) -> None:
    candidate = Candidate.model_validate(sample_profile_dict())
    job = parse_job_text(_ALIGNED_JD, job_id="J0911")
    templates = project_root / "templates"

    class _CloserToAdapted:
        """Fake embedder: adapted text → vector near JD; base → orthogonal."""

        def embed(self, text: str) -> list[float]:
            folded = text.casefold()
            if "andes analytics" in folded or "buscamos senior" in folded:
                return [1.0, 0.0]
            if "causal" in folded or "pytorch" in folded or "experiment" in folded:
                return [0.95, 0.05]
            return [0.0, 1.0]

    fit = compare_base_vs_adapted_cv(candidate, job, templates, embedder=_CloserToAdapted())
    assert fit.mode == "bert"
    assert fit.adapted_beats_base


def test_raw_compare_adaptation_fit_unit() -> None:
    job = JobPosting(
        id="J0912",
        title="Data Scientist",
        company="X",
        description="python sql machine learning causal inference pytorch",
    )
    base = "nurse hospital patient care unidad critico"
    adapted = "python sql machine learning causal inference pytorch retail"
    fit = compare_adaptation_fit(base, adapted, job)
    assert isinstance(fit, AdaptationFit)
    assert fit.adapted_beats_base
    assert fit.adapted_score > fit.base_score
    report = format_adaptation_fit_report(fit)
    assert "adapted" in report.casefold()
    assert "base" in report.casefold()


def test_default_bert_model_is_local_minilm() -> None:
    from jobbot.matching.similarity import DEFAULT_BERT_MODEL

    assert "minilm" in DEFAULT_BERT_MODEL.casefold()
    assert "sentence-transformers" in DEFAULT_BERT_MODEL
