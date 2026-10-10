"""The public mark is one closing line; dual brand swaps the face, not the engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from jobbot.adapters.getonboard.draft import EXPERIENCE_MAX, build_permanent_profile_fields
from jobbot.adapters.indeed.package import build_indeed_sync_package
from jobbot.branding import (
    DEFAULT_BRAND,
    ENGINE_NAME,
    MARK,
    brand_from_parts,
    get_brand,
    reset_brand,
    set_brand,
    stamp_description,
    strip_mark,
)
from jobbot.config import load_config
from jobbot.models.candidate import Candidate
from tests.fixtures.profile import sample_profile_dict


@pytest.fixture(autouse=True)
def _default_brand() -> None:
    reset_brand()
    yield
    reset_brand()


def test_stamp_once_and_strip() -> None:
    once = stamp_description("Data scientist.", max_len=200)
    assert once.endswith(MARK)
    assert stamp_description(once).count(MARK) == 1
    assert strip_mark(once) == "Data scientist."


def test_blank_stays_blank() -> None:
    assert stamp_description("  ") == ""


def test_stamp_respects_limit() -> None:
    text = stamp_description("palabra " * 500, max_len=80)
    assert len(text) <= 80
    assert text.endswith(MARK)


def test_published_descriptions_carry_the_mark() -> None:
    candidate = Candidate.model_validate(sample_profile_dict())
    fields = build_permanent_profile_fields(candidate)
    package = build_indeed_sync_package(candidate)
    assert fields.experiencia_y_perfil.endswith(MARK)
    assert len(fields.experiencia_y_perfil) <= EXPERIENCE_MAX
    assert package.summary.endswith(MARK)
    assert package.headline.endswith(MARK) is False


def test_engine_name_stays_jobbot_when_product_face_changes() -> None:
    other = brand_from_parts(product_name="Oficio")
    set_brand(other)
    assert ENGINE_NAME == "jobbot"
    assert get_brand().product_name == "Oficio"
    assert get_brand().mark == "powered by Oficio sync CV"
    stamped = stamp_description("Hechos del perfil.")
    assert stamped.endswith("powered by Oficio sync CV")
    assert "Jobbot" not in stamped


def test_strip_recognises_default_mark_after_skin_change() -> None:
    set_brand(brand_from_parts(product_name="Oficio"))
    legacy = f"Texto.\n\n{DEFAULT_BRAND.mark}"
    assert strip_mark(legacy) == "Texto."


def test_load_config_activates_brand_section(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("JOBBOT_PRODUCT_NAME", raising=False)
    monkeypatch.delenv("JOBBOT_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".jobbot.toml").write_text(
        '[brand]\nproduct_name = "Oficio"\nproject_url = "https://example.org/oficio"\n',
        encoding="utf-8",
    )
    (tmp_path / ".local").mkdir()
    load_config()
    brand = get_brand()
    assert brand.product_name == "Oficio"
    assert brand.repo_url == "https://example.org/oficio"
    assert brand.mark == "powered by Oficio sync CV"


def test_env_product_name_sets_brand(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("JOBBOT_PRODUCT_NAME", "Oficio")
    monkeypatch.delenv("JOBBOT_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)
    load_config()
    assert get_brand().product_name == "Oficio"
