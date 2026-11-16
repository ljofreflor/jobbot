"""A declared skill points at the role that already shows it, and nowhere else."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from jobbot.exit_codes import SUCCESS
from jobbot.models.candidate import Candidate
from jobbot.profile.skill_map import format_map, format_unbacked, map_skills
from jobbot.profile.validator import validate_candidate

DECLARED = (
    "Gestion de redes",
    "Archivo documental",
    "Presupuesto anual",
    "Informe tecnico",
    "Epidemiological surveillance",
)
UNBACKED = "Origami ficticio"


def _profile() -> Candidate:
    def ach(ach_id: str, text: str, tag: str) -> dict[str, object]:
        return {"id": ach_id, "text": text, "tags": [tag]}

    def role(role_id: str, start: str, achievements: list[dict[str, object]]) -> dict[str, object]:
        return {
            "id": role_id,
            "company": "Organismo Ficticio",
            "title": "Cargo",
            "start_date": start,
            "end_date": "2024-12",
            "current": False,
            "achievements": achievements,
        }

    return Candidate.model_validate(
        {
            "personal": {
                "name": "Ana Ejemplo",
                "headline": "Profesional",
                "email": "ana@example.com",
            },
            "experience": [
                role(
                    "role-1",
                    "2022-01",
                    [
                        ach("ach-redes", "Coordine una red regional.", "gestion_de_redes"),
                        ach("ach-archivo", "Ordene el archivo central.", "archivo_documental"),
                    ],
                ),
                role(
                    "role-2",
                    "2020-01",
                    [
                        ach("ach-presupuesto", "Cerre el presupuesto anual.", "presupuesto_anual"),
                        ach("ach-informe", "Redacte el informe tecnico.", "informe_tecnico"),
                    ],
                ),
                role(
                    "role-3",
                    "2018-01",
                    [
                        ach(
                            "ach-vigilancia",
                            "Segui una serie de casos.",
                            "vigilancia_epidemiologica",
                        ),
                        ach("ach-ceramica", "Moldee una pieza.", "ceramica_artesanal"),
                    ],
                ),
            ],
            "skills": {"other": [*DECLARED, UNBACKED]},
        }
    )


def test_each_declared_skill_points_at_the_role_that_shows_it() -> None:
    lines = format_map(map_skills(_profile()))
    expected = {
        "Gestion de redes": "role-1 (ach-redes)",
        "Archivo documental": "role-1 (ach-archivo)",
        "Presupuesto anual": "role-2 (ach-presupuesto)",
        "Informe tecnico": "role-2 (ach-informe)",
        "Epidemiological surveillance": "role-3 (ach-vigilancia)",
    }
    for skill, where in expected.items():
        assert f"{skill} -> {where}" in lines
    assert all(not line.startswith("QGIS") for line in lines)
    assert UNBACKED not in "\n".join(lines)


def test_unbacked_skill_and_achievement_are_listed_and_not_linked() -> None:
    candidate = _profile()
    lines = format_unbacked(candidate)
    assert f"unbacked skill: {UNBACKED}" in lines
    assert "unbacked achievement: ach-ceramica" in lines
    assert not any(line.startswith(f"{UNBACKED} ->") for line in format_map(map_skills(candidate)))


def _workspace(tmp_path: Path, project_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "profile.yaml").write_text(
        yaml.safe_dump(_profile().model_dump(mode="json"), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)


def test_apply_without_confirmation_does_not_write(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    before = (tmp_path / "data" / "profile.yaml").read_text(encoding="utf-8")
    monkeypatch.setattr("jobbot.cli.typer.confirm", lambda *_args, **_kwargs: False)
    from jobbot.cli import run_cli

    code = run_cli(["profile", "skills-map", "--apply"], standalone_mode=False)
    assert code == SUCCESS
    assert (tmp_path / "data" / "profile.yaml").read_text(encoding="utf-8") == before
    assert list(tmp_path.glob("data/profile.yaml.bak.*")) == []


def test_apply_with_confirmation_backs_up_and_still_validates(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    monkeypatch.setattr("jobbot.cli.typer.confirm", lambda *_args, **_kwargs: True)
    from jobbot.cli import run_cli
    from jobbot.profile.loader import load_profile

    code = run_cli(["profile", "skills-map", "--apply"], standalone_mode=False)
    assert code == SUCCESS
    assert list(tmp_path.glob("data/profile.yaml.bak.*"))
    stored = load_profile(tmp_path / "data" / "profile.yaml")
    assert validate_candidate(stored).ok
    names = {row.skill for row in stored.skill_evidence}
    assert names == set(DECLARED)
    assert UNBACKED not in names
    assert "QGIS" not in names
