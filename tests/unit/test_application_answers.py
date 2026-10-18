"""Local application answers: preferences, never a national id (#286)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from jobbot.exit_codes import SUCCESS, VALIDATION_FAILURE
from jobbot.jobs.eligibility import (
    load_application_answers,
    salary_migration_hint,
)
from jobbot.ops.pii_guard import Finding, format_report, is_blocked_path
from jobbot.portals.field_homologation import NEEDS_HUMAN, ProfileFact, project_answer, resolve_fact

FIXTURES = Path(__file__).parents[1] / "fixtures" / "answers"
FORM = Path(__file__).parents[1] / "fixtures" / "forms" / "personal_data_es.html"


def test_full_answers_file_is_valid() -> None:
    answers = load_application_answers(FIXTURES / "full.yaml")

    assert answers.identity.birth_date is not None
    assert answers.identity.birth_date.isoformat() == "1990-01-01"
    assert answers.salary is not None
    assert answers.salary.basis == "net"
    assert answers.relocation == "within_country"
    assert salary_migration_hint(answers) is None


def test_candidate_spellings_are_folded_into_the_stored_tokens(tmp_path: Path) -> None:
    path = tmp_path / "answers.yaml"
    path.write_text(
        "identity:\n  gender_to_declare: Prefer Not To Say\n"
        "salary:\n  amount: 1500000\n  currency: clp\n  period: Month\n  basis: Gross\n",
        encoding="utf-8",
    )

    answers = load_application_answers(path)

    assert answers.identity.gender_to_declare == "prefer_not_to_say"
    assert answers.salary is not None
    assert answers.salary.currency == "CLP"
    assert answers.salary.period == "month"
    assert answers.salary.basis == "gross"


def test_job_answers_override_the_new_blocks_without_wiping_the_global_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / "answers.yaml"
    path.write_text(
        "identity:\n  birth_date: 1990-01-01\n  comuna: Comuna Ejemplo\n"
        "salary:\n  amount: 1500000\n  currency: CLP\n  period: month\n  basis: net\n"
        "job_types: [full_time]\n",
        encoding="utf-8",
    )
    job_answers = tmp_path / "job-answers.yaml"
    job_answers.write_text(
        "identity:\n  birth_date:\n  comuna: Otra Comuna\n"
        "salary:\n  amount: 2000000\n  currency:\n  period:\n  basis:\n"
        "availability:\n  from_date: 2026-11-01\n"
        "job_types: []\ndesired_titles: [Analista]\n",
        encoding="utf-8",
    )

    answers = load_application_answers(path, job_answers=job_answers)

    assert answers.identity.comuna == "Otra Comuna"
    assert answers.identity.birth_date is not None
    assert answers.salary is not None
    assert answers.salary.amount == 2000000
    assert answers.salary.currency == "CLP"
    assert answers.availability is not None
    assert answers.desired_titles == ["Analista"]
    assert answers.job_types == ["full_time"]


def test_unknown_rut_key_is_named() -> None:
    with pytest.raises(ValueError, match="rut"):
        load_application_answers(FIXTURES / "with_rut.yaml")


def test_legacy_salary_sentence_suggests_a_migration_and_writes_nothing() -> None:
    path = FIXTURES / "legacy_salary_text.yaml"
    before = path.read_text(encoding="utf-8")

    answers = load_application_answers(path)
    hint = salary_migration_hint(answers)

    assert hint is not None
    assert "salary.amount: 1500000" in hint
    assert "salary.basis: net" in hint
    assert "no se escribió" in hint
    assert path.read_text(encoding="utf-8") == before


def test_form_labels_map_birth_date_and_leave_a_national_id_human() -> None:
    labels = re.findall(r"<label>(.*?)</label>", FORM.read_text(encoding="utf-8"))
    answers = load_application_answers(FIXTURES / "full.yaml")

    assert resolve_fact(labels[0]) is ProfileFact.BIRTH_DATE
    assert project_answer(labels[1], answers) == NEEDS_HUMAN
    assert resolve_fact(labels[2]) is ProfileFact.SALARY_GROSS
    assert project_answer(labels[2], answers) == NEEDS_HUMAN


def test_answers_file_content_is_blocked_on_a_commit() -> None:
    text = (FIXTURES / "full.yaml").read_text(encoding="utf-8")
    path = "data/application_answers.yaml"

    reason = is_blocked_path(path)
    assert reason
    assert "birth_date" in text
    report = format_report([Finding(path, f"blocked path ({reason})")])
    assert path in report
    assert "blocked" in report


def _workspace(tmp_path: Path, project_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = tmp_path / "data"
    data.mkdir()
    (tmp_path / "output").mkdir()
    example = project_root / "data" / "profile.example.yaml"
    raw = yaml.safe_load(example.read_text(encoding="utf-8"))
    (data / "profile.yaml").write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (tmp_path / ".jobbot.toml").write_text(
        f'[paths]\ntemplates = "{project_root / "templates"}"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)


def test_validate_accepts_the_full_file_and_rejects_rut(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    target = tmp_path / "data" / "application_answers.yaml"
    target.write_text((FIXTURES / "full.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    from jobbot.cli import run_cli

    code = run_cli(["profile", "validate"], standalone_mode=False)
    assert code == SUCCESS

    target.write_text((FIXTURES / "with_rut.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    rejected = run_cli(["profile", "validate"], standalone_mode=False)
    captured = capsys.readouterr()
    assert rejected == VALIDATION_FAILURE
    assert "rut" in captured.err


def test_show_names_blocks_and_hides_values(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    target = tmp_path / "data" / "application_answers.yaml"
    target.write_text((FIXTURES / "full.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    from jobbot.cli import run_cli

    code = run_cli(["profile", "answers", "show"], standalone_mode=False)
    out = capsys.readouterr().out

    assert code == SUCCESS
    assert "identity" in out
    assert "salary" in out
    assert "1990-01-01" not in out
    assert "1500000" not in out
    assert "Comuna Ejemplo" not in out


def test_validate_suggests_the_legacy_salary_without_writing(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    target = tmp_path / "data" / "application_answers.yaml"
    original = (FIXTURES / "legacy_salary_text.yaml").read_text(encoding="utf-8")
    target.write_text(original, encoding="utf-8")
    from jobbot.cli import run_cli

    code = run_cli(["profile", "validate"], standalone_mode=False)
    out = capsys.readouterr().out

    assert code == SUCCESS
    assert "migrar" in out
    assert "salary.amount" in out
    assert target.read_text(encoding="utf-8") == original


def test_set_refuses_a_national_id_and_writes_only_with_yes(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    target = tmp_path / "data" / "application_answers.yaml"
    from jobbot.cli import run_cli

    refused = run_cli(["profile", "answers", "set", "rut", "no-se-guarda"], standalone_mode=False)
    assert refused == VALIDATION_FAILURE
    assert not target.exists()

    preview = run_cli(
        ["profile", "answers", "set", "salary.amount", "1500000"],
        standalone_mode=False,
    )
    assert preview == SUCCESS
    assert not target.exists()

    written = run_cli(
        ["profile", "answers", "set", "salary.amount", "1500000", "--yes"],
        standalone_mode=False,
    )
    assert written == SUCCESS
    stored = target.read_text(encoding="utf-8")
    assert "1500000" in stored
    assert "rut" not in stored
