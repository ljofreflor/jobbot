"""Get on Board permanent profile maintainer tests."""

from pathlib import Path

import pytest
import yaml

from jobbot.adapters.getonboard.draft import (
    EDUCATION_MAX,
    EXPERIENCE_MAX,
    build_permanent_profile_fields,
    draft_getonboard_fields,
    load_permanent_profile,
    omission_line,
    render_permanent_profile_markdown,
    save_permanent_profile,
)
from jobbot.applications.manager import prepare_application_package
from jobbot.exit_codes import SUCCESS
from jobbot.models.candidate import Candidate
from jobbot.models.job import JobPosting
from tests.fixtures.profile import public_health_profile_dict, sample_profile_dict


def test_permanent_profile_within_limits_and_no_invention() -> None:
    candidate = Candidate.model_validate(sample_profile_dict())
    fields = build_permanent_profile_fields(candidate)
    assert len(fields.experiencia_y_perfil) <= EXPERIENCE_MAX
    assert "Mercado Libre" in fields.experiencia_y_perfil or "Data Scientist" in (
        fields.experiencia_y_perfil + fields.headline
    )
    assert "…" not in fields.experiencia_y_perfil
    assert "Stack habitual" not in fields.experiencia_y_perfil
    assert "Habilidades:" in fields.experiencia_y_perfil
    # Sample fixture includes Mercado Libre experience — must survive GoB length fit.
    assert "Mercado Libre" in fields.experiencia_y_perfil or "Data Scientist" in fields.headline


def test_summary_is_not_cut_mid_sentence_when_there_is_room() -> None:
    """A long summary was hard-cut at 549 chars, so GoB showed a dangling clause."""
    data = sample_profile_dict()
    data["summary"] = (
        "Senior Data Scientist con experiencia en fintech, retail y sector público. "
        + "Construyo modelos predictivos y plataformas de datos usadas a escala regional. "
        * 6
        + "Combino profundidad estadística con liderazgo técnico."
    )
    candidate = Candidate.model_validate(data)

    fields = build_permanent_profile_fields(candidate)
    summary_paragraph = fields.experiencia_y_perfil.split("\n\n")[0]

    assert len(fields.experiencia_y_perfil) <= EXPERIENCE_MAX
    assert summary_paragraph.endswith("."), summary_paragraph[-60:]
    # The whole summary fits under the cap, so nothing should have been dropped.
    assert summary_paragraph == data["summary"].strip()


def test_a_summary_too_long_for_the_cap_ends_on_a_sentence() -> None:
    data = sample_profile_dict()
    data["summary"] = "Lidero equipos de data science y productos de datos medibles. " * 40
    candidate = Candidate.model_validate(data)

    fields = build_permanent_profile_fields(candidate)
    summary_paragraph = fields.experiencia_y_perfil.split("\n\n")[0]

    assert len(fields.experiencia_y_perfil) <= EXPERIENCE_MAX
    assert summary_paragraph.endswith(".")
    assert "," not in summary_paragraph[-2:]


def test_save_and_load_permanent_profile(tmp_path: Path) -> None:
    candidate = Candidate.model_validate(sample_profile_dict())
    fields = build_permanent_profile_fields(candidate)
    md = save_permanent_profile(fields, tmp_path)
    assert md.is_file()
    assert "perfil permanente" in md.read_text(encoding="utf-8").casefold()
    loaded = load_permanent_profile(tmp_path)
    assert loaded is not None
    assert loaded.experiencia_y_perfil == fields.experiencia_y_perfil


def test_prepare_reuses_permanent_profile(tmp_path: Path) -> None:
    candidate = Candidate.model_validate(sample_profile_dict())
    permanent = build_permanent_profile_fields(candidate)
    # Mark permanent with a unique substring
    from jobbot.adapters.getonboard.draft import PermanentProfileFields

    custom = PermanentProfileFields(
        experiencia_y_perfil=permanent.experiencia_y_perfil + "\n\nPERMANENT_MARKER.",
        formacion_academica=permanent.formacion_academica,
        headline=permanent.headline,
        skills=permanent.skills,
    )
    save_permanent_profile(custom, tmp_path)
    job = JobPosting(
        id="J0091",
        title="Applied Scientist",
        company="NeuralWorks",
        ats_kind="getonboard",
        ats_url="https://www.getonbrd.com/jobs/x",
        description="Requires Kubernetes mastery.",
    )
    app_dir = prepare_application_package(job, tmp_path, candidate=candidate)
    text = (app_dir / "getonboard_es.md").read_text(encoding="utf-8")
    assert "PERMANENT_MARKER" in text
    assert "Kubernetes" not in text


def test_draft_getonboard_fields_dict_shape() -> None:
    candidate = Candidate.model_validate(sample_profile_dict())
    fields = draft_getonboard_fields(candidate)
    assert "experiencia_y_perfil" in fields
    assert "formacion_academica" in fields


def test_details_that_already_end_a_sentence_are_not_double_stopped() -> None:
    data = sample_profile_dict()
    data["education"] = [
        {
            "id": "mag",
            "institution": "Universidad del Litoral",
            "degree": "Magíster",
            "start_date": "2015-01",
            "end_date": "2017-12",
            "details": "Tesis sobre vigilancia.",
        }
    ]
    data["publications"] = []

    fields = build_permanent_profile_fields(Candidate.model_validate(data))

    assert ".." not in fields.formacion_academica
    assert fields.formacion_academica.startswith("Magíster — Universidad del Litoral")
    assert fields.formacion_academica.endswith("vigilancia.")


def test_education_items_that_do_not_fit_are_omitted_whole() -> None:
    data = sample_profile_dict()
    data["education"] = [
        {
            "id": f"curso-{index:02d}",
            "institution": f"Instituto {index:02d}",
            "degree": f"Curso {index:02d}",
            "start_date": "2010-01",
            "end_date": "2011-01",
            "details": "Oración de detalle del curso. " * 10,
        }
        for index in range(12)
    ]
    data["experience"] = [
        {
            "id": "docencia",
            "company": "Instituto 00",
            "title": "Docente",
            "start_date": "2012-01",
            "end_date": "2013-01",
            "current": False,
            "achievements": [],
        }
    ]
    data["publications"] = []

    fields = build_permanent_profile_fields(Candidate.model_validate(data))
    notice = omission_line(fields)
    markdown = render_permanent_profile_markdown(fields)

    assert len(fields.formacion_academica) <= EDUCATION_MAX
    assert not fields.formacion_academica.rstrip().endswith("—")
    assert fields.omitted_education > 0
    assert notice in markdown
    assert f"{fields.omitted_education} ítems de formación" in notice
    for token in ("Matlab", "VTK", "Ceamos"):
        assert token not in markdown


def test_permanent_markdown_names_no_other_domain() -> None:
    for factory in (sample_profile_dict, public_health_profile_dict):
        fields = build_permanent_profile_fields(Candidate.model_validate(factory()))
        markdown = render_permanent_profile_markdown(fields)
        for token in ("Matlab", "VTK", "Ceamos"):
            assert token not in markdown


def test_public_health_fixture_keeps_fetp_after_a_long_thesis() -> None:
    data = public_health_profile_dict()
    data["education"][0]["details"] = "Tema de tesis sobre vigilancia. " * 40
    data["education"].append(
        {
            "id": "fetp",
            "institution": "Programa Regional de Campo",
            "degree": "FETP Frontline",
            "start_date": "2018-01",
            "end_date": "2018-06",
            "details": "Curso aplicado de epidemiología de campo.",
        }
    )

    fields = build_permanent_profile_fields(Candidate.model_validate(data))

    assert "FETP Frontline" in fields.formacion_academica
    assert ".." not in fields.formacion_academica
    assert len(fields.formacion_academica) <= EDUCATION_MAX


def test_profile_without_education_stays_empty() -> None:
    data = sample_profile_dict()
    data["education"] = []
    data["experience"] = []
    data["publications"] = []

    fields = build_permanent_profile_fields(Candidate.model_validate(data))

    assert fields.formacion_academica == ""
    assert omission_line(fields) == ""


def test_prepare_prints_the_same_omission_count(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    data = sample_profile_dict()
    data["education"] = [
        {
            "id": f"curso-{index:02d}",
            "institution": f"Instituto {index:02d}",
            "degree": f"Curso {index:02d}",
            "start_date": "2010-01",
            "end_date": "2011-01",
            "details": "Oración de detalle del curso. " * 10,
        }
        for index in range(12)
    ]
    data["publications"] = []
    (tmp_path / "data").mkdir()
    (tmp_path / "output").mkdir()
    (tmp_path / "data" / "profile.yaml").write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (tmp_path / ".jobbot.toml").write_text(
        f'[paths]\ntemplates = "{project_root / "templates"}"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    from jobbot.cli import run_cli

    code = run_cli(["getonboard", "prepare"], standalone_mode=False)
    markdown = (tmp_path / "output" / "getonboard" / "profile_permanent.md").read_text(
        encoding="utf-8"
    )

    assert code == SUCCESS
    assert "Omitido por largo:" in markdown
    assert "Omitido por largo:" in capsys.readouterr().out
