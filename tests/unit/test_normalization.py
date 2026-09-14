"""Unit tests for skill normalization and job parsing."""

from __future__ import annotations

from jobbot.jobs.normalization import normalize_skill
from jobbot.jobs.parsing import parse_job_text


def test_normalize_postgres_aliases() -> None:
    assert normalize_skill("PostgreSQL") == "postgresql"
    assert normalize_skill("postgres") == "postgresql"


def test_normalize_ml_aliases() -> None:
    assert normalize_skill("ML") == "machine_learning"
    assert normalize_skill("machine-learning") == "machine_learning"


def test_sql_alias_not_matched_inside_typescript() -> None:
    """Regression: 'sql' must not match inside 'typescript'."""
    assert normalize_skill("TypeScript") != "sql"
    assert normalize_skill("React and TypeScript") != "sql"


def test_short_skill_r_not_matched_inside_react() -> None:
    """Regression: bare 'R' must not match inside 'React'."""
    text = """Title: Junior Frontend Engineer
Company: Pixel Labs
Requirements:
- React and TypeScript
"""
    job = parse_job_text(text, job_id="J0099")
    assert "R" not in job.skills


def test_parse_job_text_extracts_core_fields() -> None:
    text = """Title: Senior Data Scientist
Company: Sodimac
Location: Santiago
Requirements:
- Python
- Causal Inference
"""
    job = parse_job_text(text, job_id="J0001")
    assert job.title == "Senior Data Scientist"
    assert job.company == "Sodimac"
    assert job.location == "Santiago"
    assert job.seniority == "senior"
    assert any(s == "Python" for s in job.skills)
    assert job.requirements
