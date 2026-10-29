"""Over-engineering metric — detect premature abstraction smells in ``src/jobbot``.

Complements AGENTS.md *Against over-engineering*. Score = weighted smell count;
density = score per thousand lines scanned. Every PR must keep the metric
**in range** against ``docs/overengineering-budget.yaml`` (CI ``--check``).
Raising the budget is HITL. Local scan, no network. Prefer shrinking code over
adding detector rules.
"""

from __future__ import annotations

import ast
import json
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

BUDGET_RELPATH = "docs/overengineering-budget.yaml"

# Kinds mirror the AGENTS.md smell checklist (subset that AST can see cheaply).
KIND_SINGLE_ABC = "single_implementor_abc"
KIND_SINGLE_BASE = "single_subclass_base"
KIND_LONE_STRATEGY = "lone_strategy"
KIND_LONE_FACTORY = "lone_factory"

_WEIGHTS: dict[str, int] = {
    KIND_SINGLE_ABC: 3,
    KIND_SINGLE_BASE: 2,
    KIND_LONE_STRATEGY: 2,
    KIND_LONE_FACTORY: 2,
}

# Known ports / ABCs that are the *point* of hexagonal adapters (fan-out is
# external). Listed so the metric does not punish the architecture itself.
_ALLOW: frozenset[tuple[str, str]] = frozenset(
    {
        ("adapters/base.py", "ApplicationPortalAdapter"),
        ("adapters/base.py", "JobSourceAdapter"),
        ("adapters/base.py", "ProfileAdapter"),
        ("adapters/base.py", "WritableProfileAdapter"),
        ("jobs/sources.py", "JobSource"),
        ("jobs/sources.py", "JobSourceAdapter"),
        ("jobs/discover.py", "DiscoverAdapter"),
    }
)

# Duck-typed seams (Playwright/HTTP) — Protocol with no in-tree subclass is intentional.
_STRUCTURAL_SUFFIXES = ("Like", "Protocol")

_ABC_BASE_NAMES = frozenset({"ABC", "ABCMeta", "Protocol"})
_BASE_SUFFIXES = ("Base", "Abstract")


@dataclass(frozen=True)
class Finding:
    kind: str
    path: str  # posix path relative to src/jobbot
    name: str
    detail: str
    weight: int = 1
    child_path: str | None = None
    child_name: str | None = None


EFFORT_EASY = "easy"
EFFORT_MEDIUM = "medium"


@dataclass(frozen=True)
class QuickWin:
    """A concrete refactor that frees budget weight (compensate the range)."""

    finding: Finding
    effort: str  # easy | medium
    action: str
    frees: int  # score points recovered if done

    @property
    def same_file(self) -> bool:
        child = self.finding.child_path
        return child is not None and child == self.finding.path


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    files_scanned: int = 0
    lines_scanned: int = 0

    @property
    def score(self) -> int:
        return sum(f.weight for f in self.findings)

    @property
    def density(self) -> float:
        """Weighted smells per 1000 lines (0 if empty tree)."""
        if self.lines_scanned <= 0:
            return 0.0
        return round(1000.0 * self.score / self.lines_scanned, 2)

    def by_kind(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for f in self.findings:
            counts[f.kind] += 1
        return dict(sorted(counts.items()))

    def to_dict(self) -> dict[str, object]:
        return {
            "score": self.score,
            "density_per_kloc": self.density,
            "files_scanned": self.files_scanned,
            "lines_scanned": self.lines_scanned,
            "by_kind": self.by_kind(),
            "findings": [asdict(f) for f in self.findings],
        }


@dataclass
class _ClassInfo:
    name: str
    path: str
    bases: tuple[str, ...]
    is_abc: bool
    abstract_methods: int


def _base_names(node: ast.ClassDef) -> tuple[str, ...]:
    names: list[str] = []
    for base in node.bases:
        if isinstance(base, ast.Name):
            names.append(base.id)
        elif isinstance(base, ast.Attribute):
            names.append(base.attr)
    return tuple(names)


def _is_abstract_method(node: ast.AST) -> bool:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name) and dec.id == "abstractmethod":
            return True
        if isinstance(dec, ast.Attribute) and dec.attr == "abstractmethod":
            return True
    return False


def _collect_classes(root: Path) -> list[_ClassInfo]:
    classes: list[_ClassInfo] = []
    for path in sorted(root.rglob("*.py")):
        if path.name == "__pycache__":
            continue
        rel = path.relative_to(root).as_posix()
        try:
            source = path.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            bases = _base_names(node)
            is_abc = any(b in _ABC_BASE_NAMES for b in bases)
            abstracts = sum(1 for child in node.body if _is_abstract_method(child))
            if abstracts:
                is_abc = True
            classes.append(
                _ClassInfo(
                    name=node.name,
                    path=rel,
                    bases=bases,
                    is_abc=is_abc,
                    abstract_methods=abstracts,
                )
            )
    return classes


def _lines_and_files(root: Path) -> tuple[int, int]:
    files = 0
    lines = 0
    for path in root.rglob("*.py"):
        files += 1
        try:
            lines += len(path.read_text(encoding="utf-8").splitlines())
        except OSError:
            continue
    return files, lines


def _subclass_index(classes: list[_ClassInfo]) -> dict[str, list[_ClassInfo]]:
    """Map simple base name → direct subclasses (may collide across modules)."""
    index: dict[str, list[_ClassInfo]] = defaultdict(list)
    for info in classes:
        for base in info.bases:
            if base in _ABC_BASE_NAMES:
                continue
            index[base].append(info)
    return index


def _child_ref(subs: list[_ClassInfo]) -> tuple[str | None, str | None]:
    if len(subs) != 1:
        return None, None
    only = subs[0]
    return only.path, only.name


def scan(src_root: Path) -> Report:
    """Scan ``src_root`` (typically ``…/src/jobbot``) for over-engineering smells."""
    root = src_root.resolve()
    files, lines = _lines_and_files(root)
    classes = _collect_classes(root)
    by_base = _subclass_index(classes)
    findings: list[Finding] = []

    for info in classes:
        key = (info.path, info.name)
        if key in _ALLOW:
            continue
        subs = by_base.get(info.name, [])
        n_children = len(subs)
        child_path, child_name = _child_ref(subs)

        is_protocol = "Protocol" in info.bases or info.name.endswith(_STRUCTURAL_SUFFIXES)
        if info.is_abc and not (is_protocol and n_children == 0):
            # Checklist: "ABC with one implementor". Pure Protocol/*Like seams with no
            # in-tree subclass are typing, not speculative hierarchy. Zero children on a
            # named Adapter/Base/… still smells.
            extension_name = (
                info.name.endswith(("Adapter", "Base", "Abstract", "Strategy", "Factory"))
                or info.name.startswith("Abstract")
            )
            if n_children == 1 or (n_children == 0 and extension_name and not is_protocol):
                findings.append(
                    Finding(
                        kind=KIND_SINGLE_ABC,
                        path=info.path,
                        name=info.name,
                        detail=f"{n_children} concrete subclass(es) in tree",
                        weight=_WEIGHTS[KIND_SINGLE_ABC],
                        child_path=child_path,
                        child_name=child_name,
                    )
                )
        elif (
            n_children == 1
            and not info.is_abc
            and (
                info.name.endswith(_BASE_SUFFIXES)
                or info.name.startswith("Abstract")
                or info.name.endswith("Interface")
            )
        ):
            findings.append(
                Finding(
                    kind=KIND_SINGLE_BASE,
                    path=info.path,
                    name=info.name,
                    detail="one subclass of a *Base/*Abstract type",
                    weight=_WEIGHTS[KIND_SINGLE_BASE],
                    child_path=child_path,
                    child_name=child_name,
                )
            )

        if (
            info.name.endswith("Strategy")
            and n_children <= 1
            and (info.is_abc or n_children == 0)
        ):
            findings.append(
                Finding(
                    kind=KIND_LONE_STRATEGY,
                    path=info.path,
                    name=info.name,
                    detail="Strategy with no sibling variants in tree",
                    weight=_WEIGHTS[KIND_LONE_STRATEGY],
                    child_path=child_path,
                    child_name=child_name,
                )
            )

        if info.name.endswith("Factory") and n_children == 0 and not info.is_abc:
            findings.append(
                Finding(
                    kind=KIND_LONE_FACTORY,
                    path=info.path,
                    name=info.name,
                    detail="Factory class with no subclass fan-out (likely one product)",
                    weight=_WEIGHTS[KIND_LONE_FACTORY],
                )
            )

    findings.sort(key=lambda f: (f.kind, f.path, f.name))
    return Report(findings=findings, files_scanned=files, lines_scanned=lines)


def _action_for(finding: Finding) -> tuple[str, str]:
    """Return (effort, action) for a finding."""
    same = finding.child_path is not None and finding.child_path == finding.path
    if finding.kind == KIND_SINGLE_ABC:
        if finding.child_name and same:
            return (
                EFFORT_EASY,
                f"collapse {finding.name} + {finding.child_name} into one concrete type "
                f"in {finding.path}",
            )
        if finding.child_name:
            return (
                EFFORT_MEDIUM,
                f"inline {finding.name} into {finding.child_path}::{finding.child_name} "
                f"or drop the ABC until a second implementor exists",
            )
        return (
            EFFORT_EASY,
            f"delete unused extension point {finding.path}::{finding.name} "
            f"(zero implementors)",
        )
    if finding.kind == KIND_SINGLE_BASE:
        if finding.child_name and same:
            return (
                EFFORT_EASY,
                f"merge {finding.name} into {finding.child_name} in {finding.path}",
            )
        return (
            EFFORT_MEDIUM,
            f"fold {finding.name} into its only subclass "
            f"{finding.child_path}::{finding.child_name}",
        )
    if finding.kind == KIND_LONE_STRATEGY:
        return (
            EFFORT_EASY,
            f"replace {finding.path}::{finding.name} with a function until a second "
            f"strategy appears",
        )
    if finding.kind == KIND_LONE_FACTORY:
        return (
            EFFORT_EASY,
            f"replace {finding.path}::{finding.name} with a constructor/helper "
            f"(one product type)",
        )
    return (EFFORT_MEDIUM, f"remove or simplify {finding.path}::{finding.name}")


def quick_wins(report: Report) -> list[QuickWin]:
    """Rank refactors that free score — easy same-file collapses first."""
    wins: list[QuickWin] = []
    for finding in report.findings:
        effort, action = _action_for(finding)
        wins.append(
            QuickWin(
                finding=finding,
                effort=effort,
                action=action,
                frees=finding.weight,
            )
        )
    effort_rank = {EFFORT_EASY: 0, EFFORT_MEDIUM: 1}
    wins.sort(
        key=lambda w: (
            effort_rank.get(w.effort, 9),
            -w.frees,
            w.finding.path,
            w.finding.name,
        )
    )
    return wins


def compensation_plan(
    wins: list[QuickWin], *, deficit: int
) -> list[QuickWin]:
    """Greedy easy-first set whose ``frees`` sum covers ``deficit`` (0 → empty)."""
    if deficit <= 0:
        return []
    picked: list[QuickWin] = []
    freed = 0
    for win in wins:
        picked.append(win)
        freed += win.frees
        if freed >= deficit:
            break
    return picked


def format_quick_wins(
    wins: list[QuickWin],
    *,
    deficit: int = 0,
    limit: int = 20,
) -> str:
    if not wins:
        return "quick wins: none (no smells to shrink — headroom is the budget itself)"
    lines = ["quick wins (refactor to free budget / compensate the range):"]
    plan = compensation_plan(wins, deficit=deficit) if deficit > 0 else []
    plan_keys = {(w.finding.path, w.finding.name) for w in plan}
    if deficit > 0 and plan:
        freed = sum(w.frees for w in plan)
        lines.append(
            f"  compensation for deficit={deficit}: "
            f"do {len(plan)} win(s) freeing ≥{freed}"
        )
    for win in wins[:limit]:
        mark = "*" if (win.finding.path, win.finding.name) in plan_keys else " "
        lines.append(
            f"  {mark}[{win.effort} frees={win.frees}] "
            f"{win.finding.path}::{win.finding.name} — {win.action}"
        )
    if len(wins) > limit:
        lines.append(f"  … +{len(wins) - limit} more")
    if plan_keys:
        lines.append("  (* = minimum set to cover the score deficit)")
    return "\n".join(lines)


def format_report(report: Report, *, limit: int = 40) -> str:
    """Human-readable summary for the terminal."""
    lines = [
        f"over-engineering score={report.score}  "
        f"density={report.density}/kloc  "
        f"files={report.files_scanned}  lines={report.lines_scanned}",
        f"by_kind={report.by_kind() or '{}'}",
    ]
    if not report.findings:
        lines.append("no smells flagged (heuristic; not a proof of simplicity)")
        return "\n".join(lines)
    lines.append("findings:")
    for finding in report.findings[:limit]:
        lines.append(
            f"  [{finding.kind} w={finding.weight}] "
            f"{finding.path}::{finding.name} — {finding.detail}"
        )
    if len(report.findings) > limit:
        lines.append(f"  … +{len(report.findings) - limit} more")
    return "\n".join(lines)


def report_json(report: Report) -> str:
    return json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n"


@dataclass(frozen=True)
class Budget:
    """Ceiling every PR must stay under (committed budget file)."""

    max_score: int
    max_density_per_kloc: float


@dataclass(frozen=True)
class BudgetVerdict:
    ok: bool
    report: Report
    budget: Budget
    reasons: tuple[str, ...]

    def format(self) -> str:
        status = "IN RANGE" if self.ok else "OUT OF RANGE"
        lines = [
            f"over-engineering budget: {status}",
            f"  score {self.report.score} / max {self.budget.max_score}",
            f"  density {self.report.density}/kloc / max {self.budget.max_density_per_kloc}",
        ]
        lines.extend(f"  ! {reason}" for reason in self.reasons)
        if not self.ok:
            deficit = max(0, self.report.score - self.budget.max_score)
            lines.append(
                "Shrink via quick wins (preferred) or raise "
                "docs/overengineering-budget.yaml with HITL + reason in the PR."
            )
            lines.append(
                format_quick_wins(
                    quick_wins(self.report),
                    deficit=deficit,
                )
            )
        return "\n".join(lines)


def load_budget(path: Path) -> Budget:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"budget must be a mapping: {path}")
    try:
        max_score = int(raw["max_score"])
        max_density = float(raw["max_density_per_kloc"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"budget needs max_score + max_density_per_kloc: {path}") from exc
    if max_score < 0 or max_density < 0:
        raise ValueError(f"budget ceilings must be ≥ 0: {path}")
    return Budget(max_score=max_score, max_density_per_kloc=max_density)


def check_budget(report: Report, budget: Budget) -> BudgetVerdict:
    reasons: list[str] = []
    if report.score > budget.max_score:
        reasons.append(
            f"score {report.score} exceeds max_score {budget.max_score}"
        )
    if report.density > budget.max_density_per_kloc:
        reasons.append(
            f"density {report.density}/kloc exceeds "
            f"max_density_per_kloc {budget.max_density_per_kloc}"
        )
    return BudgetVerdict(
        ok=not reasons,
        report=report,
        budget=budget,
        reasons=tuple(reasons),
    )


def main(argv: list[str] | None = None) -> int:
    """``python -m jobbot.ops.overengineering [--json|--check|--quick-wins] [src_root]``."""
    import sys

    args = list(sys.argv[1:] if argv is None else argv)
    as_json = False
    do_check = False
    show_wins = False
    if "--json" in args:
        as_json = True
        args.remove("--json")
    if "--check" in args:
        do_check = True
        args.remove("--check")
    if "--quick-wins" in args:
        show_wins = True
        args.remove("--quick-wins")
    # __file__ = …/src/jobbot/ops/overengineering.py → package=parents[1], repo=parents[3]
    package_root = Path(__file__).resolve().parents[1]
    repo_root = Path(__file__).resolve().parents[3]
    root = Path(args[0]) if args else package_root
    report = scan(root)
    if do_check:
        budget_path = repo_root / BUDGET_RELPATH
        if args:
            # Alternate package tree: budget lives at <repo>/docs/… next to src/.
            candidate = root.parent.parent / BUDGET_RELPATH
            if candidate.is_file():
                budget_path = candidate
        verdict = check_budget(report, load_budget(budget_path))
        sys.stdout.write(verdict.format() + "\n")
        if not verdict.ok:
            sys.stdout.write(format_report(report) + "\n")
        return 0 if verdict.ok else 1
    if as_json:
        payload = report.to_dict()
        payload["quick_wins"] = [
            {
                "effort": w.effort,
                "frees": w.frees,
                "action": w.action,
                "path": w.finding.path,
                "name": w.finding.name,
                "kind": w.finding.kind,
            }
            for w in quick_wins(report)
        ]
        sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        return 0
    sys.stdout.write(format_report(report) + "\n")
    if show_wins or report.findings:
        deficit = 0
        budget_path = repo_root / BUDGET_RELPATH
        if budget_path.is_file():
            budget = load_budget(budget_path)
            deficit = max(0, report.score - budget.max_score)
        sys.stdout.write(
            format_quick_wins(quick_wins(report), deficit=deficit) + "\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
