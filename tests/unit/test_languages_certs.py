"""Languages and certifications are profile facts, not a skill group."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from jobbot.cv.renderer import CvStyle, render_cv_ats, render_cv_tex
from jobbot.exit_codes import SUCCESS
from jobbot.matching.analyzer import RuleBasedJobAnalyzer
from jobbot.models.candidate import Candidate
from jobbot.models.job import JobPosting
from jobbot.models.match import MatchStrength
from jobbot.portals.field_homologation import ProfileFact, answer_for_label, resolve_fact
from jobbot.profile.validator import validate_candidate
from tests.fixtures.profile import sample_profile_dict

_LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2", "native")


def _profile(**extra: object) -> Candidate:
    data: dict[str, object] = {
        "personal": {
            "name": "Ana Ejemplo",
            "headline": "Analista",
            "email": "ana.ejemplo@example.com",
        },
        "summary": "Trabajo en la unidad de un servicio, con terreno y con oficina.",
        "experience": [
            {
                "id": "regional",
                "company": "Servicio Regional Ficticio",
                "title": "Analista",
                "start_date": "2019-03",
                "end_date": "2024-01",
                "current": False,
                "achievements": [],
            }
        ],
        "languages": [
            {"name": "Español", "level": "native"},
            {"name": "Inglés", "level": "B2", "evidence": "EF SET 58/100 (2026)"},
        ],
        "certifications": [
            {
                "id": "cert-epi-campo",
                "name": "Epidemiología de campo, nivel inicial",
                "issuer": "Programa Ficticio de Formación",
                "date": "2023-05",
                "url": "https://example.org/cert/123",
                "expires": None,
            }
        ],
    }
    data.update(extra)
    return Candidate.model_validate(data)


def test_languages_and_certification_validate() -> None:
    result = validate_candidate(_profile())
    assert result.ok
    assert result.warnings == []


def test_unknown_level_lists_the_valid_ones() -> None:
    with pytest.raises(ValidationError) as exc:
        _profile(
            languages=[{"name": "Inglés", "level": "B5"}],
        )
    message = str(exc.value)
    for level in _LEVELS:
        assert level in message


def test_expired_certification_warns_and_stays_valid() -> None:
    certs = [
        {
            "id": "cert-epi-campo",
            "name": "Epidemiología de campo, nivel inicial",
            "issuer": "Programa Ficticio de Formación",
            "date": "2019-01",
            "expires": "2020-01",
        }
    ]
    result = validate_candidate(_profile(certifications=certs))
    assert result.ok
    assert any("2020-01" in warning.message for warning in result.warnings)


def test_duplicate_certification_ids_fail() -> None:
    cert = {
        "id": "cert-epi-campo",
        "name": "Epidemiología de campo, nivel inicial",
        "issuer": "Programa Ficticio de Formación",
        "date": "2023-05",
    }
    result = validate_candidate(_profile(certifications=[cert, dict(cert)]))
    assert not result.ok
    assert any("duplicate id" in issue.message for issue in result.issues)


def test_cv_shows_languages_and_certification(project_root: Path) -> None:
    candidate = _profile()
    templates = project_root / "templates"
    ats = render_cv_ats(candidate, templates)
    tex = render_cv_tex(candidate, templates, style=CvStyle.MODERNCV)
    assert "Inglés (B2)" in ats
    assert "Programa Ficticio de Formación" in ats
    assert "2023" in ats
    assert "Epidemiología de campo, nivel inicial" in ats
    assert "Idiomas" in tex
    assert "Certificaciones" in tex
    assert "Inglés" in tex
    assert "Programa Ficticio de Formación" in tex


def test_profile_without_these_blocks_renders_as_before(project_root: Path) -> None:
    candidate = Candidate.model_validate(sample_profile_dict())
    ats = render_cv_ats(candidate, project_root / "templates")
    tex = render_cv_tex(candidate, project_root / "templates", style=CvStyle.MODERNCV)
    assert "LANGUAGES" not in ats
    assert "IDIOMAS" not in ats
    assert "CERTIFICATIONS" not in ats
    assert r"\section{Idiomas}" not in tex
    assert r"\section{Certificaciones}" not in tex
    assert "Senior Data Scientist — Mercado Libre" in ats


def test_language_label_resolves_and_an_unknown_label_stays_empty() -> None:
    candidate = _profile()
    assert resolve_fact("Language") is ProfileFact.LANGUAGES
    value, source = answer_for_label(candidate, "Language")
    assert "Inglés (B2)" in value
    assert source == "languages"
    empty, why = answer_for_label(candidate, "Favorite color")
    assert empty == ""
    assert "you decide" in why


def test_a_bare_level_label_is_not_a_language_field() -> None:
    candidate = _profile()
    for label in ("Nivel", "Proficiency"):
        assert resolve_fact(label) is None
        value, why = answer_for_label(candidate, label)
        assert value == ""
        assert "you decide" in why


def test_posting_mention_adds_evidence_and_silence_does_not() -> None:
    candidate = _profile()
    mentioned = JobPosting(
        id="J0001",
        title="Un cargo",
        company="Casa Ficticia",
        description="Se pide inglés y epidemiología de campo, nivel inicial.",
    )
    silent = JobPosting(
        id="J0002",
        title="Un cargo",
        company="Casa Ficticia",
        description="Se pide disponibilidad de oficina en la región.",
    )
    analyzer = RuleBasedJobAnalyzer()
    hit = analyzer.analyze(candidate, mentioned)
    miss = analyzer.analyze(candidate, silent)
    labels = " ".join(item.label for item in hit.items)
    assert "Inglés" in labels or "ingles" in labels.casefold()
    assert "Epidemiología de campo, nivel inicial" in labels
    assert "Epidemiología" not in " ".join(item.label for item in miss.items)
    assert hit.score >= miss.score


def test_a_required_language_is_read_from_the_profile() -> None:
    stated = JobPosting(
        id="J0001",
        title="Un cargo",
        company="Casa Ficticia",
        description="Se pide inglés.",
        language_requirements=["english"],
    )
    analyzer = RuleBasedJobAnalyzer()
    match = analyzer.analyze(_profile(), stated)
    item = next(item for item in match.items if "english" in item.label)
    assert item.strength is MatchStrength.STRONG
    assert "Inglés (B2)" in item.detail
    assert not any("not modeled in profile.yaml" in i.detail for i in match.items)

    without = analyzer.analyze(_profile(languages=[]), stated)
    silent = next(item for item in without.items if "english" in item.label)
    assert silent.strength is MatchStrength.UNKNOWN


def test_profile_validate_warns_and_exits_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    data = tmp_path / "data"
    data.mkdir()
    (data / "profile.yaml").write_text(
        "\n".join(
            [
                "personal:",
                "  name: Ana Ejemplo",
                "  headline: Analista",
                "  email: ana.ejemplo@example.com",
                "certifications:",
                "  - id: cert-epi-campo",
                "    name: Epidemiología de campo, nivel inicial",
                "    issuer: Programa Ficticio de Formación",
                "    date: '2019-01'",
                "    expires: '2020-01'",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    from jobbot.cli import run_cli

    code = run_cli(["profile", "validate"], standalone_mode=False)
    err = capsys.readouterr().err
    assert code == SUCCESS
    assert "2020-01" in err
    assert "PROFILE INVALID" not in err
