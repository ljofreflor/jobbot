"""CLI for portal fill sheets and coverage. No network, no browser."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from jobbot.exit_codes import SUCCESS, VALIDATION_FAILURE
from jobbot.ops.pii_guard import is_blocked_path, scan_text
from tests.fixtures.profile import non_data_profile_dict


def _workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "profile.yaml").write_text(
        yaml.safe_dump(non_data_profile_dict(), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (tmp_path / "data" / "aliases.yaml").write_text(
        "aliases:\n  alias-01: ada.example@example.org\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)


def test_status_without_a_state_file_lists_the_registry_as_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from jobbot.cli import run_cli

    _workspace(tmp_path, monkeypatch)
    (tmp_path / "data" / "portals.yaml").write_text(
        yaml.safe_dump(
            {
                "portals": [
                    {"domain": "alpha.example", "ats_kind": "unknown"},
                    {"domain": "beta.example", "ats_kind": "unknown"},
                    {"domain": "gamma.example", "ats_kind": "unknown"},
                ]
            }
        ),
        encoding="utf-8",
    )

    assert run_cli(["portals", "profile", "status", "--json"], standalone_mode=False) == SUCCESS

    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["kpi_num"] == 0
    assert {row["portal"] for row in payload["portals"]} == {
        "alpha.example",
        "beta.example",
        "gamma.example",
    }
    assert {row["status"] for row in payload["portals"]} == {"unknown"}
    assert scan_text(out, "status.txt") == []
    assert "Marta Soto Vera" not in out


def test_status_prints_the_account_ratio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from jobbot.cli import run_cli

    _workspace(tmp_path, monkeypatch)
    (tmp_path / "data" / "portals.yaml").write_text(
        yaml.safe_dump(
            {
                "portals": [
                    {"domain": "alpha.example", "ats_kind": "unknown"},
                    {"domain": "beta.example", "ats_kind": "unknown"},
                    {"domain": "gamma.example", "ats_kind": "unknown"},
                ]
            }
        ),
        encoding="utf-8",
    )

    assert run_cli(["portals", "profile", "status"], standalone_mode=False) == SUCCESS
    assert "accounts 0/3" in capsys.readouterr().out


def test_status_json_matches_the_three_portal_fixture(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """alta 7/7 level 3, media 6/7 level 2, baja unknown, KPI 11/14. No profile values."""
    from jobbot.cli import run_cli

    _workspace(tmp_path, monkeypatch)
    fixture = project_root / "tests/fixtures/portals/portal_profiles_3.yaml"
    (tmp_path / "data" / "portal_profiles.yaml").write_text(
        fixture.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    pdf = tmp_path / "output" / "base" / "cv.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes((project_root / "tests/fixtures/portals/cv_bytes.txt").read_bytes())

    assert run_cli(["portals", "profile", "status", "--json"], standalone_mode=False) == SUCCESS

    out = capsys.readouterr().out
    payload = json.loads(out)
    by_id = {row["portal"]: row for row in payload["portals"]}
    assert (payload["kpi_num"], payload["kpi_den"]) == (11, 14)
    assert by_id["alta"]["status"] == "in_sync"
    assert by_id["alta"]["level"] == 3
    assert (by_id["alta"]["covered"], by_id["alta"]["applicable"]) == (7, 7)
    assert by_id["media"]["status"] == "sst_changed"
    assert by_id["media"]["level"] == 2
    assert (by_id["media"]["covered"], by_id["media"]["applicable"]) == (6, 7)
    assert by_id["baja"]["status"] == "unknown"
    assert by_id["baja"]["level"] == 0
    assert "Marta Soto Vera" not in out
    assert "marta.soto@example.com" not in out
    assert scan_text(out, "status.txt") == []


def test_identity_bound_sheet_uses_the_alias_and_marks_sst_gaps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from jobbot.cli import run_cli
    from jobbot.portals.fill_catalog import catalog_state, fill_portal
    from jobbot.portals.profile_state import default_state_path, save_states

    _workspace(tmp_path, monkeypatch)
    portal = fill_portal("adp")
    assert portal is not None
    state = catalog_state(portal)
    state.email_alias = "alias-01"
    save_states([state], default_state_path(tmp_path))

    assert run_cli(["portals", "profile", "sheet", "adp"], standalone_mode=False) == SUCCESS

    sheet = capsys.readouterr().out
    assert "alias-01" in sheet
    assert "ada.example@example.org" in sheet
    assert "marta.soto@example.com" not in sheet
    assert "[falta en el SST: national_id]" in sheet
    assert "identidad estatal" in sheet
    assert "Geodetec" in sheet


def test_mark_updated_none_does_not_raise_coverage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from jobbot.cli import run_cli
    from jobbot.portals.fill_catalog import catalog_state, fill_portal
    from jobbot.portals.profile_state import default_state_path, load_states, save_states

    _workspace(tmp_path, monkeypatch)
    portal = fill_portal("devex")
    assert portal is not None
    state = catalog_state(portal)
    state.account = state.account.__class__("evidenced")
    save_states([state], default_state_path(tmp_path))

    code = run_cli(
        [
            "portals",
            "profile",
            "mark-updated",
            "devex",
            "--sections",
            "identity",
            "--evidence",
            "none",
        ],
        standalone_mode=False,
    )
    assert code == SUCCESS
    stored = load_states(default_state_path(tmp_path))[0]
    assert stored.section_hashes == {}

    status = run_cli(["portals", "profile", "status", "--json"], standalone_mode=False)
    assert status == SUCCESS


def test_receipt_without_a_file_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from jobbot.cli import run_cli
    from jobbot.portals.fill_catalog import catalog_state, fill_portal
    from jobbot.portals.profile_state import default_state_path, save_states

    _workspace(tmp_path, monkeypatch)
    portal = fill_portal("fao")
    assert portal is not None
    save_states([catalog_state(portal)], default_state_path(tmp_path))

    code = run_cli(
        [
            "portals",
            "profile",
            "mark-updated",
            "fao",
            "--sections",
            "identity",
            "--evidence",
            "receipt",
        ],
        standalone_mode=False,
    )
    assert code == VALIDATION_FAILURE


def test_import_without_apply_does_not_write(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from jobbot.cli import run_cli
    from jobbot.portals.profile_state import default_state_path

    _workspace(tmp_path, monkeypatch)
    csv_path = project_root / "tests/fixtures/portals/tracker_3.csv"

    assert (
        run_cli(
            ["portals", "profile", "import", "--csv", str(csv_path)],
            standalone_mode=False,
        )
        == SUCCESS
    )

    out = capsys.readouterr().out
    assert "ignorada: extra" in out
    assert not default_state_path(tmp_path).exists()


def test_push_refuses_identity_bound_and_unwritten_adapters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from jobbot.cli import run_cli

    _workspace(tmp_path, monkeypatch)

    assert run_cli(["portals", "profile", "push", "adp"], standalone_mode=False) == (
        VALIDATION_FAILURE
    )
    err = capsys.readouterr().err
    assert "identity_bound" in err

    code = run_cli(
        ["portals", "profile", "push", "un_careers", "--apply"],
        standalone_mode=False,
    )
    assert code == VALIDATION_FAILURE
    err = capsys.readouterr().err
    assert "inspira" in err
    assert "Nothing was typed" in err


def test_empleos_publicos_sheet_does_not_type_or_attach(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from jobbot.cli import run_cli

    _workspace(tmp_path, monkeypatch)

    assert (
        run_cli(["portals", "profile", "sheet", "empleos_publicos"], standalone_mode=False)
        == SUCCESS
    )
    sheet = capsys.readouterr().out
    assert "Empleos Públicos" in sheet
    assert "identidad estatal" in sheet
    assert "[falta en el SST: national_id]" in sheet
    assert "password" not in sheet.casefold()

    code = run_cli(
        ["portals", "profile", "push", "empleos_publicos", "--apply"],
        standalone_mode=False,
    )
    assert code == VALIDATION_FAILURE
    err = capsys.readouterr().err
    assert "identity_bound" in err
    assert "does not attach" in err


def test_adp_sheet_does_not_type_or_attach(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from jobbot.cli import run_cli

    _workspace(tmp_path, monkeypatch)

    assert run_cli(["portals", "profile", "sheet", "adp"], standalone_mode=False) == SUCCESS
    sheet = capsys.readouterr().out
    assert "Alta Dirección Pública" in sheet
    assert "identidad estatal" in sheet
    assert "[falta en el SST: national_id]" in sheet
    assert "password" not in sheet.casefold()

    code = run_cli(["portals", "profile", "push", "adp", "--apply"], standalone_mode=False)
    assert code == VALIDATION_FAILURE
    err = capsys.readouterr().err
    assert "identity_bound" in err
    assert "does not attach" in err


def test_un_careers_sheet_does_not_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from jobbot.cli import run_cli

    _workspace(tmp_path, monkeypatch)

    assert (
        run_cli(["portals", "profile", "sheet", "un_careers"], standalone_mode=False) == SUCCESS
    )
    sheet = capsys.readouterr().out
    assert "UN Careers / Inspira" in sheet
    assert "no envía la postulación" in sheet
    for gap in ("date_of_birth", "gender", "nationality", "disability"):
        assert f"[falta en el SST: {gap}]" in sheet
    assert "password" not in sheet.casefold()

    code = run_cli(
        ["portals", "profile", "push", "un_careers", "--apply"],
        standalone_mode=False,
    )
    assert code == VALIDATION_FAILURE
    err = capsys.readouterr().err
    assert "inspira" in err
    assert "Nothing was typed" in err


def test_who_sheet_does_not_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from jobbot.cli import run_cli

    _workspace(tmp_path, monkeypatch)

    assert run_cli(["portals", "profile", "sheet", "oms_who"], standalone_mode=False) == SUCCESS
    sheet = capsys.readouterr().out
    assert "WHO Careers (Taleo)" in sheet
    assert "no envía la postulación" in sheet
    assert "adapter: `taleo`" in sheet
    assert "password" not in sheet.casefold()

    code = run_cli(["portals", "profile", "push", "oms_who", "--apply"], standalone_mode=False)
    assert code == VALIDATION_FAILURE
    err = capsys.readouterr().err
    assert "taleo" in err
    assert "Nothing was typed" in err


def test_unicef_sheet_does_not_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from jobbot.cli import run_cli

    _workspace(tmp_path, monkeypatch)

    assert run_cli(["portals", "profile", "sheet", "unicef"], standalone_mode=False) == SUCCESS
    sheet = capsys.readouterr().out
    assert "UNICEF Careers (PageUp)" in sheet
    assert "no envía la postulación" in sheet
    assert "adapter: `pageup`" in sheet
    assert "password" not in sheet.casefold()

    code = run_cli(["portals", "profile", "push", "unicef", "--apply"], standalone_mode=False)
    assert code == VALIDATION_FAILURE
    err = capsys.readouterr().err
    assert "pageup" in err
    assert "Nothing was typed" in err


def test_devex_sheet_does_not_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from jobbot.cli import run_cli

    _workspace(tmp_path, monkeypatch)

    assert run_cli(["portals", "profile", "sheet", "devex"], standalone_mode=False) == SUCCESS
    sheet = capsys.readouterr().out
    assert "# Devex" in sheet
    assert "no envía la postulación" in sheet
    assert "adapter: `devex`" in sheet
    assert "password" not in sheet.casefold()

    code = run_cli(["portals", "profile", "push", "devex", "--apply"], standalone_mode=False)
    assert code == VALIDATION_FAILURE
    err = capsys.readouterr().err
    assert "devex" in err
    assert "Nothing was typed" in err


def test_impactpool_sheet_does_not_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from jobbot.cli import run_cli

    _workspace(tmp_path, monkeypatch)

    assert (
        run_cli(["portals", "profile", "sheet", "impactpool"], standalone_mode=False) == SUCCESS
    )
    sheet = capsys.readouterr().out
    assert "# Impactpool" in sheet
    assert "no envía la postulación" in sheet
    assert "adapter: `impactpool`" in sheet
    assert "password" not in sheet.casefold()

    code = run_cli(
        ["portals", "profile", "push", "impactpool", "--apply"],
        standalone_mode=False,
    )
    assert code == VALIDATION_FAILURE
    err = capsys.readouterr().err
    assert "impactpool" in err
    assert "Nothing was typed" in err


def test_idb_sheet_does_not_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from jobbot.cli import run_cli

    _workspace(tmp_path, monkeypatch)

    assert run_cli(["portals", "profile", "sheet", "bid_idb"], standalone_mode=False) == SUCCESS
    sheet = capsys.readouterr().out
    assert "IDB Jobs" in sheet
    assert "no envía la postulación" in sheet
    assert "adapter: `generic`" in sheet
    assert "password" not in sheet.casefold()

    code = run_cli(["portals", "profile", "push", "bid_idb", "--apply"], standalone_mode=False)
    assert code == VALIDATION_FAILURE
    err = capsys.readouterr().err
    assert "generic" in err
    assert "Nothing was typed" in err


def test_world_bank_sheet_does_not_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from jobbot.cli import run_cli

    _workspace(tmp_path, monkeypatch)

    assert (
        run_cli(["portals", "profile", "sheet", "banco_mundial"], standalone_mode=False)
        == SUCCESS
    )
    sheet = capsys.readouterr().out
    assert "World Bank Group (Cornerstone)" in sheet
    assert "no envía la postulación" in sheet
    assert "adapter: `cornerstone`" in sheet
    assert "password" not in sheet.casefold()

    code = run_cli(
        ["portals", "profile", "push", "banco_mundial", "--apply"],
        standalone_mode=False,
    )
    assert code == VALIDATION_FAILURE
    err = capsys.readouterr().err
    assert "cornerstone" in err
    assert "Nothing was typed" in err


def test_undp_sheet_does_not_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from jobbot.cli import run_cli

    _workspace(tmp_path, monkeypatch)

    assert (
        run_cli(["portals", "profile", "sheet", "pnud_undp"], standalone_mode=False) == SUCCESS
    )
    sheet = capsys.readouterr().out
    assert "UNDP Careers" in sheet
    assert "no envía la postulación" in sheet
    assert "adapter: `oracle_orc`" in sheet
    assert "password" not in sheet.casefold()

    code = run_cli(
        ["portals", "profile", "push", "pnud_undp", "--apply"],
        standalone_mode=False,
    )
    assert code == VALIDATION_FAILURE
    err = capsys.readouterr().err
    assert "oracle_orc" in err
    assert "Nothing was typed" in err


def test_unops_sheet_does_not_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from jobbot.cli import run_cli

    _workspace(tmp_path, monkeypatch)

    assert run_cli(["portals", "profile", "sheet", "unops"], standalone_mode=False) == SUCCESS
    sheet = capsys.readouterr().out
    assert "UNOPS Talent Community" in sheet
    assert "no envía la postulación" in sheet
    assert "adapter: `generic`" in sheet
    assert "password" not in sheet.casefold()

    code = run_cli(["portals", "profile", "push", "unops", "--apply"], standalone_mode=False)
    assert code == VALIDATION_FAILURE
    err = capsys.readouterr().err
    assert "generic" in err
    assert "Nothing was typed" in err


def test_iom_sheet_does_not_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from jobbot.cli import run_cli

    _workspace(tmp_path, monkeypatch)

    assert run_cli(["portals", "profile", "sheet", "oim_iom"], standalone_mode=False) == SUCCESS
    sheet = capsys.readouterr().out
    assert "IOM Careers" in sheet
    assert "no envía la postulación" in sheet
    assert "adapter: `oracle_orc`" in sheet
    assert "password" not in sheet.casefold()

    code = run_cli(["portals", "profile", "push", "oim_iom", "--apply"], standalone_mode=False)
    assert code == VALIDATION_FAILURE
    err = capsys.readouterr().err
    assert "oracle_orc" in err
    assert "Nothing was typed" in err


def test_fao_sheet_does_not_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from jobbot.cli import run_cli

    _workspace(tmp_path, monkeypatch)

    assert run_cli(["portals", "profile", "sheet", "fao"], standalone_mode=False) == SUCCESS
    sheet = capsys.readouterr().out
    assert "FAO Jobs (Taleo)" in sheet
    assert "no envía la postulación" in sheet
    assert "adapter: `taleo`" in sheet
    assert "password" not in sheet.casefold()

    code = run_cli(["portals", "profile", "push", "fao", "--apply"], standalone_mode=False)
    assert code == VALIDATION_FAILURE
    err = capsys.readouterr().err
    assert "taleo" in err
    assert "Nothing was typed" in err


def test_laborum_sheet_does_not_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from jobbot.cli import run_cli

    _workspace(tmp_path, monkeypatch)

    assert run_cli(["portals", "profile", "sheet", "laborum"], standalone_mode=False) == SUCCESS
    sheet = capsys.readouterr().out
    assert "# Laborum" in sheet
    assert "no envía la postulación" in sheet
    assert "adapter: `generic`" in sheet
    assert "password" not in sheet.casefold()

    code = run_cli(["portals", "profile", "push", "laborum", "--apply"], standalone_mode=False)
    assert code == VALIDATION_FAILURE
    err = capsys.readouterr().err
    assert "generic" in err
    assert "Nothing was typed" in err


def test_korn_ferry_sheet_does_not_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from jobbot.cli import run_cli

    _workspace(tmp_path, monkeypatch)

    assert (
        run_cli(["portals", "profile", "sheet", "korn_ferry"], standalone_mode=False) == SUCCESS
    )
    sheet = capsys.readouterr().out
    assert "# Korn Ferry" in sheet
    assert "no envía la postulación" in sheet
    assert "adapter: `generic`" in sheet
    assert "password" not in sheet.casefold()

    code = run_cli(
        ["portals", "profile", "push", "korn_ferry", "--apply"],
        standalone_mode=False,
    )
    assert code == VALIDATION_FAILURE
    err = capsys.readouterr().err
    assert "generic" in err
    assert "Nothing was typed" in err


def test_robert_walters_sheet_does_not_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from jobbot.cli import run_cli

    _workspace(tmp_path, monkeypatch)

    assert (
        run_cli(["portals", "profile", "sheet", "robert_walters"], standalone_mode=False)
        == SUCCESS
    )
    sheet = capsys.readouterr().out
    assert "# Robert Walters" in sheet
    assert "no envía la postulación" in sheet
    assert "adapter: `generic`" in sheet
    assert "password" not in sheet.casefold()

    code = run_cli(
        ["portals", "profile", "push", "robert_walters", "--apply"],
        standalone_mode=False,
    )
    assert code == VALIDATION_FAILURE
    err = capsys.readouterr().err
    assert "generic" in err
    assert "Nothing was typed" in err


def test_ifrc_sheet_does_not_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from jobbot.cli import run_cli

    _workspace(tmp_path, monkeypatch)

    assert run_cli(["portals", "profile", "sheet", "ifrc"], standalone_mode=False) == SUCCESS
    sheet = capsys.readouterr().out
    assert "IFRC Careers" in sheet
    assert "no envía la postulación" in sheet
    assert "adapter: `lumesse`" in sheet
    assert "password" not in sheet.casefold()

    code = run_cli(["portals", "profile", "push", "ifrc", "--apply"], standalone_mode=False)
    assert code == VALIDATION_FAILURE
    err = capsys.readouterr().err
    assert "lumesse" in err
    assert "Nothing was typed" in err


def test_computrabajo_sheet_does_not_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from jobbot.cli import run_cli

    _workspace(tmp_path, monkeypatch)

    assert (
        run_cli(["portals", "profile", "sheet", "computrabajo"], standalone_mode=False) == SUCCESS
    )
    sheet = capsys.readouterr().out
    assert "# Computrabajo" in sheet
    assert "no envía la postulación" in sheet
    assert "adapter: `generic`" in sheet
    assert "password" not in sheet.casefold()

    code = run_cli(
        ["portals", "profile", "push", "computrabajo", "--apply"],
        standalone_mode=False,
    )
    assert code == VALIDATION_FAILURE
    err = capsys.readouterr().err
    assert "generic" in err
    assert "Nothing was typed" in err


def test_bne_sheet_does_not_type_or_attach(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from jobbot.cli import run_cli

    _workspace(tmp_path, monkeypatch)

    assert run_cli(["portals", "profile", "sheet", "bne"], standalone_mode=False) == SUCCESS
    sheet = capsys.readouterr().out
    assert "Bolsa Nacional de Empleo" in sheet
    assert "identidad estatal" in sheet
    assert "[falta en el SST: national_id]" in sheet
    assert "password" not in sheet.casefold()

    code = run_cli(["portals", "profile", "push", "bne", "--apply"], standalone_mode=False)
    assert code == VALIDATION_FAILURE
    err = capsys.readouterr().err
    assert "identity_bound" in err
    assert "does not attach" in err


def test_seed_names_the_portals_that_need_a_fill_sheet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from jobbot.cli import run_cli
    from jobbot.portals.profile_state import default_state_path

    _workspace(tmp_path, monkeypatch)

    assert run_cli(["portals", "profile", "seed"], standalone_mode=False) == SUCCESS

    out = capsys.readouterr().out
    for portal in ("un_careers", "unicef", "fao", "adp", "devex", "impactpool"):
        assert portal in out
    assert not default_state_path(tmp_path).exists()


def test_state_files_are_blocked_as_pii() -> None:
    assert is_blocked_path("data/portal_profiles.yaml")
    assert is_blocked_path("data/aliases.yaml")
    assert is_blocked_path("data/aliases.yaml.bak")
