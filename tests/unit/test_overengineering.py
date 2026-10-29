"""Over-engineering: competing criteria, quick wins, budget gate."""

from __future__ import annotations

from pathlib import Path

from jobbot.ops.overengineering import (
    EFFORT_EASY,
    KIND_LONE_FACTORY,
    KIND_LONE_STRATEGY,
    KIND_SINGLE_ABC,
    KIND_SINGLE_BASE,
    Budget,
    CriteriaSnapshot,
    check_budget,
    compensation_plan,
    format_quick_wins,
    format_report,
    load_budget,
    measure,
    quick_wins,
    report_json,
    scan,
)


def _write(root: Path, rel: str, source: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def _snap(tmp_path: Path, *, commands: int = 10, modules: int = 2) -> CriteriaSnapshot:
    return measure(tmp_path, commands=commands, modules=modules)


def test_single_implementor_abc_is_flagged(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "ports.py",
        """
from abc import ABC, abstractmethod

class OnlyOnce(ABC):
    @abstractmethod
    def run(self) -> None: ...

class OnlyOnceImpl(OnlyOnce):
    def run(self) -> None:
        pass
""",
    )
    report = scan(tmp_path)
    kinds = {(f.kind, f.name) for f in report.findings}
    assert (KIND_SINGLE_ABC, "OnlyOnce") in kinds
    assert report.score >= 3
    assert report.density > 0


def test_abc_with_two_implementors_is_clean(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "ports.py",
        """
from abc import ABC, abstractmethod

class Port(ABC):
    @abstractmethod
    def run(self) -> None: ...

class A(Port):
    def run(self) -> None:
        pass

class B(Port):
    def run(self) -> None:
        pass
""",
    )
    report = scan(tmp_path)
    assert not any(f.name == "Port" for f in report.findings)


def test_single_subclass_base_suffix(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "thing.py",
        """
class ThingBase:
    pass

class Thing(ThingBase):
    pass
""",
    )
    report = scan(tmp_path)
    assert any(f.kind == KIND_SINGLE_BASE and f.name == "ThingBase" for f in report.findings)


def test_lone_strategy_and_factory(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "patterns.py",
        """
from abc import ABC, abstractmethod

class ApplyStrategy(ABC):
    @abstractmethod
    def apply(self) -> None: ...

class WidgetFactory:
    def build(self) -> object:
        return object()
""",
    )
    report = scan(tmp_path)
    kinds = {f.kind for f in report.findings}
    assert KIND_LONE_STRATEGY in kinds
    assert KIND_LONE_FACTORY in kinds


def test_allowlisted_adapter_ports_skipped() -> None:
    """Real tree: hexagonal bases may have one local stub; they stay allowlisted."""
    from jobbot.workspace import repo_root

    src = repo_root() / "src" / "jobbot"
    report = scan(src)
    flagged = {(f.path, f.name) for f in report.findings}
    assert ("adapters/base.py", "ApplicationPortalAdapter") not in flagged
    assert ("adapters/base.py", "JobSourceAdapter") not in flagged


def test_format_and_json_round_trip(tmp_path: Path) -> None:
    _write(tmp_path, "empty.py", "x = 1\n")
    report = scan(tmp_path)
    text = format_report(report)
    assert "over-engineering score=" in text
    payload = report_json(report)
    assert '"score"' in payload
    assert '"density_per_kloc"' in payload


def test_budget_in_range_when_all_criteria_hold(tmp_path: Path) -> None:
    _write(tmp_path, "empty.py", "x = 1\n" * 1000)  # 1 kloc-ish
    snap = _snap(tmp_path, commands=5, modules=2)
    budget = Budget(
        max_score=0,
        max_density_per_kloc=0.0,
        min_commands_per_kloc=1.0,
        max_modules_per_kloc=10.0,
    )
    verdict = check_budget(snap, budget)
    assert verdict.ok
    assert all(c.ok for c in verdict.criteria)
    assert "IN RANGE" in verdict.format()
    assert "competing criteria" in verdict.format()


def test_budget_fails_when_commands_per_kloc_too_low(tmp_path: Path) -> None:
    _write(tmp_path, "empty.py", "x = 1\n" * 2000)
    snap = _snap(tmp_path, commands=1, modules=1)
    budget = Budget(
        max_score=0,
        max_density_per_kloc=0.0,
        min_commands_per_kloc=5.0,
        max_modules_per_kloc=50.0,
    )
    verdict = check_budget(snap, budget)
    assert not verdict.ok
    assert any(c.name == "commands_per_kloc" and not c.ok for c in verdict.criteria)
    assert "capability tip" in verdict.format()


def test_budget_fails_when_module_sprawl(tmp_path: Path) -> None:
    for i in range(8):
        _write(tmp_path, f"m{i}.py", "x = 1\n")
    snap = _snap(tmp_path, commands=20, modules=8)
    budget = Budget(
        max_score=0,
        max_density_per_kloc=0.0,
        min_commands_per_kloc=0.1,
        max_modules_per_kloc=1.0,
    )
    verdict = check_budget(snap, budget)
    assert not verdict.ok
    assert any(c.name == "modules_per_kloc" and not c.ok for c in verdict.criteria)
    assert "sprawl tip" in verdict.format()


def test_budget_out_of_range_when_score_exceeds(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "ports.py",
        """
from abc import ABC, abstractmethod

class OnlyOnce(ABC):
    @abstractmethod
    def run(self) -> None: ...

class OnlyOnceImpl(OnlyOnce):
    def run(self) -> None:
        pass
""",
    )
    snap = _snap(tmp_path, commands=50, modules=1)
    verdict = check_budget(
        snap,
        Budget(
            max_score=0,
            max_density_per_kloc=0.0,
            min_commands_per_kloc=0.0,
            max_modules_per_kloc=100.0,
        ),
    )
    assert not verdict.ok
    assert any("score" in r for r in verdict.reasons)
    assert "OUT OF RANGE" in verdict.format()
    assert "quick wins" in verdict.format()


def test_load_budget_from_yaml(tmp_path: Path) -> None:
    path = tmp_path / "budget.yaml"
    path.write_text(
        "max_score: 3\nmax_density_per_kloc: 1.5\n"
        "min_commands_per_kloc: 2.0\nmax_modules_per_kloc: 5.0\n",
        encoding="utf-8",
    )
    budget = load_budget(path)
    assert budget == Budget(
        max_score=3,
        max_density_per_kloc=1.5,
        min_commands_per_kloc=2.0,
        max_modules_per_kloc=5.0,
    )


def test_committed_budget_holds_current_tree() -> None:
    """CI --check must pass on the branch that ships the gate."""
    from jobbot.ops.overengineering import BUDGET_RELPATH, measure_repo
    from jobbot.workspace import repo_root

    root = repo_root()
    snapshot = measure_repo(root)
    verdict = check_budget(snapshot, load_budget(root / BUDGET_RELPATH))
    assert verdict.ok, verdict.format()
    assert len(verdict.criteria) == 4


def test_quick_wins_prefer_same_file_collapse(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "ports.py",
        """
from abc import ABC, abstractmethod

class OnlyOnce(ABC):
    @abstractmethod
    def run(self) -> None: ...

class OnlyOnceImpl(OnlyOnce):
    def run(self) -> None:
        pass
""",
    )
    _write(
        tmp_path,
        "factory.py",
        """
class WidgetFactory:
    def build(self) -> object:
        return object()
""",
    )
    wins = quick_wins(scan(tmp_path))
    assert wins
    assert wins[0].effort == EFFORT_EASY
    assert wins[0].frees >= 2
    text = format_quick_wins(wins, deficit=3)
    assert "quick wins" in text
    assert "frees=" in text
    assert "*" in text


def test_compensation_plan_covers_deficit(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "a.py",
        """
from abc import ABC, abstractmethod

class A(ABC):
    @abstractmethod
    def run(self) -> None: ...

class AImpl(A):
    def run(self) -> None:
        pass
""",
    )
    _write(
        tmp_path,
        "b.py",
        """
class WidgetFactory:
    def build(self) -> object:
        return object()
""",
    )
    wins = quick_wins(scan(tmp_path))
    plan = compensation_plan(wins, deficit=3)
    assert plan
    assert sum(w.frees for w in plan) >= 3
