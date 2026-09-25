"""Document-level CV↔JD fit — reduces dependence on parsed skill lists."""

from __future__ import annotations

from pathlib import Path

from jobbot.jobs.chat_first import parse_job_chat_first
from jobbot.jobs.parsing import parse_job_text
from jobbot.matching.analyzer import RuleBasedJobAnalyzer
from jobbot.matching.similarity import (
    bag_cosine,
    candidate_document,
    document_similarity,
    job_document,
)
from jobbot.models.candidate import Candidate
from jobbot.models.job import JobPosting
from jobbot.models.match import MatchStrength
from jobbot.profile.loader import load_profile
from tests.fixtures.profile import sample_profile_dict

_ALIGNED_JD = (
    "Title: Senior Data Scientist\n"
    "Company: Andes Analytics\n"
    "Location: Santiago, Chile\n"
    "\n"
    "We are hiring a Senior Data Scientist to lead causal inference, "
    "machine learning models, forecasting, and experimentation in retail "
    "and marketplace analytics. You will use Python, SQL, PyTorch, and "
    "scikit-learn to design measurable A/B tests, survival models, and "
    "customer analytics pipelines on GCP and AWS. MLOps and APIs matter.\n"
    "\n"
    "Requirements:\n"
    "- Python and SQL\n"
    "- Causal inference and machine learning\n"
    "- Experimentation / RCT experience\n"
)


def test_bag_cosine_aligns_ds_profile_with_ds_jd() -> None:
    candidate = Candidate.model_validate(sample_profile_dict())
    job = parse_job_text(_ALIGNED_JD, job_id="J0900")
    score = bag_cosine(candidate_document(candidate), job_document(job))
    assert score >= 0.35


def test_noisy_skills_do_not_own_the_score() -> None:
    """Garbage skill tokens (LinkedIn chrome) must not tank match when JD text fits."""
    candidate = Candidate.model_validate(sample_profile_dict())
    job = JobPosting(
        id="J0901",
        source="manual",
        title="Senior Data Scientist",
        company="Andes Analytics",
        description=_ALIGNED_JD,
        raw_description=_ALIGNED_JD,
        skills=["Publicado", "haypega", "LinkedIn", "CORFO", "mailto"],
        requirements=[],
    )
    blended = RuleBasedJobAnalyzer(document_fit=True).analyze(candidate, job)
    lexical_only = RuleBasedJobAnalyzer(document_fit=False).analyze(candidate, job)
    assert blended.document_score is not None
    assert blended.document_score >= 35
    assert blended.score > lexical_only.score
    assert blended.score >= 30
    assert blended.fit_mode == "bag"
    assert any(i.label.startswith("document:") for i in blended.items)


def test_mocked_embedder_sets_fit_mode_embedding() -> None:
    candidate = Candidate.model_validate(sample_profile_dict())
    job = parse_job_text(_ALIGNED_JD, job_id="J0902")

    class _Fake:
        def embed(self, text: str) -> list[float]:
            # Same vector → perfect cosine; proves the embedding path is wired.
            return [1.0, 0.0, 0.0]

    match = RuleBasedJobAnalyzer(document_fit=True, embedder=_Fake()).analyze(candidate, job)
    assert match.fit_mode == "embedding"
    assert match.document_score == 100.0
    assert match.score > 50


def test_ecos_document_fit_beats_noisy_lexical() -> None:
    """ECOS LinkedIn paste: structured skills stay noisy; document fit still helps."""
    text = Path("tests/fixtures/jobs/ecos_ai_multiagent_linkedin.txt").read_text(encoding="utf-8")
    job = parse_job_chat_first(text, job_id="J0903", use_llm=False).job
    candidate = load_profile(Path("data/profile.example.yaml"))
    blended = RuleBasedJobAnalyzer(document_fit=True).analyze(candidate, job)
    lexical_only = RuleBasedJobAnalyzer(document_fit=False).analyze(candidate, job)
    assert blended.document_score is not None
    assert blended.document_score > lexical_only.score
    assert blended.score >= lexical_only.score
    assert blended.fit_mode == "bag"
    doc_item = next(i for i in blended.items if i.label.startswith("document:"))
    assert doc_item.strength in {
        MatchStrength.PARTIAL,
        MatchStrength.STRONG,
        MatchStrength.MISSING,
    }


def test_document_similarity_helper_returns_mode() -> None:
    candidate = Candidate.model_validate(sample_profile_dict())
    job = parse_job_text(_ALIGNED_JD, job_id="J0904")
    score, mode = document_similarity(candidate, job)
    assert mode == "bag"
    assert 0 <= score <= 100
