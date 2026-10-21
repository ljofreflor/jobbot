"""Unit tests for skill normalization and job parsing."""

from __future__ import annotations

from jobbot.jobs.normalization import normalize_skill, skills_in_text
from jobbot.jobs.parsing import parse_job_text


def test_skills_in_text_reads_whole_phrases_across_languages() -> None:
    found = skills_in_text("Construí modelos predictivos; Magíster en Estadística.")
    assert {"predictive_modeling", "statistics"} <= found


def test_skills_in_text_ignores_short_aliases_and_fragments() -> None:
    assert skills_in_text("Área de I+D y R&D, equipo TF") == set()
    assert "predictive_modeling" not in skills_in_text("un modelo que no es predictivo")


def test_normalize_postgres_aliases() -> None:
    assert normalize_skill("PostgreSQL") == "postgresql"
    assert normalize_skill("postgres") == "postgresql"


def test_normalize_ml_aliases() -> None:
    assert normalize_skill("ML") == "machine_learning"
    assert normalize_skill("machine-learning") == "machine_learning"


def test_visualization_tool_aliases() -> None:
    for name in ("Power BI", "PowerBI", "Microsoft Power BI", "power-bi"):
        assert normalize_skill(name) == "power_bi"
    assert normalize_skill("ggplot") == normalize_skill("ggplot2") == "ggplot2"
    assert normalize_skill("pyplot") == normalize_skill("Matplotlib") == "matplotlib"
    assert normalize_skill("Looker") == "looker"


def test_looker_studio_is_not_looker() -> None:
    """Looker Studio is a different product: a shared word must not merge them."""
    assert normalize_skill("Looker Studio") == "looker_studio"
    assert normalize_skill("Looker Studio") != normalize_skill("Looker")


def test_dax_is_identity_only() -> None:
    assert normalize_skill("DAX") == "dax"


def test_sql_alias_not_matched_inside_typescript() -> None:
    """Regression: 'sql' must not match inside 'typescript'."""
    assert normalize_skill("TypeScript") != "sql"
    assert normalize_skill("React and TypeScript") != "sql"


def test_unknown_non_ds_terms_fall_through_unchanged() -> None:
    """Equivalence tables add recall; an unknown term is never dropped or gated."""
    assert normalize_skill("Ventilación Mecánica") == "ventilacion_mecanica"
    assert normalize_skill("Reanimación Cardiopulmonar") == "reanimacion_cardiopulmonar"
    assert normalize_skill("SEO") == "seo"
    assert normalize_skill("WordPress") == "wordpress"
    for term in ("Ventilación Mecánica", "SEO", "Triage Avanzado"):
        assert normalize_skill(term) not in {"machine_learning", "python", "sql"}


def test_short_skill_r_not_matched_inside_react() -> None:
    """Regression: bare 'R' must not match inside 'React'."""
    text = """Title: Junior Frontend Engineer
Company: Pixel Labs
Requirements:
- React and TypeScript
"""
    job = parse_job_text(text, job_id="J0099")
    assert "R" not in job.skills


def test_page_chrome_is_not_the_title() -> None:
    text = """Volver a resultados
Postular
Analista de operaciones
Acerca de Servicio Neutro

Perfil del cargo
- Coordinar los equipos regionales
"""
    job = parse_job_text(text, job_id="J0103")
    assert job.title == "Analista de operaciones"
    assert job.company == "Servicio Neutro"
    assert job.requirements == ["Coordinar los equipos regionales"]


def test_a_labelled_cargo_wins_over_the_chrome_line() -> None:
    job = parse_job_text(
        "Volver a resultados\nCargo: Analista de terreno\n",
        job_id="J0104",
    )
    assert job.title == "Analista de terreno"


def test_acerca_de_nosotros_is_not_an_employer() -> None:
    job = parse_job_text(
        "Analista de operaciones\nAcerca de nosotros\n",
        job_id="J0105",
    )
    assert job.title == "Analista de operaciones"
    assert job.company == "Unknown"


def test_spanish_requirement_headings_open_the_list() -> None:
    text = """Cargo: Analista de operaciones
Empresa: Servicio Neutro

Perfil del cargo
- Coordinar los equipos regionales
- Cinco años en el mismo oficio

Beneficios
- Salud
"""
    job = parse_job_text(text, job_id="J0101")
    assert job.requirements == [
        "Coordinar los equipos regionales",
        "Cinco años en el mismo oficio",
    ]


def test_a_question_heading_opens_requirements_for_any_trade() -> None:
    text = """¿Qué buscamos?
- Ventilación mecánica
- Registro clínico

Sobre nosotros
- Una institución neutra
"""
    job = parse_job_text(text, job_id="J0102")
    assert job.requirements == ["Ventilación mecánica", "Registro clínico"]


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
