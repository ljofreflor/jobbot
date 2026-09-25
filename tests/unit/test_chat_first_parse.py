"""Chat-first / preprocess JD parsing (LinkedIn paste, email posts)."""

from __future__ import annotations

from pathlib import Path

from jobbot.jobs.chat_first import parse_job_chat_first
from jobbot.jobs.parsing import parse_job_text
from jobbot.jobs.preprocess import preprocess_job_text
from jobbot.matching.analyzer import RuleBasedJobAnalyzer

ECOS = Path("tests/fixtures/jobs/ecos_ai_multiagent_linkedin.txt")


def test_preprocess_strips_linkedin_chrome() -> None:
    text = ECOS.read_text(encoding="utf-8")
    cleaned = preprocess_job_text(text)
    assert "Publicado en LinkedIn" not in cleaned
    assert "fernanda.fuentes@" not in cleaned
    assert "#haypega" not in cleaned
    assert "AI & Multi-Agent Lead" in cleaned
    assert "LLMs" in cleaned


def test_ecos_title_and_company_without_llm() -> None:
    text = ECOS.read_text(encoding="utf-8")
    result = parse_job_chat_first(text, job_id="J0800", use_llm=False)
    assert result.mode == "deterministic"
    assert result.job.title == "AI & Multi-Agent Lead"
    assert result.job.company == "ECOS Chile"
    assert result.job.seniority == "lead"
    skills_fold = " ".join(s.casefold() for s in result.job.skills)
    assert "llm" in skills_fold or "llms" in skills_fold
    assert "publicado" not in skills_fold
    assert "principales desafíos" not in skills_fold
    assert "haypega" not in skills_fold


def test_ecos_match_not_dominated_by_chrome_noise() -> None:
    from jobbot.models.match import MatchStrength

    text = ECOS.read_text(encoding="utf-8")
    job = parse_job_chat_first(text, job_id="J0801", use_llm=False).job
    from jobbot.profile.loader import load_profile

    candidate = load_profile(Path("data/profile.example.yaml"))
    match = RuleBasedJobAnalyzer().analyze(candidate, job)
    missing_labels = [i.label.casefold() for i in match.by_strength(MatchStrength.MISSING)]
    for chrome in ("publicado", "haypega", "principales desafíos", "fernanda"):
        assert chrome not in missing_labels
    skills_fold = " ".join(s.casefold() for s in job.skills)
    assert "llm" in skills_fold or "llms" in skills_fold


def test_chat_first_llm_mocked_grounds_skills() -> None:
    text = ECOS.read_text(encoding="utf-8")

    class _Fake:
        def invoke(self, _prompt: object) -> object:
            return (
                '{"title":"AI & Multi-Agent Lead","company":"ECOS Chile",'
                '"location":null,"seniority":"lead",'
                '"skills":["LLMs","arquitecturas multiagente","IA","InventedSkillXYZ"],'
                '"requirements":["Al menos 5 años de experiencia en roles similares."]}'
            )

    result = parse_job_chat_first(
        text, job_id="J0802", use_llm=True, chat_model=_Fake()
    )
    assert result.mode == "llm"
    assert result.job.company == "ECOS Chile"
    assert "LLMs" in result.job.skills or "IA" in result.job.skills
    assert "InventedSkillXYZ" not in result.job.skills


def test_title_company_em_dash_still_works_on_raw_parse() -> None:
    job = parse_job_text(
        "Staff Platform Engineer — Acme Robotics\nRequirements:\n- Python\n",
        job_id="J0803",
    )
    assert job.title == "Staff Platform Engineer"
    assert job.company == "Acme Robotics"
    assert "Python" in job.skills
