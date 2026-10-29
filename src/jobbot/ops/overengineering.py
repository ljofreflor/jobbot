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


def _subclass_counts(classes: list[_ClassInfo]) -> dict[str, int]:
    """Map simple base name → number of classes that list it as a direct base."""
    counts: dict[str, int] = defaultdict(int)
    for info in classes:
        for base in info.bases:
            if base in _ABC_BASE_NAMES:
                continue
            counts[base] += 1
    return counts


def scan(src_root: Path) -> Report:
    """Scan ``src_root`` (typically ``…/src/jobbot``) for over-engineering smells."""
    root = src_root.resolve()
    files, lines = _lines_and_files(root)
    classes = _collect_classes(root)
    children = _subclass_counts(classes)
    findings: list[Finding] = []

    for info in classes:
        key = (info.path, info.name)
        if key in _ALLOW:
            continue
        n_children = children.get(info.name, 0)

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
            lines.append(
                "Shrink the smell (preferred) or raise docs/overengineering-budget.yaml "
                "with HITL + reason in the PR."
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
    """``python -m jobbot.ops.overengineering [--json|--check] [src_root]``."""
    import sys

    args = list(sys.argv[1:] if argv is None else argv)
    as_json = False
    do_check = False
    if "--json" in args:
        as_json = True
        args.remove("--json")
    if "--check" in args:
        do_check = True
        args.remove("--check")
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
    sys.stdout.write(report_json(report) if as_json else format_report(report) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
