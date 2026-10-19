"""A degree states whether it is finished, underway, a candidacy, or abandoned."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from jobbot.cv.renderer import CvStyle, es_year_range, render_cv_ats, render_cv_tex
from jobbot.exit_codes import SUCCESS
from jobbot.models.candidate import Candidate
from jobbot.profile.loader import ProfileLoadError, load_profile
from tests.fixtures.profile import sample_profile_dict

DEGREE = "Doctorado en Ciencias Ficticias"
INSTITUTION = "Universidad Ficticia"


def _candidate(**edu: object) -> Candidate:
    data = sample_profile_dict()
    data["education"] = [
        {
            "id": "edu-doc",
            "institution": INSTITUTION,
            "degree": DEGREE,
            "start_date": "2021-03",
            **edu,
        }
    ]
    return Candidate.model_validate(data)


def _workspace(tmp_path: Path, project_root: Path, data: dict[str, object]) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "profile.yaml").write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (tmp_path / ".jobbot.toml").write_text(
        f'[paths]\ntemplates = "{project_root / "templates"}"\n',
        encoding="utf-8",
    )


def test_an_entry_without_status_keeps_finished_dates_and_names_in_progress(
    project_root: Path,
) -> None:
    finished = _candidate(end_date="2024-12")
    templates = project_root / "templates"
    modern = render_cv_tex(finished, templates, style=CvStyle.MODERNCV)
    assert es_year_range("2021-03", "2024-12") in modern
    assert "en curso" not in modern

    open_degree = _candidate()
    modern = render_cv_tex(open_degree, templates, style=CvStyle.MODERNCV)
    plain = render_cv_tex(open_degree, templates, style=CvStyle.PLAIN)
    ats = render_cv_ats(open_degree, templates)
    assert "2021 – en curso" in modern
    assert "Presente" not in modern.split("Formación Académica", 1)[1]
    assert "in progress" in plain
    assert "in progress" in ats


def test_spanish_ats_education_keeps_the_status_wording(project_root: Path) -> None:
    templates = project_root / "templates"
    underway = render_cv_ats(_candidate(expected_end="2027-06"), templates, language="es")
    assert "2021 – en curso (egreso esperado 2027)" in underway
    assert "Presente" not in underway.split("FORMACIÓN", 1)[1]

    done = render_cv_ats(_candidate(status="completed"), templates, language="es")
    assert "Presente" not in done.split("FORMACIÓN", 1)[1]


def test_candidate_degree_is_marked_in_spanish_and_english(project_root: Path) -> None:
    candidate = _candidate(status="candidate", expected_end="2027-06")
    templates = project_root / "templates"
    tex = render_cv_tex(candidate, templates, style=CvStyle.MODERNCV)
    ats = render_cv_ats(candidate, templates)
    assert f"{DEGREE} (c)" in tex
    assert "Candidate" in ats


def test_completed_without_end_does_not_say_present_and_warns(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    data = sample_profile_dict()
    data["education"] = [
        {
            "id": "edu-done",
            "institution": INSTITUTION,
            "degree": "Diplomado en Ciencias Ficticias",
            "start_date": "2018-03",
            "status": "completed",
        }
    ]
    candidate = Candidate.model_validate(data)
    tex = render_cv_tex(candidate, project_root / "templates", style=CvStyle.MODERNCV)
    section = tex.split("Formación Académica", 1)[1]
    assert "Presente" not in section

    _workspace(tmp_path, project_root, data)
    monkeypatch.chdir(tmp_path)
    from jobbot.cli import run_cli

    code = run_cli(["profile", "validate"], standalone_mode=False)
    assert code == SUCCESS
    assert "completed degree has no end_date" in capsys.readouterr().err


def test_abandoned_stays_off_the_cv_and_on_profile_show(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    data = sample_profile_dict()
    data["education"] = [
        {
            "id": "edu-left",
            "institution": INSTITUTION,
            "degree": "Diplomado abandonado",
            "start_date": "2015-03",
            "status": "abandoned",
        }
    ]
    candidate = Candidate.model_validate(data)
    tex = render_cv_tex(candidate, project_root / "templates", style=CvStyle.MODERNCV)
    ats = render_cv_ats(candidate, project_root / "templates")
    assert "Diplomado abandonado" not in tex
    assert "Diplomado abandonado" not in ats

    _workspace(tmp_path, project_root, data)
    monkeypatch.chdir(tmp_path)
    from jobbot.cli import run_cli

    assert run_cli(["profile", "show"], standalone_mode=False) == SUCCESS
    assert "Diplomado abandonado (abandoned)" in capsys.readouterr().out


def test_doctor_headline_without_a_completed_degree_warns_and_exits_zero(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    data = sample_profile_dict()
    data["personal"]["headline"] = "Doctor en Ciencias Ficticias"
    data["education"] = [
        {
            "id": "edu-doc",
            "institution": INSTITUTION,
            "degree": DEGREE,
            "start_date": "2021-03",
            "status": "candidate",
        }
    ]
    _workspace(tmp_path, project_root, data)
    monkeypatch.chdir(tmp_path)
    from jobbot.cli import run_cli

    code = run_cli(["profile", "validate"], standalone_mode=False)
    assert code == SUCCESS
    assert "headline says doctor without a completed degree" in capsys.readouterr().err


def test_abandoned_with_expected_end_and_an_earlier_expected_end_are_errors() -> None:
    with pytest.raises(ValidationError, match="expected_end"):
        _candidate(status="abandoned", expected_end="2027-06")
    with pytest.raises(ValidationError, match="expected_end"):
        _candidate(status="in_progress", expected_end="2020-01")


def test_unknown_status_names_the_four_values(tmp_path: Path) -> None:
    data = sample_profile_dict()
    data["education"][0]["status"] = "terminado"
    path = tmp_path / "profile.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    with pytest.raises(ProfileLoadError) as exc:
        load_profile(path)
    message = str(exc.value)
    for value in ("completed", "in_progress", "candidate", "abandoned"):
        assert value in message
