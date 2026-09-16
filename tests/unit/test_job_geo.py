"""Country preference for job discovery (default CL, overridable)."""

from __future__ import annotations

from pathlib import Path

from jobbot.config import load_config
from jobbot.jobs.geo import (
    DEFAULT_COUNTRIES,
    country_allows,
    detect_country,
    mentions_remote,
    normalize_country,
)


def test_normalize_country_accepts_codes_and_names() -> None:
    assert normalize_country("cl") == "CL"
    assert normalize_country("CL") == "CL"
    assert normalize_country("Chile") == "CL"
    assert normalize_country("méxico") == "MX"
    assert normalize_country("") is None


def test_detect_country_from_real_post_wording() -> None:
    assert detect_country("Data Scientist en Santiago, Chile. Sueldo en CLP") == "CL"
    assert detect_country("Vacantes exclusivas en TI para CDMX") == "MX"
    assert detect_country("Data Scientist → $46,000 – $51,000 libres, Ciudad de México") == "MX"
    assert detect_country("Phaxsi, startup peruana; prácticas en Lima") == "PE"
    assert detect_country("Buscamos analista en Buenos Aires, Argentina") == "AR"
    assert detect_country("Data Scientist for a global team") is None


def test_mentions_remote() -> None:
    assert mentions_remote("100% remoto desde cualquier país")
    assert mentions_remote("Fully remote role")
    assert not mentions_remote("Modalidad presencial en oficina")


def test_country_allows_default_is_chile() -> None:
    assert DEFAULT_COUNTRIES == ("CL",)
    assert country_allows("Puesto en Santiago, Chile", wanted=DEFAULT_COUNTRIES)
    assert not country_allows("Vacante para CDMX, pago en MXN", wanted=DEFAULT_COUNTRIES)


def test_country_allows_keeps_undetectable_and_remote_posts() -> None:
    # Never drop a post we cannot classify: better a human decides.
    assert country_allows("Data Scientist for a global team", wanted=("CL",))
    assert country_allows("Remote worldwide, team in Ciudad de México", wanted=("CL",))
    assert not country_allows(
        "Remote worldwide, team in Ciudad de México",
        wanted=("CL",),
        allow_remote=False,
    )


def test_country_allows_without_preference_keeps_everything() -> None:
    assert country_allows("Vacante para CDMX", wanted=())


def test_config_defaults_to_chile_and_reads_search_section(tmp_path: Path) -> None:
    assert load_config(tmp_path).search.countries == ("CL",)

    (tmp_path / ".jobbot.toml").write_text(
        '[search]\ncountries = ["cl", "Argentina"]\nallow_remote = false\n',
        encoding="utf-8",
    )
    config = load_config(tmp_path)
    assert config.search.countries == ("CL", "AR")
    assert config.search.allow_remote is False


def test_config_falls_back_to_indeed_country(tmp_path: Path) -> None:
    (tmp_path / ".jobbot.toml").write_text('[indeed]\ncountry = "pe"\n', encoding="utf-8")
    assert load_config(tmp_path).search.countries == ("PE",)


def test_resolve_countries_precedence() -> None:
    from jobbot.jobs.geo import resolve_countries

    assert resolve_countries(("CL",)) == ("CL",)
    assert resolve_countries(("CL",), ["pe", "Argentina"]) == ("PE", "AR")
    assert resolve_countries(("CL",), ["pe"], any_country=True) == ()
    assert resolve_countries(("CL",), []) == ("CL",)
