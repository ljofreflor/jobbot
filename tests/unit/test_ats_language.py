"""ATS text follows the profile's language. English stays the snapshot it already was."""

from __future__ import annotations

from pathlib import Path

import pytest

from jobbot.config import CvConfig, JobbotConfig, PathsConfig
from jobbot.cv.build import build_adapted_cv
from jobbot.cv.renderer import render_cv_ats, resolve_ats_language
from jobbot.exit_codes import SUCCESS
from jobbot.matching.analyzer import RuleBasedJobAnalyzer
from jobbot.models.candidate import Candidate
from jobbot.models.job import JobPosting
from tests.fixtures.profile import sample_profile_dict

_ENGLISH_ATS = """\
Ana Ejemplo
Senior Data Scientist
Santiago, Chile
Email: ana@example.com
LinkedIn: https://www.linkedin.com/in/ana
GitHub: https://github.com/ana

SUMMARY
Data scientist focused on causal inference.

SPECIALTIES
Machine Learning, Causal Inference

EXPERIENCE
Senior Data Scientist — Mercado Libre
2022-04 – 2025-05 | Remote
Customer analytics & credit risk.
- Share of Wallet for 6M sellers. (6M sellers; USD 460M)

EDUCATION
Magíster en Estadística — Universidad de Chile
2017-03 – 2019-12

SKILLS
Programming: Python, SQL
Machine Learning: XGBoost
Cloud: GCP
Statistics: Causal Inference
Engineering: MLOps

PUBLICATIONS
- Marketplace interference. Working paper (2021) [preprint]
"""


def _spanish() -> Candidate:
    return Candidate.model_validate(
        {
            "personal": {
                "name": "Ana Ejemplo",
                "headline": "Analista",
                "city": "Santiago",
                "country": "Chile",
                "email": "ana.ejemplo@example.com",
                "phone": "555 0100",
            },
            "summary": (
                "Trabajo en la unidad de un servicio regional, con terreno y con oficina, "
                "para la región."
            ),
            "experience": [
                {
                    "id": "regional",
                    "company": "Servicio Regional Ficticio",
                    "title": "Analista",
                    "start_date": "2019-03",
                    "current": True,
                    "achievements": [
                        {"id": "informe", "text": "Cerré el informe anual de la unidad."}
                    ],
                }
            ],
            "education": [
                {
                    "id": "curso",
                    "institution": "Instituto Ficticio",
                    "degree": "Curso",
                    "start_date": "2015-01",
                }
            ],
            "skills": {"gestion_y_relacionamiento": ["Una cosa"]},
        }
    )


def _ambiguous() -> Candidate:
    return Candidate.model_validate(
        {
            "personal": {"name": "Ana Ejemplo", "headline": "Analista"},
            "summary": "Cargo regional.",
            "experience": [
                {
                    "id": "uno",
                    "company": "Casa Ficticia",
                    "title": "Analista",
                    "start_date": "2020-01",
                    "end_date": "2021-01",
                    "current": False,
                    "achievements": [{"id": "hecho", "text": "Informe anual."}],
                }
            ],
        }
    )


def test_spanish_profile_uses_spanish_headings_and_dates(project_root: Path) -> None:
    ats = render_cv_ats(_spanish(), project_root / "templates")
    for label in ("RESUMEN", "EXPERIENCIA", "FORMACIÓN", "Teléfono:", "Mar 2019 – Presente"):
        assert label in ats
    assert "2015 – en curso" in ats
    assert "Gestion y relacionamiento" in ats
    assert "SUMMARY" not in ats
    assert "– Present" not in ats.replace("– Presente", "")
    assert "2019-03" not in ats
    assert "2015-01" not in ats


def test_lang_en_forces_english_on_the_same_profile(project_root: Path) -> None:
    ats = render_cv_ats(_spanish(), project_root / "templates", language="en")
    assert "SUMMARY" in ats
    assert "EXPERIENCE" in ats
    assert "2019-03 – Present" in ats
    assert "RESUMEN" not in ats
    assert "Teléfono:" not in ats


def test_english_example_profile_keeps_the_current_snapshot(project_root: Path) -> None:
    ats = render_cv_ats(Candidate.model_validate(sample_profile_dict()), project_root / "templates")
    assert ats == _ENGLISH_ATS


def test_ambiguous_text_falls_back_to_english(project_root: Path) -> None:
    candidate = _ambiguous()
    assert resolve_ats_language(candidate) == "en"
    ats = render_cv_ats(candidate, project_root / "templates")
    assert "SUMMARY" in ats
    assert "RESUMEN" not in ats


def test_explicit_lang_beats_configured_and_detection() -> None:
    spanish = _spanish()
    assert resolve_ats_language(spanish, explicit="en", configured="es") == "en"
    assert resolve_ats_language(spanish, configured="en") == "en"
    assert resolve_ats_language(_ambiguous(), configured="es") == "es"
    assert resolve_ats_language(spanish) == "es"


def test_cv_build_lang_en_writes_english_headings(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = tmp_path / "data"
    data.mkdir()
    profile = data / "profile.yaml"
    profile.write_text(
        "\n".join(
            [
                "personal:",
                "  name: Ana Ejemplo",
                "  headline: Analista",
                "  email: ana.ejemplo@example.com",
                "summary: Trabajo en la unidad de un servicio, con terreno y con oficina.",
                "experience:",
                "  - id: regional",
                "    company: Servicio Regional Ficticio",
                "    title: Analista",
                "    start_date: '2019-03'",
                "    current: true",
                "    achievements:",
                "      - id: informe",
                "        text: Cerré el informe anual de la unidad.",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / ".jobbot.toml").write_text(
        f'[paths]\ntemplates = "{project_root / "templates"}"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    from jobbot.cli import run_cli

    code = run_cli(["cv", "build", "--target", "ats", "--lang", "en"], standalone_mode=False)
    assert code == SUCCESS
    text = (tmp_path / "output" / "base" / "cv_ats.txt").read_text(encoding="utf-8")
    assert "SUMMARY" in text
    assert "RESUMEN" not in text
    assert "2019-03 – Present" in text


def test_configured_language_reaches_the_job_adapted_text(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The standing `[cv] language` also governs the CV pasted into a form."""

    def fake(tex_path: Path, work_dir: Path) -> Path:
        pdf = work_dir / "cv.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        return pdf

    monkeypatch.setattr("jobbot.cv.build._compile_xelatex", fake)
    config = JobbotConfig(
        paths=PathsConfig(templates=project_root / "templates"),
        root=tmp_path,
        cv=CvConfig(language="en"),
    )
    candidate = _spanish()
    job = JobPosting.model_validate(
        {
            "id": "J0900",
            "title": "Analista",
            "company": "Casa Ficticia",
            "url": "https://jobs.example.com/postings/42",
            "description": "Buscamos un analista para la unidad regional.",
        }
    )
    build_adapted_cv(config, candidate, job, RuleBasedJobAnalyzer().analyze(candidate, job))

    ats = (tmp_path / "output" / "jobs" / "J0900" / "cv_ats.txt").read_text(encoding="utf-8")
    assert "EXPERIENCE" in ats
    assert "EXPERIENCIA" not in ats
