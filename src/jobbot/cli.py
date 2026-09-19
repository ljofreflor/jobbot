"""CLI entrypoint for JobBot."""

from __future__ import annotations

import json
import logging
import re
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy.orm import Session

from jobbot import __version__
from jobbot.applications.manager import (
    ApplicationRepository,
    prepare_application_package,
)
from jobbot.companies.models import DiscoverySource
from jobbot.companies.registry import CompanyRegistry
from jobbot.config import JobbotConfig, load_config
from jobbot.cv.build import BuildTarget, build_cv
from jobbot.cv.renderer import CvStyle
from jobbot.db.engine import make_engine, make_session_factory
from jobbot.exit_codes import (
    AUTH_REQUIRED,
    GENERIC_FAILURE,
    MANUAL_CHALLENGE,
    SUCCESS,
    VALIDATION_FAILURE,
)
from jobbot.jobs.freshness import age_label, is_fresh
from jobbot.jobs.geo import detect_country, resolve_countries
from jobbot.jobs.repository import JobRepository, write_job_json
from jobbot.matching.analyzer import RuleBasedJobAnalyzer
from jobbot.matching.scoring import format_match_report
from jobbot.models.application import ApplicationStatus
from jobbot.models.candidate import Candidate
from jobbot.models.job import JobPosting
from jobbot.ops.narrate import ExplorationOutcome, Narrator, Phase
from jobbot.profile.diff import compare_summaries, summarize_profile
from jobbot.profile.importer_common import write_generated_profile
from jobbot.profile.importer_latex import LatexImportError, import_latex_cv
from jobbot.profile.importer_pdf import PdfImportError, import_pdf_cv
from jobbot.profile.loader import ProfileLoadError, load_profile, load_profile_raw
from jobbot.profile.validator import validate_candidate
from jobbot.workspace import (
    DEFAULT_LABEL,
    STAMP_NAME,
    WorkspaceOwnerError,
    active_workspace,
    list_workspaces,
    read_stamp,
    resolve_root,
    sandboxes_dir,
    set_active_workspace,
    workspace_root,
)
from jobbot.workspace import adopt as adopt_workspace

app = typer.Typer(
    name="jobbot",
    help="Local terminal tool for job search and structured CV management.",
    no_args_is_help=True,
)
profile_app = typer.Typer(help="Candidate profile operations", no_args_is_help=True)
cv_app = typer.Typer(help="Build CV variants", no_args_is_help=True)
jobs_app = typer.Typer(help="Search and inspect jobs", no_args_is_help=True)
application_app = typer.Typer(help="Prepare or open one application", no_args_is_help=True)
applications_app = typer.Typer(help="Track applications", no_args_is_help=True)
indeed_app = typer.Typer(help="Indeed profile operations", no_args_is_help=True)
linkedin_app = typer.Typer(
    help="LinkedIn: audit, publications sync, recruiter-post sweep",
    no_args_is_help=True,
)
browser_app = typer.Typer(
    help="Browser helpers (HITL Chrome / CDP — no CAPTCHA bypass)",
    no_args_is_help=True,
)
getonboard_app = typer.Typer(
    help="Get on Board: perfil/CVs HITL + job discovery (LATAM)",
    no_args_is_help=True,
)
torre_app = typer.Typer(help="Torre: job discovery (LATAM / remoto)", no_args_is_help=True)
portals_app = typer.Typer(help="Recruitment portal registry (ATS)", no_args_is_help=True)
companies_app = typer.Typer(
    help="Company ↔ career platform knowledge (candidate → promote; public data only)",
    no_args_is_help=True,
)
recruiters_app = typer.Typer(
    help="Public hiring practice that feeds cv advise (practices only, never people)",
    no_args_is_help=True,
)
ops_app = typer.Typer(
    help="Local ops: failure observability + continuous loops (no telemetry)",
    no_args_is_help=True,
)
ops_failure_app = typer.Typer(help="Inspect / triage stored failures", no_args_is_help=True)
workspace_app = typer.Typer(
    help="Isolated homes for extra candidates (test CVs) in this checkout",
    no_args_is_help=True,
)

app.add_typer(workspace_app, name="workspace")
app.add_typer(profile_app, name="profile")
app.add_typer(cv_app, name="cv")
app.add_typer(jobs_app, name="jobs")
app.add_typer(application_app, name="application")
app.add_typer(applications_app, name="applications")
app.add_typer(indeed_app, name="indeed")
app.add_typer(linkedin_app, name="linkedin")
app.add_typer(getonboard_app, name="getonboard")
app.add_typer(torre_app, name="torre")
app.add_typer(browser_app, name="browser")
app.add_typer(portals_app, name="portals")
app.add_typer(companies_app, name="companies")
app.add_typer(recruiters_app, name="recruiters")
app.add_typer(ops_app, name="ops")
ops_app.add_typer(ops_failure_app, name="failure")

console = Console()
err_console = Console(stderr=True)


def run_cli(
    argv: Sequence[str] | None = None,
    *,
    prog_name: str = "jobbot",
    standalone_mode: bool = True,
) -> int:
    """Invoke the Typer app and persist non-zero exits as local ops failures."""
    args = list(sys.argv[1:] if argv is None else argv)
    exit_code = SUCCESS
    caught: BaseException | None = None
    aborted = False
    try:
        result = app(args, prog_name=prog_name, standalone_mode=False)
        if isinstance(result, int):
            exit_code = result
    except typer.Exit as exc:
        exit_code = int(exc.exit_code)
        caught = exc
    except typer.Abort:
        exit_code = GENERIC_FAILURE
        caught = None
        aborted = True
    except WorkspaceOwnerError as exc:
        # Pointing a profile at somebody else's data is a wrong invocation, not a bug:
        # report it and stop, without recording an ops failure or writing anything.
        err_console.print(f"[bold red]Wrong workspace[/bold red]\n{exc}")
        if standalone_mode:
            raise SystemExit(VALIDATION_FAILURE) from exc
        return VALIDATION_FAILURE
    except Exception as exc:  # noqa: BLE001 — CLI boundary capture
        exit_code = GENERIC_FAILURE
        caught = exc
        err_console.print(f"[red]Unhandled error:[/red] {exc}")

    if exit_code != SUCCESS:
        from jobbot.ops.failures import ABORT_MESSAGE, capture_cli_failure, runtime_context

        record = capture_cli_failure(
            exit_code,
            argv=["jobbot", *args],
            exc=caught if not isinstance(caught, typer.Exit) else None,
            error_class="Abort" if aborted else None,
            message=ABORT_MESSAGE if aborted else None,
            context=runtime_context(),
        )
        if record is not None:
            err_console.print(
                f"[yellow]Recorded failure[/yellow] {record.id} "
                f"(fingerprint={record.fingerprint})"
            )

    if standalone_mode:
        raise SystemExit(exit_code)
    return exit_code


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-5s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _session() -> tuple[Session, JobbotConfig]:
    config = load_config()
    engine = make_engine(config.database_path)
    return make_session_factory(engine)(), config


@app.callback()
def main(
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Enable debug logging"),
    ] = False,
    workspace: Annotated[
        str | None,
        typer.Option(
            "--workspace",
            "-w",
            help="Run against another candidate's workspace (see `jobbot workspace list`)",
        ),
    ] = None,
) -> None:
    """JobBot CLI."""
    _setup_logging(verbose)
    set_active_workspace(workspace)
    if workspace is not None:
        console.print(f"[yellow]workspace:[/yellow] {workspace} ({workspace_root(workspace)})")


@app.command("version")
def version_cmd() -> None:
    """Show JobBot version."""
    console.print(__version__)


# ── workspace ────────────────────────────────────────────────────────────────


@workspace_app.command("list")
def workspace_list() -> None:
    """List the extra candidates living in this checkout."""
    names = list_workspaces()
    if not names:
        console.print(f"No workspaces yet in {sandboxes_dir()} — create one with `workspace new`.")
        return
    table = Table(title="Workspaces")
    table.add_column("name")
    table.add_column("profile")
    table.add_column("owner")
    for name in names:
        root = workspace_root(name)
        profile = root / "data" / "profile.yaml"
        stamp = read_stamp(root / "data" / STAMP_NAME)
        table.add_row(
            name,
            "yes" if profile.is_file() else "missing",
            stamp.fingerprint if stamp else "unstamped",
        )
    console.print(table)


@workspace_app.command("new")
def workspace_new(
    name: Annotated[str, typer.Argument(help="Workspace name, e.g. a test CV's nickname")],
) -> None:
    """Create an isolated `data/` + `output/` for another candidate."""
    root = workspace_root(name)
    if root.exists():
        err_console.print(f"Workspace already exists: {root}")
        raise typer.Exit(GENERIC_FAILURE)
    (root / "data").mkdir(parents=True)
    (root / "output").mkdir(parents=True)
    console.print(f"Created {root}")
    console.print(f"Now put the candidate's profile in {root / 'data' / 'profile.yaml'}")
    console.print(f"and run commands with [bold]--workspace {name}[/bold].")


@workspace_app.command("show")
def workspace_show() -> None:
    """Show which candidate the current run would touch."""
    name = active_workspace()
    config = load_config()
    table = Table(title="Active workspace")
    table.add_column("field")
    table.add_column("value")
    table.add_row("workspace", name or "default (current directory)")
    table.add_row("profile", str(config.profile_path))
    table.add_row("output", str(config.output_dir))
    table.add_row("database", str(config.database_path))
    stamp = read_stamp(config.profile_path.parent / STAMP_NAME)
    table.add_row("owner", stamp.fingerprint if stamp else "unstamped")
    console.print(table)


@workspace_app.command("adopt")
def workspace_adopt(
    yes: Annotated[bool, typer.Option("--yes", help="Skip the confirmation")] = False,
) -> None:
    """Hand this workspace's data and output over to the profile now in place."""
    name = active_workspace()
    base, _ = resolve_root(Path.cwd())
    profile_path = base / "data" / "profile.yaml"
    output_dir = base / "output"
    console.print(f"Re-stamp {profile_path.parent} and {output_dir} for {profile_path}")
    if not yes and not typer.confirm("Artifacts of the previous owner stay in place. Continue?"):
        raise typer.Abort
    fingerprint = adopt_workspace(profile_path, output_dir, label=name or DEFAULT_LABEL)
    if fingerprint is None:
        err_console.print(f"No profile with a name at {profile_path}")
        raise typer.Exit(GENERIC_FAILURE)
    console.print(f"Owner is now {fingerprint}")


# ── profile ──────────────────────────────────────────────────────────────────


@profile_app.command("validate")
def profile_validate() -> None:
    """Validate data/profile.yaml."""
    config = load_config()
    try:
        candidate = load_profile(config.profile_path)
    except ProfileLoadError as exc:
        err_console.print("[bold red]PROFILE INVALID[/bold red]")
        err_console.print(str(exc))
        raise typer.Exit(VALIDATION_FAILURE) from exc

    result = validate_candidate(candidate)
    if not result.ok:
        err_console.print("[bold red]PROFILE INVALID[/bold red]")
        for issue in result.issues:
            err_console.print(str(issue))
        raise typer.Exit(VALIDATION_FAILURE)

    console.print("[bold green]PROFILE VALID[/bold green]")
    console.print(f"Experiences: {len(candidate.experience)}")
    console.print(f"Achievements: {candidate.achievement_count()}")
    console.print(f"Skills: {candidate.skills.count()}")
    console.print(f"Publications: {len(candidate.publications)}")
    raise typer.Exit(SUCCESS)


@profile_app.command("show")
def profile_show() -> None:
    """Show a summary of the local profile."""
    config = load_config()
    try:
        candidate = load_profile(config.profile_path)
    except ProfileLoadError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(VALIDATION_FAILURE) from exc

    personal = candidate.personal
    table = Table(title="Candidate profile", show_header=False)
    table.add_column("Field", style="cyan")
    table.add_column("Value")
    table.add_row("Name", personal.name)
    table.add_row("Headline", personal.headline)
    table.add_row("Location", personal.location_line() or "—")
    table.add_row("Email", str(personal.email) if personal.email else "—")
    table.add_row("Experiences", str(len(candidate.experience)))
    table.add_row("Skills", str(candidate.skills.count()))
    console.print(table)
    if candidate.summary:
        console.print(Panel(candidate.summary.strip(), title="Summary"))


@profile_app.command("import-latex")
def profile_import_latex(
    tex_path: Annotated[
        Path | None,
        typer.Argument(help="Path to legacy moderncv .tex"),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Destination YAML"),
    ] = None,
) -> None:
    """Import a legacy LaTeX CV into profile.generated.yaml."""
    config = load_config()
    source = tex_path or config.legacy_cv_path
    if source is None:
        err_console.print(
            "[red]Provide a .tex path or set paths.legacy_cv in .jobbot.toml[/red]"
        )
        raise typer.Exit(GENERIC_FAILURE)

    source = source.expanduser().resolve()
    destination = (output or config.generated_profile_path).expanduser().resolve()

    try:
        result = import_latex_cv(source)
        write_generated_profile(result, destination)
    except LatexImportError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(GENERIC_FAILURE) from exc

    console.print("[bold green]LEGACY CV IMPORTED[/bold green]")
    console.print(f"Source:  {source}")
    console.print(f"Wrote:   {destination}")
    console.print(f"Experiences: {result.experience_count}")
    console.print(f"Achievements: {result.achievement_count}")
    console.print(f"Skills: {result.skill_count}")
    console.print(f"Publications: {len(result.data.get('publications', []))}")

    if result.warnings:
        console.print("\n[yellow]Warnings[/yellow]")
        for warning in result.warnings:
            console.print(f"- {warning}")

    if config.profile_path.is_file():
        try:
            local_raw = load_profile_raw(config.profile_path)
            lines = compare_summaries(
                summarize_profile(local_raw),
                summarize_profile(result.data),
            )
            console.print("\n[bold]Comparison vs data/profile.yaml[/bold]")
            for line in lines:
                console.print(line)
        except ProfileLoadError:
            pass

    console.print(
        Panel(
            "Review the generated YAML, then:\n"
            "  jobbot profile promote-generated\n"
            "  jobbot profile validate",
            title="Next steps",
        )
    )


@profile_app.command("import-pdf")
def profile_import_pdf(
    pdf_path: Annotated[
        Path,
        typer.Argument(help="Path to a CV exported as PDF (needs a text layer)"),
    ],
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Destination YAML"),
    ] = None,
) -> None:
    """Import a PDF CV into profile.generated.yaml."""
    config = load_config()
    source = pdf_path.expanduser().resolve()
    destination = (output or config.generated_profile_path).expanduser().resolve()

    try:
        result = import_pdf_cv(source)
        write_generated_profile(result, destination, command="profile import-pdf")
    except PdfImportError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(GENERIC_FAILURE) from exc

    console.print("[bold green]PDF CV IMPORTED[/bold green]")
    console.print(f"Source:  {source}")
    console.print(f"Wrote:   {destination}")
    console.print(f"Experiences: {result.experience_count}")
    console.print(f"Achievements: {result.achievement_count}")
    console.print(f"Skills: {result.skill_count}")
    console.print(f"Education: {len(result.data.get('education', []))}")

    if result.warnings:
        console.print("\n[yellow]Warnings[/yellow]")
        for warning in result.warnings:
            console.print(f"- {warning}")

    console.print(
        Panel(
            "A PDF carries no structure, so every field is a guess.\n"
            "Review the generated YAML, then:\n"
            "  jobbot profile promote-generated\n"
            "  jobbot profile validate",
            title="Next steps",
        )
    )


@profile_app.command("promote-generated")
def profile_promote_generated(
    yes: Annotated[bool, typer.Option("--yes", "-y")] = False,
) -> None:
    """Copy profile.generated.yaml → profile.yaml after confirmation."""
    config = load_config()
    generated = config.generated_profile_path
    target = config.profile_path
    if not generated.is_file():
        err_console.print(f"[red]Generated profile not found: {generated}[/red]")
        raise typer.Exit(GENERIC_FAILURE)

    try:
        candidate = load_profile(generated)
    except ProfileLoadError as exc:
        err_console.print("[bold red]GENERATED PROFILE INVALID[/bold red]")
        err_console.print(str(exc))
        raise typer.Exit(VALIDATION_FAILURE) from exc

    result = validate_candidate(candidate)
    if not result.ok:
        err_console.print("[bold red]GENERATED PROFILE INVALID[/bold red]")
        for issue in result.issues:
            err_console.print(str(issue))
        raise typer.Exit(VALIDATION_FAILURE)

    if target.is_file() and not yes:
        console.print(f"This will overwrite [bold]{target}[/bold] with {generated}")
        if not typer.confirm("Promote generated profile?", default=False):
            console.print("Aborted.")
            raise typer.Exit(SUCCESS)

    if target.is_file():
        backup = target.with_suffix(target.suffix + ".bak")
        shutil.copy2(target, backup)
        console.print(f"Backup: {backup}")

    shutil.copy2(generated, target)
    console.print(f"[green]Promoted[/green] {generated} → {target}")


@profile_app.command("suggest-from-market")
def profile_suggest_from_market(
    min_count: Annotated[
        int,
        typer.Option("--min-count", help="Min JD occurrences for a market term"),
    ] = 2,
    ask: Annotated[
        bool,
        typer.Option("--ask/--no-ask", help="Interactively confirm suspected gaps"),
    ] = True,
    promote: Annotated[
        bool,
        typer.Option(
            "--promote",
            help="Write confirmed skills into profile.yaml (after confirmation)",
        ),
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y")] = False,
) -> None:
    """Suggest baseline wording from stored JDs; ask before adding missing skills."""
    from jobbot.profile.loader import load_profile_raw
    from jobbot.profile.market import (
        merge_confirmed_skills_into_raw,
        render_suggestion_markdown,
        suggest_from_market,
    )

    session, config = _session()
    try:
        candidate = load_profile(config.profile_path)
        raw_profile = load_profile_raw(config.profile_path)
    except ProfileLoadError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(VALIDATION_FAILURE) from exc

    jobs = JobRepository(session).list_all()
    if not jobs:
        console.print("No stored jobs. Run jobs search or linkedin sweep first.")
        raise typer.Exit(SUCCESS)

    narrator = _narrator()
    narrator.phase(Phase.RECEIVING_WORLD, f"{len(jobs)} job descriptions", may_ask=ask)
    suggestion = suggest_from_market(candidate, jobs, min_count=min_count)
    out = config.output_dir / "profile_market_suggestion.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_suggestion_markdown(suggestion), encoding="utf-8")
    console.print(f"[green]Wrote[/green] {out}")
    for gap in suggestion.missing_suspected[:15]:
        console.print(f"  gap? {gap.term} — {gap.reason}")

    confirmed: list[str] = []
    if ask and suggestion.missing_suspected:
        console.print(
            "\nConfirm skills you [bold]actually have[/bold] (never invent):"
        )
        for gap in suggestion.missing_suspected:
            if typer.confirm(f"Add skill to baseline: {gap.term}?", default=False):
                confirmed.append(gap.term)

    suggested_path = config.root / "data" / "profile.suggested.yaml"
    suggested_raw = merge_confirmed_skills_into_raw(raw_profile, confirmed)
    suggested_path.write_text(
        yaml.safe_dump(suggested_raw, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    console.print(f"Suggested profile: {suggested_path}")
    if confirmed:
        console.print(f"Confirmed new skills: {', '.join(confirmed)}")
    else:
        console.print("No new skills confirmed.")

    if not promote:
        console.print(
            "Review the markdown + suggested YAML. "
            "Re-run with [bold]--promote[/bold] to copy into profile.yaml."
        )
        return
    if not confirmed and not yes:
        console.print("Nothing confirmed to promote.")
        return
    if not yes and not typer.confirm(
        f"Promote confirmed skills into {config.profile_path}?",
        default=False,
    ):
        console.print("Aborted.")
        raise typer.Exit(SUCCESS)
    backup = config.profile_path.with_suffix(config.profile_path.suffix + ".bak")
    shutil.copy2(config.profile_path, backup)
    shutil.copy2(suggested_path, config.profile_path)
    console.print(f"Backup: {backup}")
    console.print(f"[green]Promoted[/green] confirmed market skills → {config.profile_path}")


@profile_app.command("status")
def profile_status(
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show local vs portal consistency (snapshots if available)."""
    from jobbot.adapters.portal_status import build_profile_status

    config = load_config()
    status = build_profile_status(config)
    if as_json:
        console.print_json(data=status)
        return
    table = Table(title="PROFILE CONSISTENCY")
    table.add_column("")
    table.add_column("Local")
    table.add_column("Indeed")
    table.add_column("LinkedIn")
    for row in status["rows"]:
        table.add_row(row["section"], row["local"], row["indeed"], row["linkedin"])
    console.print(table)


@profile_app.command("diff")
def profile_diff(
    target: Annotated[
        str | None,
        typer.Option("--target", help="indeed | linkedin"),
    ] = None,
    all_targets: Annotated[bool, typer.Option("--all")] = False,
    section: Annotated[str | None, typer.Option("--section")] = None,
) -> None:
    """Diff local profile against portal snapshots."""
    from jobbot.adapters.diff_engine import render_profile_diff

    config = load_config()
    targets: list[str]
    if all_targets:
        targets = ["indeed", "linkedin"]
    elif target:
        targets = [target]
    else:
        err_console.print("Provide --target or --all")
        raise typer.Exit(GENERIC_FAILURE)

    try:
        candidate = load_profile(config.profile_path)
    except ProfileLoadError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(VALIDATION_FAILURE) from exc

    for name in targets:
        text = render_profile_diff(candidate, config.output_dir, name, section=section)
        console.print(text)


# ── cv ───────────────────────────────────────────────────────────────────────


@cv_app.command("build")
def cv_build(
    target: Annotated[
        BuildTarget,
        typer.Option("--target", help="cv (PDF) or ats"),
    ] = BuildTarget.CV,
    job_id: Annotated[
        str | None,
        typer.Option("--job", help="Build job-specific CV for Jxxxx"),
    ] = None,
    style: Annotated[
        CvStyle,
        typer.Option("--style", help="moderncv (your CV design) or plain (portable article)"),
    ] = CvStyle.MODERNCV,
) -> None:
    """Build CV from profile.yaml (base or job-specific)."""
    config = load_config()
    try:
        candidate = load_profile(config.profile_path)
    except ProfileLoadError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(VALIDATION_FAILURE) from exc

    result = validate_candidate(candidate)
    if not result.ok:
        err_console.print("[bold red]PROFILE INVALID[/bold red]")
        for issue in result.issues:
            err_console.print(str(issue))
        raise typer.Exit(VALIDATION_FAILURE)

    job = None
    match = None
    if job_id:
        session, _ = _session()
        repo = JobRepository(session)
        job = repo.get(job_id)
        if job is None:
            err_console.print(f"[red]Job not found: {job_id}[/red]")
            raise typer.Exit(GENERIC_FAILURE)
        match = RuleBasedJobAnalyzer().analyze(candidate, job)
        repo.update_match_score(job.id, match.score)

    try:
        outputs = build_cv(
            candidate=candidate,
            templates_dir=config.templates_dir,
            output_dir=config.output_dir,
            target=target,
            job=job,
            match=match,
            style=style,
        )
    except (FileNotFoundError, RuntimeError) as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(GENERIC_FAILURE) from exc

    for path in outputs:
        console.print(f"[green]Wrote[/green] {path}")


@cv_app.command("advise")
def cv_advise(
    limit: Annotated[
        int,
        typer.Option("--limit", help="How many suggestions this run may make"),
    ] = 3,
    apply_changes: Annotated[
        bool,
        typer.Option("--apply", help="Confirm each suggestion and write it to profile.yaml"),
    ] = False,
    axis: Annotated[
        str | None,
        typer.Option("--axis", help="machine | language | layout (default: all three)"),
    ] = None,
    llm: Annotated[
        bool,
        typer.Option("--llm", help="Let a plain LLM reword lines (validated; costs tokens)"),
    ] = False,
    llm_deep: Annotated[
        bool,
        typer.Option("--llm-deep", help="Also allow a reasoning model when --llm fails"),
    ] = False,
    max_llm_calls: Annotated[
        int,
        typer.Option("--max-llm-calls", help="Budget for this run"),
    ] = 3,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="With --llm: print what would be sent, call nobody"),
    ] = False,
) -> None:
    """Suggest how the CV presents what you already did. Adds no facts, deletes none."""
    from jobbot.cv.advisor import (
        advise,
        apply_advice,
        default_advice_log_path,
        record_decision,
        render_advice_markdown,
    )
    from jobbot.portals.form_learn import default_form_knowledge_path, load_form_knowledge
    from jobbot.recruiters.playbook import advisor_notes

    session, config = _session()
    try:
        candidate = load_profile(config.profile_path)
    except ProfileLoadError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(VALIDATION_FAILURE) from exc

    jobs = JobRepository(session).list_all()
    forms = load_form_knowledge(default_form_knowledge_path(config.root))
    notes = advisor_notes(config.root)
    log_path = default_advice_log_path(config.output_dir)

    narrator = _narrator()
    narrator.phase(
        Phase.RECEIVING_WORLD,
        f"{len(jobs)} JD · {len(forms)} formulario(s) · {len(notes)} práctica(s)",
    )
    suggestions = advise(
        candidate,
        jobs=jobs,
        forms=forms,
        playbook=notes,
        limit=max(1, limit),
        log_path=log_path,
    )
    if axis:
        wanted = axis.strip().casefold()
        suggestions = [item for item in suggestions if item.axis.value == wanted]
    if not suggestions:
        console.print("Nothing to suggest this run (or you already answered what there was).")
        console.print(f"Log: {log_path}")
        raise typer.Exit(SUCCESS)

    if llm or llm_deep:
        suggestions = _reword_with_llm(
            suggestions,
            candidate,
            config,
            deep=llm_deep,
            max_calls=max_llm_calls,
            dry_run=dry_run,
        )
        if dry_run:
            return

    out = config.output_dir / "cv" / "advice.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_advice_markdown(suggestions), encoding="utf-8")

    for item in suggestions:
        body = [f"[bold]{item.what}[/bold]", f"where: {item.target.describe()}", f"why: {item.why}"]
        if item.before:
            body.append(f"\nnow:      {item.before}")
        if item.is_rewrite:
            body.append(f"proposed: {item.after}")
        console.print(Panel("\n".join(body), title=f"{item.axis.value} · {item.id}"))
    console.print(f"[green]Wrote[/green] {out}")

    if not apply_changes:
        console.print(
            "Dry-run. Re-run with [bold]--apply[/bold] to confirm each one; "
            "notes without proposed text are yours to act on."
        )
        return

    raw = load_profile_raw(config.profile_path)
    applied = 0
    for item in suggestions:
        if not item.is_rewrite:
            console.print(f"[dim]{item.id}: nothing to write, it is a note.[/dim]")
            continue
        console.print(f"\n[bold]{item.what}[/bold]")
        console.print(f"  now:      {item.before}")
        console.print(f"  proposed: {item.after}")
        if not typer.confirm("Take this wording?", default=False):
            record_decision(log_path, item, "rejected")
            continue
        if apply_advice(raw, item):
            record_decision(log_path, item, "applied")
            applied += 1
        else:
            err_console.print("[yellow]The text changed since this was proposed; skipped.[/yellow]")

    if not applied:
        console.print("Nothing written.")
        return
    backup = config.profile_path.with_suffix(config.profile_path.suffix + ".bak")
    shutil.copy2(config.profile_path, backup)
    config.profile_path.write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    console.print(f"Backup: {backup}")
    console.print(f"[green]Applied[/green] {applied} rewording(s) → {config.profile_path}")
    console.print("Next: [bold]jobbot cv build[/bold] then [bold]jobbot cv propagate[/bold]")


def _reword_with_llm(
    suggestions: list[Any],
    candidate: Candidate,
    config: JobbotConfig,
    *,
    deep: bool,
    max_calls: int,
    dry_run: bool,
) -> list[Any]:
    """Ask a model to reword the suggestions it can, keeping tier 0 when it cannot."""
    from jobbot.cv.llm_advice import Budget, LlmRewriter, default_cache_dir

    rewriter = LlmRewriter(
        cache_dir=default_cache_dir(config.output_dir),
        budget=Budget(max_calls=max(1, max_calls)),
        deep=deep,
        dry_run=dry_run,
    )
    if not rewriter.available and not dry_run:
        console.print(
            "[yellow]No LLM reachable (needs `uv sync --extra llm` and OPENAI_API_KEY). "
            "Showing the deterministic suggestions.[/yellow]"
        )
        return suggestions

    out: list[Any] = []
    improved_count = 0
    for item in suggestions:
        better = rewriter.improve(item, candidate)
        if better is not None:
            improved_count += 1
            out.append(better)
        else:
            out.append(item)

    if dry_run:
        table = Table(title="What --llm would send (nothing was sent)")
        table.add_column("Suggestion")
        table.add_column("Tier")
        table.add_column("Chars", justify="right")
        for call in rewriter.planned:
            table.add_row(call.advice_id, call.tier.value, str(call.chars))
        console.print(table)
        console.print(
            f"{len(rewriter.planned)} call(s), {rewriter.total_planned_chars} characters, "
            f"budget {max_calls} call(s). Drop --dry-run to spend it."
        )
        return out

    console.print(
        f"[dim]LLM: {improved_count} rewording(s) accepted, "
        f"{len(rewriter.rejections)} discarded by validation, "
        f"{rewriter.budget.calls} call(s) spent.[/dim]"
    )
    for reason in rewriter.rejections[:3]:
        console.print(f"[dim]  discarded: {reason}[/dim]")
    return out


@cv_app.command("propagate")
def cv_propagate(
    targets: Annotated[
        str,
        typer.Option("--targets", help="all | cv,getonboard,indeed,linkedin"),
    ] = "all",
    apply_changes: Annotated[
        bool,
        typer.Option("--apply", help="Write to the portals (default: dry-run plan)"),
    ] = False,
    section: Annotated[
        str,
        typer.Option("--section", help="Indeed section: headline|summary|skills|experience|all"),
    ] = "all",
    style: Annotated[
        CvStyle,
        typer.Option("--style", help="moderncv (your CV design) or plain"),
    ] = CvStyle.MODERNCV,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip per-destination confirmation (with --apply)"),
    ] = False,
    cdp: Annotated[
        str | None,
        typer.Option("--cdp", help="Attach to your logged-in Chrome (browser chrome-debug)"),
    ] = None,
) -> None:
    """Rebuild the base CV and propagate it to your permanent portal profiles (HITL)."""
    from jobbot.cv.propagate import (
        PropagationTarget,
        UnknownTargetError,
        parse_targets,
        plan_propagation,
        summarize_plans,
    )

    config = load_config()
    try:
        candidate = load_profile(config.profile_path)
    except ProfileLoadError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(VALIDATION_FAILURE) from exc
    validation = validate_candidate(candidate)
    if not validation.ok:
        err_console.print("[bold red]PROFILE INVALID[/bold red]")
        for issue in validation.issues:
            err_console.print(str(issue))
        raise typer.Exit(VALIDATION_FAILURE)
    try:
        wanted = parse_targets(targets)
    except UnknownTargetError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(VALIDATION_FAILURE) from exc

    from jobbot.browser.sessions import inspect_sessions

    sessions = inspect_sessions(config.root, sites=[t.value for t in wanted])
    plans = plan_propagation(
        config,
        candidate,
        targets=wanted,
        section=section,
        sessions=sessions,
        cdp_url=cdp,
    )
    narrator = _narrator()
    narrator.phase(Phase.PROPAGATING_CV, summarize_plans(plans))

    table = Table(title="CV propagation plan")
    table.add_column("Destination")
    table.add_column("Operations")
    table.add_column("Detail")
    for plan in plans:
        detail = plan.blocked_reason or plan.note or ""
        if plan.hint:
            detail = f"{detail} → {plan.hint}"
        table.add_row(
            plan.target.value,
            "blocked" if not plan.ready else str(len(plan.operations)),
            detail,
        )
    console.print(table)
    for plan in plans:
        for operation in plan.operations:
            narrator.note(f"{plan.target.value}: {operation}")

    if not apply_changes:
        console.print(
            "Dry-run. Re-run with [bold]--apply[/bold] to rebuild the CV and open/write "
            "each destination (you confirm one by one)."
        )
        raise typer.Exit(SUCCESS)

    for plan in plans:
        if not plan.ready:
            err_console.print(
                f"[yellow]Skipping {plan.target.value}[/yellow]: {plan.blocked_reason}"
            )
            continue
        if not plan.actionable:
            console.print(f"{plan.target.value}: nothing to do.")
            continue
        if not yes and not typer.confirm(
            f"Propagate to {plan.target.value} ({len(plan.operations)} operation(s))?",
            default=plan.target == PropagationTarget.CV,
        ):
            console.print(f"{plan.target.value}: skipped.")
            continue
        if plan.target == PropagationTarget.CV:
            _propagate_base_cv(config, candidate, style=style)
        elif plan.target == PropagationTarget.GETONBOARD:
            _propagate_getonboard(config, apply_changes=apply_changes, cdp=cdp, yes=yes)
        elif plan.target == PropagationTarget.INDEED:
            _propagate_indeed(config, section=section, cdp=cdp, yes=yes)
        elif plan.target == PropagationTarget.LINKEDIN:
            _propagate_linkedin(config, cdp=cdp, yes=yes)


def _propagate_base_cv(config: JobbotConfig, candidate: Candidate, *, style: CvStyle) -> None:
    for target in (BuildTarget.CV, BuildTarget.ATS):
        try:
            outputs = build_cv(
                candidate=candidate,
                templates_dir=config.templates_dir,
                output_dir=config.output_dir,
                target=target,
                style=style,
            )
        except (FileNotFoundError, RuntimeError) as exc:
            err_console.print(f"[red]cv ({target.value}): {exc}[/red]")
            continue
        for path in outputs:
            console.print(f"[green]Wrote[/green] {path}")


def _getonboard_session(config: JobbotConfig, cdp: str | None) -> Any:
    from jobbot.browser.cdp import resolve_cdp_url
    from jobbot.browser.session import BrowserSession

    return BrowserSession(
        profile_dir=config.root / "browser-data" / "getonboard-cdp",
        headless=False,
        cdp_url=resolve_cdp_url(cdp),
        debug_root=config.output_dir / "debug",
    )


def _propagate_getonboard(
    config: JobbotConfig,
    *,
    apply_changes: bool,
    cdp: str | None,
    yes: bool,
) -> None:
    from jobbot.adapters.getonboard.client import GetOnBoardProfileClient
    from jobbot.adapters.getonboard.draft import load_permanent_profile
    from jobbot.adapters.getonboard.profile_edit import (
        GOB_EDIT_URL,
        apply_writes,
        desired_from_fields,
        plan_writes,
        read_current,
    )

    client = GetOnBoardProfileClient.from_config(config)
    path, result = client.prepare_package()
    console.print(f"[green]Wrote[/green] {path}  (mode={result.mode})")
    if not apply_changes:
        console.print(f"Dry-run: --apply escribe el perfil en {GOB_EDIT_URL}")
        return

    fields = load_permanent_profile(config.output_dir)
    if fields is None:
        err_console.print("[red]getonboard: no permanent profile to write[/red]")
        return
    desired = desired_from_fields(
        fields.headline,
        fields.experiencia_y_perfil,
        fields.formacion_academica,
    )
    with _getonboard_session(config, cdp) as browser:
        page = browser.page
        page.goto(GOB_EDIT_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        writes = plan_writes(read_current(page), desired)
        if not writes:
            console.print("getonboard: el portal ya tiene estos textos.")
            return
        for write in writes:
            console.print(f"  {write.describe()}")
        if not yes and not typer.confirm(
            f"Write these {len(writes)} field(s) on Get on Board?",
            default=False,
        ):
            console.print("getonboard: skipped.")
            return
        done = apply_writes(page, writes)
    console.print(f"[green]Wrote[/green] {len(done)} field(s) on Get on Board.")
    console.print("Tus CVs sigue siendo manual: sube output/base/cv.pdf y márcalo default.")
    console.print(client.open_resumes())


def _propagate_indeed(config: JobbotConfig, *, section: str, cdp: str | None, yes: bool) -> None:
    from jobbot.adapters.indeed.client import IndeedAdapter
    from jobbot.browser.cdp import resolve_cdp_url

    adapter = IndeedAdapter.from_config(config, cdp_url=resolve_cdp_url(cdp))
    plan = adapter.build_sync_plan(section=section)
    if not plan.actionable:
        console.print("indeed: no changes required.")
        return
    if not yes and not typer.confirm(
        f"Apply these {len(plan.actionable)} Indeed modifications?",
        default=False,
    ):
        console.print("indeed: skipped.")
        return
    console.print(adapter.apply_sync_plan(plan).message)


def _propagate_linkedin(config: JobbotConfig, *, cdp: str | None, yes: bool) -> None:
    from jobbot.adapters.linkedin.client import LinkedInAdapter
    from jobbot.adapters.linkedin.package import LinkedInPublicationItem
    from jobbot.browser.cdp import resolve_cdp_url

    adapter = LinkedInAdapter.from_config(config, cdp_url=resolve_cdp_url(cdp))
    console.print("Fetching remote publication titles…")
    remote_titles = adapter.fetch_remote_publication_titles()

    def _confirm(item: LinkedInPublicationItem) -> bool:
        if yes:
            return True
        return typer.confirm(f"Add publication: {item.title}?", default=True)

    console.print(
        adapter.apply_publications(confirm_each=_confirm, remote_titles=remote_titles).message
    )


# ── jobs ─────────────────────────────────────────────────────────────────────


@jobs_app.command("add")
def jobs_add(
    file: Annotated[
        Path | None,
        typer.Option("--file", "-f", help="Path to JD text file"),
    ] = None,
    url: Annotated[str | None, typer.Option("--url")] = None,
    stdin: Annotated[
        bool,
        typer.Option("--stdin", help="Read JD from stdin"),
    ] = False,
) -> None:
    """Add a job posting from a text file or stdin (manual fallback)."""
    session, config = _session()
    if file is not None:
        text = file.read_text(encoding="utf-8")
    elif stdin:
        text = typer.get_text_stream("stdin").read()
    else:
        err_console.print("Provide --file or --stdin (prefer: jobbot jobs search)")
        raise typer.Exit(GENERIC_FAILURE)

    repo = JobRepository(session)
    job = repo.add_from_text(text, url=url)
    path = write_job_json(job, config.output_dir)
    console.print(f"[green]Added[/green] {job.id}  {job.company}  {job.title}")
    console.print(f"Wrote {path}")
    _learn_company_knowledge(config, job)


@jobs_app.command("search")
def jobs_search(
    query: Annotated[str, typer.Argument(help="Search query, e.g. the role you want")],
    location: Annotated[
        str | None,
        typer.Option("--location", "-l", help="Location (default: Santiago)"),
    ] = "Santiago",
    remote: Annotated[bool, typer.Option("--remote", help="Prefer remote filters")] = False,
    limit: Annotated[
        int,
        typer.Option("--limit", help="Max results (1-50, default 20)"),
    ] = 20,
    enrich: Annotated[
        bool,
        typer.Option(
            "--enrich/--no-enrich",
            help="Open each job page for full description (slower)",
        ),
    ] = True,
    cdp: Annotated[
        str | None,
        typer.Option(
            "--cdp",
            help="Attach to user Chrome via CDP (e.g. http://127.0.0.1:9222). "
            "Also: JOBBOT_CDP_URL. Start with: jobbot browser chrome-debug",
        ),
    ] = None,
) -> None:
    """Search Indeed and store job postings locally (small volumes)."""
    from jobbot.adapters.indeed.jobs import IndeedJobSource
    from jobbot.browser.cdp import resolve_cdp_url
    from jobbot.jobs.sources import JobSearchQuery

    if limit < 1 or limit > 50:
        err_console.print("--limit must be between 1 and 50")
        raise typer.Exit(GENERIC_FAILURE)

    session, config = _session()
    cdp_url = resolve_cdp_url(cdp)
    source = IndeedJobSource(config, cdp_url=cdp_url)
    q = JobSearchQuery(query=query, location=location, remote=remote, limit=limit)

    if cdp_url:
        console.print(f"Using CDP Chrome at [bold]{cdp_url}[/bold]")
    console.print(f"Searching Indeed ({source.base}) for [bold]{query}[/bold]…")
    try:
        found = source.search_jobs(q) if enrich else source.search_cards(q)
    except Exception as exc:
        err_console.print(f"[red]Indeed search failed: {exc}[/red]")
        raise typer.Exit(GENERIC_FAILURE) from exc

    if not found:
        console.print("No jobs found.")
        raise typer.Exit(SUCCESS)

    repo = JobRepository(session)
    table = Table(title="Indeed search results")
    table.add_column("ID")
    table.add_column("Company")
    table.add_column("Role")
    table.add_column("Match")
    stored: list[str] = []
    for raw in found:
        job = repo.upsert_external(raw)
        write_job_json(job, config.output_dir)
        _learn_company_knowledge(config, job)
        stored.append(job.id)
        score = f"{job.match_score:.0f}%" if job.match_score is not None else "-"
        table.add_row(job.id, job.company, job.title, score)
    console.print(table)
    console.print(f"Stored {len(stored)} jobs. Next: [bold]jobbot jobs match {stored[0]}[/bold]")
    console.print("Or: [bold]jobbot jobs shortlist[/bold]")


@jobs_app.command("show")
def jobs_show(
    job_id: Annotated[str, typer.Argument()],
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show a stored job posting."""
    session, _ = _session()
    job = JobRepository(session).get(job_id)
    if job is None:
        err_console.print(f"[red]Job not found: {job_id}[/red]")
        raise typer.Exit(GENERIC_FAILURE)
    if as_json:
        console.print_json(data=job.model_dump(mode="json"))
        return
    console.print(f"[bold]{job.id}[/bold]  {job.title}")
    console.print(f"Company: {job.company}")
    console.print(f"Location: {job.location or '—'}")
    console.print(f"Seniority: {job.seniority or '—'}")
    console.print(f"Remote: {job.remote_type or '—'}")
    console.print(f"URL: {job.url or '—'}")
    console.print(f"Skills: {', '.join(job.skills) or '—'}")
    if job.requirements:
        console.print("Requirements:")
        for req in job.requirements:
            console.print(f"  - {req}")
    console.print(Panel(job.description[:2000], title="Description"))


@jobs_app.command("match")
def jobs_match(
    job_id: Annotated[str, typer.Argument()],
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Match a job against the local profile (decision aid)."""
    session, config = _session()
    try:
        candidate = load_profile(config.profile_path)
    except ProfileLoadError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(VALIDATION_FAILURE) from exc

    repo = JobRepository(session)
    job = repo.get(job_id)
    if job is None:
        err_console.print(f"[red]Job not found: {job_id}[/red]")
        raise typer.Exit(GENERIC_FAILURE)

    match = RuleBasedJobAnalyzer().analyze(candidate, job)
    repo.update_match_score(job.id, match.score)
    job_dir = config.output_dir / "jobs" / job.id
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "match.json").write_text(
        json.dumps(match.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    if as_json:
        console.print_json(data=match.to_dict())
        return
    console.print(format_match_report(match))


@jobs_app.command("shortlist")
def jobs_shortlist() -> None:
    """Rank stored jobs by match score."""
    session, config = _session()
    try:
        candidate = load_profile(config.profile_path)
    except ProfileLoadError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(VALIDATION_FAILURE) from exc

    repo = JobRepository(session)
    analyzer = RuleBasedJobAnalyzer()
    rows: list[tuple[float, str, str, str]] = []
    for job in repo.list_all():
        match = analyzer.analyze(candidate, job)
        repo.update_match_score(job.id, match.score)
        rows.append((match.score, job.id, job.title, job.company))
    rows.sort(key=lambda r: r[0], reverse=True)
    console.print("[bold]TOP MATCHES[/bold]")
    for score, jid, title, company in rows:
        console.print(f"{score:5.1f}%  {jid}  {title}  {company}")


@jobs_app.command("backfill-dates")
def jobs_backfill_dates() -> None:
    """Date already-stored posts from the activity id in their URL (offline)."""
    from jobbot.jobs.backfill import backfill_posted_at

    session, _ = _session()
    repo = JobRepository(session)
    updated = backfill_posted_at(repo)
    console.print(f"Dated [bold]{updated}[/bold] stored jobs from their post URL.")
    stale = [
        job
        for job in repo.list_all()
        if job.posted_at is not None and not is_fresh(job.posted_at)
    ]
    if stale:
        console.print("Older than the freshness window:")
        for job in stale:
            console.print(f"  {job.id}  {age_label(job.posted_at):>9}  {job.title[:50]}")


@jobs_app.command("note")
def jobs_note(
    job_id: Annotated[str, typer.Argument()],
    text: Annotated[str, typer.Argument()],
) -> None:
    """Attach a free-text note to a job."""
    session, _ = _session()
    try:
        JobRepository(session).set_note(job_id, text)
    except KeyError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(GENERIC_FAILURE) from exc
    console.print(f"[green]Noted[/green] {job_id}")


# ── application(s) ───────────────────────────────────────────────────────────


def _build_job_cv(config: JobbotConfig, candidate: Candidate, job: JobPosting) -> None:
    """Build the CV adapted to this job, unless it is already there."""
    job_dir = config.output_dir / "jobs" / job.id
    if (job_dir / "cv.pdf").is_file() or (job_dir / "cv_ats.txt").is_file():
        return
    console.print(f"Building CV adapted to {job.id}…")
    match = RuleBasedJobAnalyzer().analyze(candidate, job)
    try:
        build_cv(
            candidate,
            config.templates_dir,
            config.output_dir,
            target=BuildTarget.CV,
            job=job,
            match=match,
        )
    except RuntimeError as exc:
        # PDF may fail without xelatex; ATS text is enough for the package
        err_console.print(f"[yellow]{exc}[/yellow]")
        build_cv(
            candidate,
            config.templates_dir,
            config.output_dir,
            target=BuildTarget.ATS,
            job=job,
            match=match,
        )


@application_app.command("prepare")
def application_prepare(job_id: Annotated[str, typer.Argument()]) -> None:
    """Prepare application package for a job (does not invent answers)."""
    session, config = _session()
    repo = JobRepository(session)
    job = repo.get(job_id)
    if job is None:
        err_console.print(f"[red]Job not found: {job_id}[/red]")
        raise typer.Exit(GENERIC_FAILURE)

    job_dir = config.output_dir / "jobs" / job.id
    try:
        candidate = load_profile(config.profile_path)
    except ProfileLoadError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(VALIDATION_FAILURE) from exc

    narrator = _narrator()
    narrator.phase(Phase.PROPAGATING_CV, f"{job.company} · {job.title}"[:60])
    _build_job_cv(config, candidate, job)

    app_dir = prepare_application_package(
        job, config.output_dir, job_dir=job_dir, candidate=candidate
    )
    ApplicationRepository(session).upsert_for_job(
        job.id,
        status=ApplicationStatus.PREPARED,
        package_dir=str(app_dir),
    )
    console.print(f"[green]Prepared[/green] {app_dir}")
    gob = app_dir / "getonboard_es.md"
    if gob.is_file():
        console.print(f"Get on Board Spanish drafts: {gob}")


@application_app.command("open")
def application_open(job_id: Annotated[str, typer.Argument()]) -> None:
    """Open the job URL (or ATS URL) in the default browser (does not apply)."""
    session, _ = _session()
    job = JobRepository(session).get(job_id)
    if job is None:
        err_console.print(f"[red]Job not found: {job_id}[/red]")
        raise typer.Exit(GENERIC_FAILURE)
    from jobbot.adapters.ats.apply import open_ats_in_browser, resolve_ats_url

    ats_url, _kind = resolve_ats_url(job)
    target = ats_url or job.url
    if not target:
        err_console.print(f"[red]No URL for job {job_id}[/red]")
        raise typer.Exit(GENERIC_FAILURE)
    open_ats_in_browser(target)
    console.print(f"Opened {target}")


@application_app.command("apply")
def application_apply(
    job_id: Annotated[str, typer.Argument()],
    apply_changes: Annotated[
        bool,
        typer.Option(
            "--apply",
            help="Open ATS/Gmail and record assisted apply (default: dry-run plan only)",
        ),
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Skip confirmation")] = False,
    attach: Annotated[
        bool,
        typer.Option(
            "--attach/--no-attach",
            help="Email apply: attach the CV in Gmail via browser (--no-attach = compose URL only)",
        ),
    ] = True,
    cdp: Annotated[
        str | None,
        typer.Option("--cdp", help="Attach to your logged-in Chrome (see browser chrome-debug)"),
    ] = None,
) -> None:
    """Plan or open ATS/Gmail apply for a job (HITL; no CAPTCHA bypass; no invented answers)."""
    from jobbot.adapters.ats.apply import build_apply_plan, prefill_field_map
    from jobbot.adapters.ats.email_apply import build_email_draft, open_gmail_compose
    from jobbot.adapters.ats.registry import adapter_for_job
    from jobbot.adapters.base import ApplyMethod
    from jobbot.applications.manager import FilesystemApplicationPackage

    session, config = _session()
    job = JobRepository(session).get(job_id)
    if job is None:
        err_console.print(f"[red]Job not found: {job_id}[/red]")
        raise typer.Exit(GENERIC_FAILURE)
    try:
        candidate = load_profile(config.profile_path)
    except ProfileLoadError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(VALIDATION_FAILURE) from exc

    plan = build_apply_plan(candidate, job)
    adapter = adapter_for_job(job)
    adapter_name = adapter.name if adapter is not None else plan.ats_kind.value
    console.print(f"[bold]{job.id}[/bold]  {job.title} @ {job.company}")
    console.print(f"ATS: {plan.ats_kind.value}  adapter={adapter_name}  {plan.ats_url or '(none)'}")
    console.print(f"Method: {plan.method.value}")
    console.print(plan.message)

    if plan.method == ApplyMethod.EMAIL:
        from jobbot.adapters.ats.email_apply import is_tailored_cv, resolve_cv_path

        if apply_changes:
            _build_job_cv(config, candidate, job)
            prepare_application_package(
                job,
                config.output_dir,
                job_dir=config.output_dir / "jobs" / job.id,
                candidate=candidate,
            )
        cv_pdf = resolve_cv_path(config.output_dir, job.id)
        tailored = is_tailored_cv(cv_pdf, job.id)
        draft = build_email_draft(candidate, job, cv_path=cv_pdf)
        if cv_pdf is None:
            cv_line = "(none — run jobbot cv build --job " + job.id + ")"
        elif tailored:
            cv_line = f"{cv_pdf}  [green](adapted to {job.id})[/green]"
        else:
            cv_line = f"{cv_pdf}  [yellow](base CV — not adapted)[/yellow]"
        console.print(
            Panel(
                f"[bold]To:[/bold] {draft.to}\n"
                f"[bold]Subject:[/bold] {draft.subject}\n\n"
                f"{draft.body}\n\n"
                f"[bold]CV:[/bold] {cv_line}",
                title="email apply draft (HITL)",
            )
        )
        if draft.body_truncated_for_url:
            console.print(
                "[yellow]Body is long — Gmail URL may truncate; "
                "paste the rest from this dry-run if needed.[/yellow]"
            )
        if not apply_changes:
            if not tailored:
                console.print(
                    f"Tip: [bold]jobbot cv build --job {job.id}[/bold] first — "
                    "--apply builds the adapted CV for you."
                )
            console.print(
                "Dry-run only. Re-run with [bold]--apply[/bold] to open Gmail compose "
                "(log in if asked, attach CV, press Send yourself)."
            )
            return
        if not yes and not typer.confirm(
            "¿Abrir Gmail con el CV adjunto para que lo revises y envíes vos?",
            default=False,
        ):
            console.print("Aborted.")
            raise typer.Exit(SUCCESS)
        if attach and cv_pdf is not None:
            from jobbot.adapters.gmail.compose import GmailComposeAdapter, GmailComposeError

            try:
                GmailComposeAdapter(config, cdp_url=cdp).open_draft_for_review(
                    draft, cv_path=cv_pdf
                )
                console.print(
                    f"[green]Gmail draft ready with[/green] {cv_pdf.name} "
                    "[green]attached. Review it and press Send yourself.[/green]"
                )
            except GmailComposeError as exc:
                err_console.print(f"[yellow]Could not attach in Gmail: {exc}[/yellow]")
                open_gmail_compose(draft)
                err_console.print(
                    f"[yellow]Opened plain compose — attach {cv_pdf} by hand.[/yellow]"
                )
        else:
            url = open_gmail_compose(draft)
            console.print(f"Opened Gmail compose ({len(url)} chars URL)")
            console.print(
                f"Adjuntá el CV ({cv_pdf or 'output/base/cv.pdf'}) "
                "y pulsá [bold]Enviar[/bold] en Gmail. JobBot no envía por vos."
            )
        job_dir = config.output_dir / "jobs" / job.id
        app_dir = prepare_application_package(
            job, config.output_dir, job_dir=job_dir, candidate=candidate
        )
        ApplicationRepository(session).upsert_for_job(
            job.id,
            status=ApplicationStatus.PREPARED,
            package_dir=str(app_dir),
        )
        if yes:
            console.print(
                "[dim]Status stays prepared — --yes skips the applied prompt; "
                "confirm after you actually send.[/dim]"
            )
        elif typer.confirm("Mark application as applied after you send?", default=False):
            ApplicationRepository(session).upsert_for_job(
                job.id,
                status=ApplicationStatus.APPLIED,
                package_dir=str(app_dir),
            )
            console.print("[green]Status → applied[/green]")
        return

    console.print("Known fields to inject:")
    for key, value in prefill_field_map(candidate).items():
        console.print(f"  {key}: {value}")
    prefill_review = plan.needs_review
    if adapter is not None:
        pkg_preview = FilesystemApplicationPackage(
            config.output_dir / "jobs" / job.id / "application"
        )
        prefill_review = adapter.prefill(candidate, job, pkg_preview).needs_review
    console.print("Needs human review:")
    for item in prefill_review:
        console.print(f"  • {item}")
    if not apply_changes:
        console.print(
            "Dry-run only. Prepare package then re-run with [bold]--apply[/bold] "
            "to open the ATS (you submit)."
        )
        return
    if not plan.ats_url:
        err_console.print("[red]No ATS URL — cannot open portal.[/red]")
        raise typer.Exit(GENERIC_FAILURE)
    if not yes and not typer.confirm(
        f"Open {plan.ats_kind.value} and assist apply (you submit)?",
        default=False,
    ):
        console.print("Aborted.")
        raise typer.Exit(SUCCESS)
    # Ensure package exists
    job_dir = config.output_dir / "jobs" / job.id
    app_dir = prepare_application_package(
        job, config.output_dir, job_dir=job_dir, candidate=candidate
    )
    if adapter is not None and hasattr(adapter, "open"):
        adapter.open(job)
    else:
        from jobbot.adapters.ats.apply import open_ats_in_browser

        open_ats_in_browser(plan.ats_url)
    ApplicationRepository(session).upsert_for_job(
        job.id,
        status=ApplicationStatus.PREPARED,
        package_dir=str(app_dir),
    )
    # Write prefill cheat-sheet next to package
    cheat = app_dir / "ats_prefill.yaml"
    import yaml

    cheat.write_text(
        yaml.safe_dump(
            {
                "ats_url": plan.ats_url,
                "ats_kind": plan.ats_kind.value,
                "fields": prefill_field_map(candidate),
                "needs_review": prefill_review,
                "note": "Fill only known fields; leave blank rather than inventing.",
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    console.print(f"[green]Opened ATS[/green] {plan.ats_url}")
    console.print(f"Prefill sheet: {cheat}")
    console.print("Submit manually after reviewing HITL fields.")
    _learn_form_from_apply(config, plan.ats_url, job.company)
    if yes:
        console.print(
            "[dim]Status stays prepared — --yes skips the applied prompt; "
            "confirm after you actually submit.[/dim]"
        )
    elif typer.confirm("Mark application as applied?", default=False):
        ApplicationRepository(session).upsert_for_job(
            job.id,
            status=ApplicationStatus.APPLIED,
            package_dir=str(app_dir),
        )
        console.print("[green]Status → applied[/green]")


@application_app.command("show")
def application_show(job_id: Annotated[str, typer.Argument()]) -> None:
    """Show application package path and status for a job."""
    session, config = _session()
    apps = [a for a in ApplicationRepository(session).list_all() if a.job_id == job_id]
    job = JobRepository(session).get(job_id)
    if job is None:
        err_console.print(f"[red]Job not found: {job_id}[/red]")
        raise typer.Exit(GENERIC_FAILURE)
    console.print(f"{job.id}  {job.company}  {job.title}")
    if apps:
        app = apps[0]
        console.print(f"Application: {app.id}  status={app.status.value}")
        pkg = app.package_dir or str(config.output_dir / "jobs" / job_id / "application")
        console.print(f"Package: {pkg}")
    else:
        console.print("No application record yet. Run: jobbot application prepare " + job_id)


@applications_app.command("list")
def applications_list() -> None:
    """List tracked applications."""
    session, _ = _session()
    jobs = {j.id: j for j in JobRepository(session).list_all()}
    table = Table(title="Applications")
    table.add_column("ID")
    table.add_column("Company")
    table.add_column("Role")
    table.add_column("Status")
    for app in ApplicationRepository(session).list_all():
        job = jobs.get(app.job_id)
        table.add_row(
            app.id,
            job.company if job else "?",
            job.title if job else app.job_id,
            app.status.value,
        )
    console.print(table)


@applications_app.command("status")
def applications_status() -> None:
    """Alias for applications list."""
    applications_list()


# ── indeed / linkedin (Vertical B) ───────────────────────────────────────────


@indeed_app.command("login")
def indeed_login(
    cdp: Annotated[
        str | None,
        typer.Option("--cdp", help="Attach to Chrome CDP (e.g. http://127.0.0.1:9222)"),
    ] = None,
) -> None:
    """Open Indeed login with persistent browser profile."""
    from jobbot.adapters.indeed.client import IndeedAdapter
    from jobbot.browser.cdp import resolve_cdp_url

    IndeedAdapter.from_config(load_config(), cdp_url=resolve_cdp_url(cdp)).login()


@indeed_app.command("status")
def indeed_status(
    cdp: Annotated[str | None, typer.Option("--cdp")] = None,
) -> None:
    """Check whether an Indeed session appears valid."""
    from jobbot.adapters.indeed.client import IndeedAdapter
    from jobbot.browser.cdp import resolve_cdp_url

    ok = IndeedAdapter.from_config(load_config(), cdp_url=resolve_cdp_url(cdp)).session_valid()
    console.print("Indeed session: " + ("valid" if ok else "not authenticated"))


@indeed_app.command("inspect")
def indeed_inspect(
    cdp: Annotated[str | None, typer.Option("--cdp")] = None,
) -> None:
    """Inspect Indeed page roles/labels for selector development."""
    from jobbot.adapters.indeed.client import IndeedAdapter
    from jobbot.browser.cdp import resolve_cdp_url

    IndeedAdapter.from_config(load_config(), cdp_url=resolve_cdp_url(cdp)).inspect()


@indeed_app.command("prepare")
def indeed_prepare() -> None:
    """Write Indeed sync package markdown from profile.yaml (no portal write)."""
    from jobbot.adapters.indeed.client import IndeedAdapter

    path = IndeedAdapter.from_config(load_config()).prepare_package()
    console.print(f"[green]Wrote[/green] {path}")
    console.print("Review, then: jobbot indeed sync --section all [--apply]")


@indeed_app.command("pull")
def indeed_pull(
    cdp: Annotated[str | None, typer.Option("--cdp")] = None,
) -> None:
    """Pull Indeed profile snapshot (read)."""
    from jobbot.adapters.indeed.client import IndeedAdapter
    from jobbot.browser.cdp import resolve_cdp_url

    path = IndeedAdapter.from_config(load_config(), cdp_url=resolve_cdp_url(cdp)).pull_and_save()
    console.print(f"[green]Wrote[/green] {path}")


@indeed_app.command("diff")
def indeed_diff(
    section: Annotated[str | None, typer.Option("--section")] = None,
) -> None:
    """Diff local profile vs Indeed snapshot."""
    from jobbot.adapters.diff_engine import render_profile_diff

    config = load_config()
    candidate = load_profile(config.profile_path)
    console.print(render_profile_diff(candidate, config.output_dir, "indeed", section=section))


@indeed_app.command("sync")
def indeed_sync(
    section: Annotated[
        str,
        typer.Option(
            "--section",
            help="headline|summary|skills|experience|all (default: all)",
        ),
    ] = "all",
    apply_changes: Annotated[
        bool,
        typer.Option("--apply", help="Apply changes (default is dry-run)"),
    ] = False,
    reconcile: Annotated[
        bool,
        typer.Option(
            "--reconcile",
            help="Full mirror: update/add/delete Indeed Resume to match profile.yaml",
        ),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option("--yes", help="Skip interactive confirmation (with --apply)"),
    ] = False,
    cdp: Annotated[
        str | None,
        typer.Option("--cdp", help="Attach to Chrome CDP (e.g. http://127.0.0.1:9222)"),
    ] = None,
) -> None:
    """Dry-run (default) or apply Indeed profile sync from profile.yaml."""
    from jobbot.adapters.indeed.client import IndeedAdapter
    from jobbot.browser.cdp import resolve_cdp_url

    adapter = IndeedAdapter.from_config(load_config(), cdp_url=resolve_cdp_url(cdp))
    if reconcile:
        if not apply_changes:
            console.print(
                "Reconcile dry-run: will update/add/delete Indeed Resume to mirror "
                "profile.yaml (publications are NOT written to Recognitions)."
            )
            console.print("Re-run with [bold]--reconcile --apply[/bold] to write.")
            return
        if not yes and not typer.confirm(
            "Full mirror Indeed ← profile.yaml (may delete legacy Indeed rows)?",
            default=False,
        ):
            console.print("Aborted.")
            raise typer.Exit(SUCCESS)
        result = adapter.apply_reconcile()
        console.print(result.message)
        return

    plan = adapter.build_sync_plan(section=section)
    if not plan.actionable:
        console.print("No changes required.")
        return
    console.print("Operations:")
    for op in plan.actionable:
        console.print(f"  {op.op.value:6} {op.section}.{op.field}  {op.label}")
    if not apply_changes:
        console.print(
            "Dry-run only. Re-run with [bold]--apply[/bold] "
            "or full mirror with [bold]--reconcile --apply[/bold]."
        )
        return
    if not yes and not typer.confirm(
        f"Apply these {len(plan.actionable)} modifications?",
        default=False,
    ):
        console.print("Aborted.")
        raise typer.Exit(SUCCESS)
    result = adapter.apply_sync_plan(plan)
    console.print(result.message)


@linkedin_app.command("login")
def linkedin_login(
    cdp: Annotated[
        str | None,
        typer.Option("--cdp", help="Attach to Chrome CDP (e.g. http://127.0.0.1:9222)"),
    ] = None,
) -> None:
    """Open LinkedIn login with persistent browser profile."""
    from jobbot.adapters.linkedin.client import LinkedInAdapter
    from jobbot.browser.cdp import resolve_cdp_url

    LinkedInAdapter.from_config(load_config(), cdp_url=resolve_cdp_url(cdp)).login()


@linkedin_app.command("status")
def linkedin_status(
    cdp: Annotated[str | None, typer.Option("--cdp")] = None,
) -> None:
    """Check whether a LinkedIn session appears valid."""
    from jobbot.adapters.linkedin.client import LinkedInAdapter
    from jobbot.browser.cdp import resolve_cdp_url

    ok = LinkedInAdapter.from_config(load_config(), cdp_url=resolve_cdp_url(cdp)).session_valid()
    console.print("LinkedIn session: " + ("valid" if ok else "not authenticated"))


@linkedin_app.command("inspect")
def linkedin_inspect(
    cdp: Annotated[str | None, typer.Option("--cdp")] = None,
) -> None:
    """Inspect LinkedIn page for selector development."""
    from jobbot.adapters.linkedin.client import LinkedInAdapter
    from jobbot.browser.cdp import resolve_cdp_url

    LinkedInAdapter.from_config(load_config(), cdp_url=resolve_cdp_url(cdp)).inspect()


@linkedin_app.command("pull")
def linkedin_pull(
    cdp: Annotated[str | None, typer.Option("--cdp")] = None,
) -> None:
    """Pull LinkedIn profile snapshot (read-only)."""
    from jobbot.adapters.linkedin.client import LinkedInAdapter
    from jobbot.browser.cdp import resolve_cdp_url

    path = LinkedInAdapter.from_config(load_config(), cdp_url=resolve_cdp_url(cdp)).pull_and_save()
    console.print(f"[green]Wrote[/green] {path}")


@linkedin_app.command("diff")
def linkedin_diff(
    section: Annotated[str | None, typer.Option("--section")] = None,
) -> None:
    """Diff local profile vs LinkedIn snapshot (read-only audit)."""
    from jobbot.adapters.diff_engine import render_profile_diff

    config = load_config()
    candidate = load_profile(config.profile_path)
    console.print(render_profile_diff(candidate, config.output_dir, "linkedin", section=section))


@linkedin_app.command("sync")
def linkedin_sync(
    section: Annotated[
        str,
        typer.Option("--section", help="Only 'publications' is writable"),
    ] = "publications",
    apply_changes: Annotated[
        bool,
        typer.Option("--apply", help="Apply changes (default is dry-run)"),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option("--yes", help="Skip per-item confirmation (with --apply)"),
    ] = False,
    cdp: Annotated[
        str | None,
        typer.Option("--cdp", help="Attach to Chrome CDP (e.g. http://127.0.0.1:9222)"),
    ] = None,
    fetch_remote: Annotated[
        bool,
        typer.Option(
            "--fetch-remote/--no-fetch-remote",
            help="Scrape LinkedIn publications list to skip already-present titles",
        ),
    ] = True,
    enrich: Annotated[
        bool,
        typer.Option(
            "--enrich/--no-enrich",
            help="Update existing LinkedIn pubs with date, DOI URL, authors description",
        ),
    ] = False,
) -> None:
    """Dry-run or apply LinkedIn Publications from profile.yaml (DOI + coauthors)."""
    from jobbot.adapters.linkedin.client import LinkedInAdapter
    from jobbot.adapters.linkedin.package import build_linkedin_publication_items
    from jobbot.browser.cdp import resolve_cdp_url

    if section != "publications":
        err_console.print(
            f"[red]LinkedIn sync only supports --section publications (got {section!r}).[/red]"
        )
        raise typer.Exit(GENERIC_FAILURE)

    config = load_config()
    adapter = LinkedInAdapter.from_config(config, cdp_url=resolve_cdp_url(cdp))
    candidate = load_profile(config.profile_path)
    items = build_linkedin_publication_items(candidate)

    remote_titles: list[str] = []
    if fetch_remote and apply_changes:
        console.print("Fetching remote publication titles…")
        remote_titles = adapter.fetch_remote_publication_titles()
    elif fetch_remote and not apply_changes:
        console.print(
            "[dim]Dry-run assumes remote empty unless you pass --apply "
            "(which fetches remote titles).[/dim]"
        )

    plan = adapter.build_publications_plan(
        candidate, remote_titles=remote_titles, enrich_existing=enrich
    )
    actionable = plan.actionable
    console.print(f"Local publications: {len(items)}")
    if remote_titles:
        console.print(f"Remote titles matched: {len(remote_titles)}")
    if not actionable:
        console.print("No publications to add/enrich (all present or profile empty).")
        return
    console.print("Operations:")
    for op in actionable:
        after = op.after if isinstance(op.after, dict) else {}
        coauthors = ", ".join(after.get("coauthors") or []) or "(solo)"
        console.print(f"  {op.op.value:6} {op.label}")
        console.print(f"      publisher={after.get('publisher')} year={after.get('year')}")
        console.print(f"      url={after.get('url')}")
        console.print(f"      coauthors={coauthors}")
    if not apply_changes:
        console.print(
            "Dry-run only. Re-run with [bold]--apply[/bold] "
            "(confirms each publication unless [bold]--yes[/bold]). "
            "Use [bold]--enrich[/bold] to update existing entries."
        )
        return

    def _confirm(item: object) -> bool:
        if yes:
            return True
        title = getattr(item, "title", str(item))
        return typer.confirm(f"Write publication to LinkedIn?\n  {title}", default=True)

    result = adapter.apply_publications(
        confirm_each=_confirm,
        remote_titles=remote_titles,
        enrich_existing=enrich,
    )
    console.print(result.message)


@linkedin_app.command("sweep")
def linkedin_sweep(
    query: Annotated[
        str | None,
        typer.Argument(help="Content search keywords (default: your own headline + 'hiring')"),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", help="Max posts to keep")] = 20,
    fixture: Annotated[
        Path | None,
        typer.Option("--fixture", help="Parse posts from a text fixture (no browser)"),
    ] = None,
    register_portals: Annotated[
        bool,
        typer.Option(
            "--register-portals/--no-register-portals",
            help="Upsert detected ATS domains into data/portals.yaml",
        ),
    ] = True,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Auto-add new portals without prompting"),
    ] = False,
    cdp: Annotated[
        str | None,
        typer.Option("--cdp", help="Attach to Chrome CDP"),
    ] = None,
    country: Annotated[
        list[str] | None,
        typer.Option(
            "--country",
            help="Where you want to work, repeatable (default: [search].countries, CL)",
        ),
    ] = None,
    any_country: Annotated[
        bool,
        typer.Option("--any-country", help="Keep posts from every country"),
    ] = False,
    copy_links: Annotated[
        bool,
        typer.Option(
            "--copy-links/--no-copy-links",
            help="Read each post's own URL from its '…' menu (one extra click per post)",
        ),
    ] = True,
    max_age_days: Annotated[
        int | None,
        typer.Option(
            "--max-age-days",
            help="Skip posts older than N days (default: [search].max_age_days, 30)",
        ),
    ] = None,
    any_age: Annotated[
        bool,
        typer.Option("--any-age", help="Keep posts of every age"),
    ] = False,
) -> None:
    """Sweep LinkedIn recruiter posts → store jobs + detect ATS URLs (MVP: posts)."""
    from jobbot.adapters.getonboard.jobs import remember_portal_from_url
    from jobbot.adapters.linkedin.posts_source import LinkedInPostJobSource
    from jobbot.browser.cdp import resolve_cdp_url
    from jobbot.jobs.sources import JobSearchQuery, get_job_source
    from jobbot.portals.detect import AtsKind
    from jobbot.portals.registry import (
        default_portals_path,
        domain_from_url,
        load_registry,
        save_registry,
    )

    if limit < 1 or limit > 50:
        err_console.print("--limit must be between 1 and 50")
        raise typer.Exit(GENERIC_FAILURE)

    session, config = _session()
    if query is None:
        role = _profile_role_query(config)
        if role is None:
            err_console.print(
                "No query given and no role in the profile: "
                "pass the keywords or set personal.headline."
            )
            raise typer.Exit(GENERIC_FAILURE)
        query = f"hiring {role}"
        console.print(f"[dim]Query from your profile: {query}[/dim]")
    countries = resolve_countries(config.search.countries, country, any_country=any_country)
    max_age = 0 if any_age else config.search.max_age_days
    if max_age_days is not None and not any_age:
        max_age = max_age_days
    source = get_job_source("linkedin_post", config, cdp_url=resolve_cdp_url(cdp))
    assert isinstance(source, LinkedInPostJobSource)
    if countries:
        console.print(
            f"Country filter: [bold]{', '.join(countries)}[/bold] (--any-country to lift)"
        )
    if max_age > 0:
        console.print(
            f"Age filter: posts newer than [bold]{max_age} days[/bold] (--any-age to lift)"
        )
    if fixture is not None:
        found = source.search_from_fixture(
            fixture.expanduser().resolve(),
            query=query,
            countries=countries,
            allow_remote=config.search.allow_remote,
            max_age_days=max_age,
        )
    else:
        console.print(f"Sweeping LinkedIn content for [bold]{query}[/bold]…")
        found = source.search_jobs(
            JobSearchQuery(
                query=query,
                limit=limit,
                countries=countries,
                allow_remote=config.search.allow_remote,
                copy_permalinks=copy_links,
                max_age_days=max_age,
            )
        )


    if not found:
        console.print("No relevant posts found.")
        raise typer.Exit(SUCCESS)

    try:
        candidate = load_profile(config.profile_path)
    except ProfileLoadError:
        candidate = None

    analyzer = RuleBasedJobAnalyzer()
    repo = JobRepository(session)
    registry = load_registry(default_portals_path(config.root))
    narrator = _narrator()
    narrator.phase(Phase.UPDATING_WORLD, f"{len(found)} recruiter posts")
    table = Table(title="LinkedIn post sweep")
    table.add_column("ID")
    table.add_column("Company")
    table.add_column("Role")
    table.add_column("ATS")
    table.add_column("Age")
    table.add_column("Where")
    table.add_column("Match")
    stored: list[str] = []
    for raw in found[:limit]:
        job = repo.upsert_external(raw)
        if candidate is not None:
            match = analyzer.analyze(candidate, job)
            repo.update_match_score(job.id, match.score)
            job.match_score = match.score
        write_job_json(job, config.output_dir)
        stored.append(job.id)
        ats = job.ats_kind or "-"
        score = f"{job.match_score:.0f}%" if job.match_score is not None else "-"
        table.add_row(
            job.id,
            job.company[:28],
            job.title[:40],
            ats,
            age_label(job.posted_at),
            detect_country(f"{job.title}\n{job.description}") or "?",
            score,
        )
        if register_portals and job.ats_url:
            domain = domain_from_url(job.ats_url)
            kind = AtsKind(job.ats_kind) if job.ats_kind else AtsKind.UNKNOWN
            existing = registry.find(domain)
            should_ask = existing is None and not yes
            if should_ask and not typer.confirm(
                f"New ATS portal {domain} ({kind.value}). Add to registry?",
                default=True,
            ):
                continue
            registry.upsert(
                domain=domain,
                ats_kind=kind,
                example_url=job.ats_url,
                seen=True,
            )
            # Always persist newly seen employment platforms
            remember_portal_from_url(
                config,
                job.ats_url,
                notes=f"learned from LinkedIn post job {job.id}",
            )
            _learn_company_knowledge(
                config,
                job,
                source=DiscoverySource.LINKEDIN_POST,
                narrator=narrator,
            )
    if register_portals:
        save_registry(registry, default_portals_path(config.root))
        console.print(f"Portal registry updated: {default_portals_path(config.root)}")
    console.print(table)
    console.print(
        f"Stored {len(stored)} jobs. Next: [bold]jobbot jobs match {stored[0]}[/bold] "
        f"→ [bold]jobbot application apply {stored[0]}[/bold]"
    )


@getonboard_app.command("prepare")
def getonboard_prepare(
    cold: Annotated[
        bool,
        typer.Option(
            "--cold",
            help="Ignore previous draft (cold start from profile.yaml only)",
        ),
    ] = False,
    use_llm: Annotated[
        bool,
        typer.Option(
            "--llm",
            help="Refine with LangChain (needs jobbot[llm] + OPENAI_API_KEY)",
        ),
    ] = False,
    seed: Annotated[
        Path | None,
        typer.Option(
            "--seed",
            help="Seed previous text from a file (old GoB paste = accumulated capital)",
        ),
    ] = None,
) -> None:
    """Maintain permanent GoB profile: cumulative refine by default (not cold replace)."""
    from jobbot.adapters.getonboard.client import GetOnBoardProfileClient

    seed_exp = seed.read_text(encoding="utf-8") if seed is not None else None
    path, result = GetOnBoardProfileClient.from_config(load_config()).prepare_package(
        cold=cold,
        use_llm=use_llm,
        seed_experiencia=seed_exp,
    )
    console.print(f"[green]Wrote permanent profile[/green] {path}")
    console.print(
        f"mode={result.mode}  kept={result.kept_paragraphs}  "
        f"added={result.added_paragraphs}  dropped={result.dropped_paragraphs}"
    )
    console.print(
        "También: output/getonboard/profile_permanent.yaml + sync_package.md "
        "(history/ guarda versiones previas)"
    )
    console.print(
        "Orden: 1) [bold]jobbot getonboard open-profile[/bold] "
        "(reemplaza textos viejos en el portal)  "
        "2) [bold]jobbot getonboard open-cvs[/bold]  "
        "3) postular."
    )


@getonboard_app.command("show-profile")
def getonboard_show_profile() -> None:
    """Show paths / char counts for the permanent GoB profile maintainer."""
    from jobbot.adapters.getonboard.draft import (
        EDUCATION_MAX,
        EXPERIENCE_MAX,
        load_permanent_profile,
        permanent_profile_md_path,
        permanent_profile_yaml_path,
    )

    config = load_config()
    fields = load_permanent_profile(config.output_dir)
    md = permanent_profile_md_path(config.output_dir)
    yml = permanent_profile_yaml_path(config.output_dir)
    if fields is None:
        console.print("No hay perfil permanente generado. Corre: jobbot getonboard prepare")
        raise typer.Exit(SUCCESS)
    console.print(f"Markdown: {md}")
    console.print(f"YAML:     {yml}")
    console.print(
        f"experiencia_y_perfil: {len(fields.experiencia_y_perfil)} / {EXPERIENCE_MAX}"
    )
    console.print(
        f"formacion_academica:  {len(fields.formacion_academica)} / {EDUCATION_MAX}"
    )
    console.print(f"headline: {fields.headline}")
    console.print(f"skills: {', '.join(fields.skills)}")


@getonboard_app.command("open-profile")
def getonboard_open_profile() -> None:
    """Open Get on Board 'Editar perfil' (HITL; paste permanent profile)."""
    from jobbot.adapters.getonboard.client import GetOnBoardProfileClient

    config = load_config()
    client = GetOnBoardProfileClient.from_config(config)
    # Ensure permanent texts exist before opening (cumulative refine)
    client.prepare_package()
    url = client.open_profile_edit()
    console.print(f"Opened {url}")
    console.print(
        "Reemplaza textos viejos con "
        "output/getonboard/profile_permanent.md"
    )


@getonboard_app.command("open-cvs")
def getonboard_open_cvs() -> None:
    """Open Get on Board profile area for 'Tus CVs' (HITL upload)."""
    from jobbot.adapters.getonboard.client import GetOnBoardProfileClient
    from jobbot.adapters.getonboard.package import PROFILE_EDIT_URL

    config = load_config()
    cv_pdf = config.output_dir / "base" / "cv.pdf"
    if not cv_pdf.is_file():
        cv_pdf = config.output_dir / "cv.pdf"
    url = GetOnBoardProfileClient.from_config(config).open_resumes()
    console.print(f"Opened {url}")
    console.print(
        "En la UI: ve a [bold]Tus CVs / Your resumes[/bold], "
        "sube el PDF y márcalo default."
    )
    if cv_pdf.is_file():
        console.print(f"PDF local: {cv_pdf}")
    else:
        console.print(
            "No hay PDF — genera con [bold]jobbot cv build[/bold] "
            "(queda en output/base/cv.pdf)."
        )
    console.print(f"(Misma base que editar perfil: {PROFILE_EDIT_URL})")


@getonboard_app.command("sync")
def getonboard_sync(
    apply_changes: Annotated[
        bool,
        typer.Option(
            "--apply",
            help="Open profile + CV editors (default: dry-run checklist only)",
        ),
    ] = False,
) -> None:
    """Maintain permanent GoB profile: regenerate texts; optionally open editors."""
    from jobbot.adapters.getonboard.client import GetOnBoardProfileClient

    client = GetOnBoardProfileClient.from_config(load_config())
    path, result = client.prepare_package()
    console.print(f"[green]Wrote[/green] {path}  (mode={result.mode})")
    if not apply_changes:
        console.print(
            "Dry-run del mantenedor (computación acumulativa). Revisa "
            "profile_permanent.md, luego:\n"
            "  jobbot cv build\n"
            "  jobbot getonboard sync --apply   # abre Editar perfil + Tus CVs\n"
            "  jobbot getonboard prepare --seed old.txt --llm  # refine con LLM"
        )
        return
    console.print("Abriendo Editar perfil (pega profile_permanent.md)…")
    console.print(client.open_profile_edit())
    console.print("Abriendo zona profesional (navega a Tus CVs)…")
    console.print(client.open_resumes())
    console.print(
        "HITL: reemplaza textos viejos, sube CV default, guarda. Luego postula."
    )


@getonboard_app.command("search")
def getonboard_search(
    query: Annotated[
        str | None,
        typer.Argument(help="Search query (default: the role in your own profile)"),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", help="Max results (1-50)")] = 20,
) -> None:
    """Search Get on Board (Spanish/LATAM) and store jobs locally."""
    from jobbot.adapters.getonboard.jobs import GetOnBoardJobSource
    from jobbot.jobs.sources import JobSearchQuery

    if limit < 1 or limit > 50:
        err_console.print("--limit must be between 1 and 50")
        raise typer.Exit(GENERIC_FAILURE)

    session, config = _session()
    if query is None:
        query = _profile_role_query(config)
        if query is None:
            err_console.print(
                "No query given and no role in the profile: "
                "pass the search terms or set personal.headline."
            )
            raise typer.Exit(GENERIC_FAILURE)
        console.print(f"[dim]Query from your profile: {query}[/dim]")
    source = GetOnBoardJobSource(config)
    console.print(f"Searching Get on Board for [bold]{query}[/bold]…")
    try:
        found = source.search_jobs(JobSearchQuery(query=query, limit=limit))
    except Exception as exc:
        err_console.print(f"[red]Get on Board search failed: {exc}[/red]")
        raise typer.Exit(GENERIC_FAILURE) from exc

    if not found:
        console.print("No jobs found.")
        raise typer.Exit(SUCCESS)

    try:
        candidate = load_profile(config.profile_path)
    except ProfileLoadError:
        candidate = None
    analyzer = RuleBasedJobAnalyzer()
    repo = JobRepository(session)
    table = Table(title="Get on Board results")
    table.add_column("ID")
    table.add_column("Company")
    table.add_column("Role")
    table.add_column("Where")
    table.add_column("Match")
    stored: list[str] = []
    for raw in found:
        job = repo.upsert_external(raw)
        if candidate is not None:
            match = analyzer.analyze(candidate, job)
            repo.update_match_score(job.id, match.score)
            job.match_score = match.score
        write_job_json(job, config.output_dir)
        stored.append(job.id)
        score = f"{job.match_score:.0f}%" if job.match_score is not None else "-"
        table.add_row(
            job.id,
            job.company[:24],
            job.title[:36],
            (job.location or "-")[:20],
            score,
        )
    console.print(table)
    console.print(
        f"Stored {len(stored)} jobs (portal getonbrd.com learned). "
        f"Next: [bold]jobbot jobs match {stored[0]}[/bold]"
    )


@torre_app.command("search")
def torre_search(
    query: Annotated[
        str | None,
        typer.Argument(help="Search query (default: the role in your own profile)"),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", help="Max results (1-50)")] = 20,
    remote: Annotated[bool, typer.Option("--remote", help="Only remote opportunities")] = False,
) -> None:
    """Search Torre (LATAM / remote) and store jobs locally."""
    from jobbot.adapters.torre.jobs import TorreJobSource
    from jobbot.jobs.sources import JobSearchQuery

    if limit < 1 or limit > 50:
        err_console.print("--limit must be between 1 and 50")
        raise typer.Exit(GENERIC_FAILURE)

    session, config = _session()
    if query is None:
        query = _profile_role_query(config)
        if query is None:
            err_console.print(
                "No query given and no role in the profile: "
                "pass the search terms or set personal.headline."
            )
            raise typer.Exit(GENERIC_FAILURE)
        console.print(f"[dim]Query from your profile: {query}[/dim]")

    narrator = _narrator()
    narrator.phase(Phase.RECEIVING_WORLD, f"Torre: {query}")
    source = TorreJobSource(config)
    try:
        found = source.search_jobs(JobSearchQuery(query=query, limit=limit, remote=remote))
    except Exception as exc:
        err_console.print(f"[red]Torre search failed: {exc}[/red]")
        raise typer.Exit(GENERIC_FAILURE) from exc

    if not found:
        console.print("No jobs found.")
        raise typer.Exit(SUCCESS)

    try:
        candidate = load_profile(config.profile_path)
    except ProfileLoadError:
        candidate = None
    analyzer = RuleBasedJobAnalyzer()
    repo = JobRepository(session)
    table = Table(title="Torre results")
    table.add_column("ID")
    table.add_column("Company")
    table.add_column("Role")
    table.add_column("Where")
    table.add_column("Match")
    stored: list[str] = []
    for raw in found:
        job = repo.upsert_external(raw)
        if candidate is not None:
            match = analyzer.analyze(candidate, job)
            repo.update_match_score(job.id, match.score)
            job.match_score = match.score
        write_job_json(job, config.output_dir)
        _learn_company_knowledge(config, job)
        stored.append(job.id)
        score = f"{job.match_score:.0f}%" if job.match_score is not None else "-"
        table.add_row(
            job.id,
            job.company[:24],
            job.title[:36],
            (job.location or "-")[:20],
            score,
        )
    console.print(table)
    console.print(
        f"Stored {len(stored)} jobs (portal torre.ai learned). "
        f"Next: [bold]jobbot jobs match {stored[0]}[/bold]"
    )


@portals_app.command("list")
def portals_list() -> None:
    """List known recruitment portals."""
    from jobbot.portals.registry import default_portals_path, load_registry

    config = load_config()
    registry = load_registry(default_portals_path(config.root))
    if not registry.portals:
        console.print("No portals registered yet. Run linkedin sweep or portals add.")
        return
    table = Table(title="Portal registry")
    table.add_column("Domain")
    table.add_column("ATS")
    table.add_column("Registered")
    table.add_column("Last seen")
    for entry in registry.portals:
        table.add_row(
            entry.domain,
            entry.ats_kind.value,
            "yes" if entry.registered else "no",
            entry.last_seen.isoformat(timespec="seconds") if entry.last_seen else "—",
        )
    console.print(table)


@portals_app.command("detect")
def portals_detect(
    url: Annotated[str, typer.Argument(help="Job or ATS URL")],
) -> None:
    """Detect ATS kind for a URL."""
    from jobbot.portals.detect import detect_ats
    from jobbot.portals.registry import domain_from_url

    kind = detect_ats(url)
    console.print(f"domain={domain_from_url(url)}  ats_kind={kind.value}")


@portals_app.command("add")
def portals_add(
    url: Annotated[str, typer.Argument(help="ATS URL or domain")],
    registered: Annotated[
        bool,
        typer.Option("--registered/--not-registered", help="You have an account there"),
    ] = False,
    notes: Annotated[str | None, typer.Option("--notes")] = None,
) -> None:
    """Add or update a portal in data/portals.yaml."""
    from jobbot.portals.detect import detect_ats
    from jobbot.portals.registry import (
        default_portals_path,
        domain_from_url,
        load_registry,
        save_registry,
    )

    config = load_config()
    path = default_portals_path(config.root)
    registry = load_registry(path)
    domain = domain_from_url(url)
    kind = detect_ats(url if "://" in url else f"https://{url}")
    entry = registry.upsert(
        domain=domain,
        ats_kind=kind,
        registered=registered,
        notes=notes,
        example_url=url if "://" in url else None,
        seen=True,
    )
    save_registry(registry, path)
    console.print(
        f"[green]Upserted[/green] {entry.domain} ({entry.ats_kind.value}) "
        f"registered={entry.registered}"
    )


def _learn_form_from_apply(config: JobbotConfig, url: str, company: str | None) -> None:
    """While you fill the form, record what it asks. Best effort: never blocks the apply."""
    from jobbot.portals.form_learn import learn_form_html

    try:
        html = _fetch_public_html(url)
        if html is None:
            return
        form = learn_form_html(html, url=url, company=company)
        if not form.readable:
            console.print(f"[dim]Form questions: {form.evidence}[/dim]")
            return
        _store_form_knowledge(config, form)
    except Exception:  # noqa: BLE001 — learning is a bonus, applying is the task
        console.print("[dim]Form questions: could not be read this time.[/dim]")
        return
    questions = form.screening_questions()
    narrator = _narrator()
    narrator.phase(Phase.RECEIVING_WORLD, f"{len(form.fields)} campos del formulario")
    if questions:
        console.print(f"[dim]This form asks {len(questions)} question(s) beyond your data:[/dim]")
        for question in questions[:6]:
            console.print(f"[dim]  • {question}[/dim]")
        console.print("[dim]Feeds jobbot cv advise.[/dim]")


@portals_app.command("form-learn")
def portals_form_learn(
    url: Annotated[str, typer.Argument(help="Application form URL (public page)")],
    fixture: Annotated[
        Path | None,
        typer.Option("--fixture", help="Read a saved HTML instead of fetching the URL"),
    ] = None,
    company: Annotated[
        str | None,
        typer.Option("--company", help="Who the form belongs to"),
    ] = None,
    fetch: Annotated[
        bool,
        typer.Option("--fetch", help="Allow one polite GET of the URL (obeys robots.txt)"),
    ] = False,
    save: Annotated[bool, typer.Option("--save/--no-save", help="Store what it learned")] = True,
) -> None:
    """Learn what an application form asks. Reads only; never fills or submits."""
    from jobbot.portals.form_learn import learn_form_html

    config = load_config()
    if fixture is not None:
        path = fixture.expanduser().resolve()
        if not path.is_file():
            err_console.print(f"[red]Fixture not found: {path}[/red]")
            raise typer.Exit(VALIDATION_FAILURE)
        html = path.read_text(encoding="utf-8")
    elif fetch:
        fetched = _fetch_public_html(url)
        if fetched is None:
            raise typer.Exit(GENERIC_FAILURE)
        html = fetched
    else:
        err_console.print(
            "Reading a live form needs [bold]--fetch[/bold] (one GET, obeys robots.txt), "
            "or pass [bold]--fixture PATH[/bold] with saved HTML."
        )
        raise typer.Exit(VALIDATION_FAILURE)

    form = learn_form_html(html, url=url, company=company)
    _print_form_knowledge(form)
    if save and form.readable:
        stored = _store_form_knowledge(config, form)
        console.print(f"Learned (candidate knowledge): {stored}")
    elif save:
        console.print("[yellow]Nothing stored: the form could not be read.[/yellow]")


def _fetch_public_html(url: str) -> str | None:
    """One polite GET, robots.txt respected. Returns None when we must not look."""
    from jobbot.companies.oneshot import RobotsPolicy, RobotsVerdict, UrllibFetcher

    fetcher = UrllibFetcher()
    verdict = RobotsPolicy(fetcher).verdict(url)
    if verdict is RobotsVerdict.DISALLOWED:
        err_console.print(f"[yellow]robots.txt disallows {url} — not fetched.[/yellow]")
        return None
    if verdict is RobotsVerdict.HOST_REFUSED:
        err_console.print(
            f"[yellow]{url} would not serve its robots.txt — staying out "
            "(unknown, not empty).[/yellow]"
        )
        return None
    result = fetcher.fetch(url)
    if not result.ok:
        err_console.print(f"[yellow]{url} answered HTTP {result.status}.[/yellow]")
        return None
    return result.html


def _print_form_knowledge(form: Any) -> None:
    from jobbot.portals.form_learn import FieldKind

    console.print(f"[bold]{form.url}[/bold]  ats={form.ats.value}")
    if not form.readable:
        console.print(f"[yellow]{form.evidence}[/yellow]")
        console.print("Tip: open the page, save the HTML, and pass it with --fixture.")
        return
    table = Table(title="What this form asks")
    table.add_column("Question")
    table.add_column("Kind")
    table.add_column("Req", justify="center")
    table.add_column("Choices")
    for field in form.fields:
        mark = "yes" if field.required else ""
        choices = ", ".join(field.options[:4]) if field.options else ""
        if field.kind is FieldKind.FILE and field.accepts:
            choices = " ".join(field.accepts)
        table.add_row(field.label[:52], field.kind.value, mark, choices[:34])
    console.print(table)
    questions = form.screening_questions()
    if questions:
        console.print(f"Questions your CV has to answer ({len(questions)}):")
        for question in questions:
            console.print(f"  • {question}")


def _store_form_knowledge(config: JobbotConfig, form: Any) -> Path:
    from jobbot.portals.form_learn import (
        default_form_knowledge_path,
        load_form_knowledge,
        save_form_knowledge,
        upsert_form,
    )

    path = default_form_knowledge_path(config.root)
    forms = upsert_form(load_form_knowledge(path), form)
    return save_form_knowledge(forms, path)


# ── companies (collaborative career-platform knowledge) ──────────────────────


def _narrator(quiet: bool = False) -> Narrator:
    """Phase narration for the long loops (dim lines, local stdout only)."""
    return Narrator(sink=lambda line: console.print(f"[dim]{line}[/dim]"), quiet=quiet)


def _companies_registry(config: JobbotConfig) -> tuple[CompanyRegistry, Path]:
    from jobbot.companies.registry import default_companies_path, load_companies

    path = default_companies_path(config.root)
    return load_companies(path), path


def _profile_role_query(config: JobbotConfig) -> str | None:
    """The role to search for comes from the profile, not from a literal default.

    A default query hardcodes one career into the tool; the candidate's own
    headline (or latest held title) is the only honest guess.
    """
    try:
        candidate = load_profile(config.profile_path)
    except Exception:  # noqa: BLE001 — no profile yet is a normal first run
        return None
    headline = (candidate.personal.headline or "").strip()
    if headline:
        return re.split(r"\s*[|/·–—]\s*", headline)[0].strip() or None
    for exp in candidate.experience:
        if exp.title.strip():
            return exp.title.strip()
    return None


def _learn_company_knowledge(
    config: JobbotConfig,
    job: JobPosting,
    *,
    source: DiscoverySource = DiscoverySource.JOB_SOURCE,
    narrator: Narrator | None = None,
) -> None:
    """Record the company↔portal relation behind a stored job (candidate knowledge)."""
    from jobbot.companies.learn import learn_from_job

    result = learn_from_job(config, job, source=source)
    if result is None:
        return
    voice = narrator or _narrator()
    verb = "learned" if result.created else "confirmed"
    voice.note(
        f"{verb} {result.company_id}: {result.url} "
        f"({result.site_type.value}, ats={result.ats}) — candidate"
    )
    if result.conflict:
        err_console.print(f"[yellow]Contradiction:[/yellow] {result.conflict}")


@companies_app.command("detect")
def companies_detect(
    url: Annotated[str, typer.Argument(help="Career page, ATS or job URL")],
    resolve: Annotated[
        bool,
        typer.Option("--resolve/--no-resolve", help="Follow redirects before classifying"),
    ] = False,
) -> None:
    """Classify a URL (posting / career portal / ATS / redirect). Writes nothing."""
    from jobbot.companies.discovery import career_root_url, classify_url
    from jobbot.companies.urls import PrivateRouteRejected, company_hint_from_url

    try:
        found = classify_url(url, resolve=resolve)
    except PrivateRouteRejected as exc:
        err_console.print(f"[red]Not shareable company knowledge:[/red] {exc}")
        raise typer.Exit(VALIDATION_FAILURE) from exc
    table = Table(title="URL classification")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("url", found.url)
    table.add_row("domain", found.domain)
    table.add_row("site_type", found.site_type.value)
    table.add_row("ats", found.ats.value)
    table.add_row("career_root", career_root_url(found.url, found.ats))
    table.add_row("redirects_to", found.redirects_to or "—")
    table.add_row("evidence", found.evidence or "(none — ats stays unknown)")
    table.add_row("company_hint", company_hint_from_url(found.url))
    console.print(table)


@companies_app.command("learn")
def companies_learn(
    url: Annotated[str, typer.Argument(help="Career portal / ATS URL")],
    company: Annotated[
        str | None,
        typer.Option("--company", help="Company name (defaults to a hint from the URL)"),
    ] = None,
    country: Annotated[str | None, typer.Option("--country", help="ISO code, e.g. CL")] = None,
    resolve: Annotated[
        bool,
        typer.Option("--resolve/--no-resolve", help="Follow redirects before classifying"),
    ] = False,
    verify: Annotated[
        bool,
        typer.Option("--verify", help="Promote straight to active (you confirm it is right)"),
    ] = False,
) -> None:
    """Register a company/portal relation you found yourself (candidate by default)."""
    from jobbot.companies.learn import learn_from_url
    from jobbot.companies.models import DiscoverySource
    from jobbot.companies.registry import save_companies
    from jobbot.companies.urls import PrivateRouteRejected, company_hint_from_url

    config = load_config()
    registry, path = _companies_registry(config)
    narrator = _narrator()
    narrator.phase(Phase.UPDATING_WORLD, "company career platforms")
    try:
        outcome = learn_from_url(
            registry,
            company=company or company_hint_from_url(url),
            url=url,
            source=DiscoverySource.USER_OBSERVATION,
            country=country,
            resolve=resolve,
        )
    except PrivateRouteRejected as exc:
        err_console.print(f"[red]Not shareable company knowledge:[/red] {exc}")
        raise typer.Exit(VALIDATION_FAILURE) from exc
    if outcome is None:
        console.print(
            "[yellow]Not company-specific[/yellow] (job board or unclear URL); nothing stored."
        )
        raise typer.Exit(SUCCESS)
    if outcome.conflict and outcome.site is None:
        err_console.print(f"[yellow]Duplicate:[/yellow] {outcome.conflict}")
        raise typer.Exit(SUCCESS)
    assert outcome.site is not None
    if verify:
        registry.promote(outcome.company.id, url=outcome.site.url)
    save_companies(registry, path)
    verb = "Added" if outcome.created_site else "Merged observation into"
    narrator.note(
        f"{verb} {outcome.site.url} → company={outcome.company.id} "
        f"type={outcome.site.site_type.value} ats={outcome.site.ats.value} "
        f"status={outcome.site.status.value} confidence={outcome.site.confidence}"
    )
    if outcome.conflict:
        err_console.print(f"[yellow]Contradiction:[/yellow] {outcome.conflict}")
    if not verify:
        console.print(
            f"Candidate stored. Confirm with: [bold]jobbot companies promote "
            f"{outcome.company.id} --site {outcome.site.url}[/bold]"
        )


@companies_app.command("list")
def companies_list(
    status: Annotated[
        str,
        typer.Option("--status", help="candidate | active | stale | rejected | all"),
    ] = "all",
) -> None:
    """List known companies and their career platforms."""
    from jobbot.companies.models import KnowledgeStatus

    config = load_config()
    registry, path = _companies_registry(config)
    if not registry.companies:
        console.print(
            "No company knowledge yet. Try [bold]jobbot companies learn URL --company NAME[/bold] "
            "or [bold]jobbot companies discover data/companies-cl.example.yaml[/bold]."
        )
        return
    wanted: set[str] | None = None
    if status != "all":
        if status not in {s.value for s in KnowledgeStatus}:
            err_console.print(f"[red]Invalid --status {status!r}[/red]")
            raise typer.Exit(GENERIC_FAILURE)
        wanted = {status}
    table = Table(title=f"Company career platforms ({path.name})")
    table.add_column("Company")
    table.add_column("Country")
    table.add_column("Career site")
    table.add_column("Type")
    table.add_column("ATS")
    table.add_column("Status")
    table.add_column("Conf.")
    rows = 0
    for record in registry.companies:
        for site in record.career_sites:
            if wanted is not None and site.status.value not in wanted:
                continue
            table.add_row(
                record.id,
                record.country or "—",
                site.url[:52],
                site.site_type.value,
                site.ats.value,
                site.status.value,
                str(site.confidence),
            )
            rows += 1
    if rows == 0:
        console.print(f"No career sites with status {status!r}.")
        return
    console.print(table)


@companies_app.command("show")
def companies_show(
    company: Annotated[str, typer.Argument(help="Company id or name")],
) -> None:
    """Show one company with every portal, observation and contradiction."""
    config = load_config()
    registry, _ = _companies_registry(config)
    record = registry.find_company(company)
    if record is None:
        err_console.print(f"[red]Unknown company {company!r}[/red]")
        raise typer.Exit(VALIDATION_FAILURE)
    console.print(
        Panel(
            f"[bold]{record.name}[/bold] ({record.id})\n"
            f"country: {record.country or '—'}  sector: {record.sector or '—'}\n"
            f"domains: {', '.join(record.domains) or '—'}",
            title="Company",
        )
    )
    for site in record.career_sites:
        verified = site.last_verified.date().isoformat() if site.last_verified else "—"
        lines = [
            f"type: {site.site_type.value}   ats: {site.ats.value}   status: {site.status.value}",
            f"first_seen: {site.first_seen.date().isoformat()}   last_verified: {verified}",
        ]
        if site.reached_from:
            lines.append(f"reached_from: {site.reached_from}")
        lines.append(f"confidence: {site.confidence} independent source(s)")
        for obs in site.observations:
            lines.append(
                f"  · {obs.checked_at.date().isoformat()} {obs.source.value}: "
                f"{obs.evidence or '(no technical evidence)'}"
            )
        for conflict in site.conflicts:
            lines.append(f"  ! {conflict}")
        console.print(Panel("\n".join(lines), title=site.url))


@companies_app.command("signup")
def companies_signup(
    company: Annotated[str, typer.Argument(help="Company id or name (already in the registry)")],
    open_page: Annotated[
        bool,
        typer.Option("--open/--no-open", help="Open the portal in your browser"),
    ] = True,
    site_url: Annotated[
        str | None,
        typer.Option("--site", help="Which career site, when the company has several"),
    ] = None,
    apply_fill: Annotated[
        bool,
        typer.Option(
            "--apply",
            help="Fill known fields from profile.yaml (stops before password/terms/submit)",
        ),
    ] = False,
    cdp_url: Annotated[
        str | None,
        typer.Option("--cdp", help="CDP endpoint URL (e.g. http://127.0.0.1:9222)"),
    ] = None,
) -> None:
    """Open a company portal and list what registering will ask. Creates nothing.
    
    With --apply, fills fields profile.yaml already answers and may attach the built CV.
    Stops before password, terms, CAPTCHA/2FA, and final create/submit."""
    from jobbot.companies.signup import (
        AccountNeed,
        screening_to_prepare,
        signup_sheet,
        signup_target,
    )
    from jobbot.portals.form_learn import default_form_knowledge_path, load_form_knowledge

    config = load_config()
    registry, _ = _companies_registry(config)
    record = registry.find_company(company)
    if record is None:
        err_console.print(f"[red]Unknown company {company!r}[/red]")
        err_console.print("Learn it first: [bold]jobbot companies learn URL --company NAME[/bold]")
        raise typer.Exit(VALIDATION_FAILURE)
    sites = record.career_sites
    if site_url:
        sites = [site for site in sites if site.url == site_url]
    if not sites:
        err_console.print(f"[red]No career site stored for {record.name}[/red]")
        raise typer.Exit(VALIDATION_FAILURE)
    site = sites[0]
    target = signup_target(site)

    try:
        candidate = load_profile(config.profile_path)
    except ProfileLoadError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(VALIDATION_FAILURE) from exc

    forms = load_form_knowledge(default_form_knowledge_path(config.root))
    form = next(
        (f for f in forms if f.url.startswith(site.url) or site.url.startswith(f.url)),
        None,
    )

    console.print(
        Panel(
            f"[bold]{record.name}[/bold] ({record.id})\n"
            f"{target.url}\n"
            f"ats: {site.ats.value}   account: {target.need.value}\n\n{target.note}",
            title="Registration (you complete it)",
        )
    )
    table = Table(title="Have this at hand" + ("  (from the form we saw)" if form else ""))
    table.add_column("The portal asks")
    table.add_column("Your profile answers")
    table.add_column("From")
    for item in signup_sheet(candidate, form=form):
        value = item.value or "[yellow]you decide[/yellow]"
        table.add_row(item.label[:40], value[:46], item.source[:34])
    console.print(table)
    for question in screening_to_prepare(form):
        console.print(f"  • decide beforehand: {question}")
    console.print(
        "[dim]JobBot does not create the account, does not set a password and does not "
        "accept terms for you.[/dim]"
    )
    if target.need is AccountNeed.NOT_NEEDED:
        console.print("You may not need an account at all — check before registering.")

    # Handle --apply: fill known fields from profile.yaml
    if apply_fill:
        from jobbot.adapters.ats.signup_fill import build_fill_plan, fill_signup_with_session
        from jobbot.browser.session import BrowserSession

        # Resolve CV path
        cv_path = config.root / "output" / "base" / "cv.pdf"

        plan = build_fill_plan(candidate, target.url, target.need, form, cv_path)

        console.print("\n[bold]Fill Plan:[/bold]")
        filled_list = ", ".join(plan.fields_to_fill) if plan.fields_to_fill else "none"
        console.print(f"  • Will fill: {filled_list}")
        manual_list = ", ".join(plan.needs_manual[:3])
        ellipsis = "..." if len(plan.needs_manual) > 3 else ""
        console.print(f"  • Requires manual: {manual_list}{ellipsis}")
        if plan.can_attach_cv:
            console.print(f"  • Will attach CV: {plan.cv_path}")

        if not plan.fields_to_fill and not plan.can_attach_cv:
            console.print("[yellow]No fields can be filled automatically.[/yellow]")
        else:
            console.print("\n[bold yellow]Opening browser to fill form...[/bold yellow]")
            console.print("[dim]Stop before password, terms, CAPTCHA/2FA and submit.[/dim]\n")

            browser_data_dir = config.root / "browser-data" / "signup"
            with BrowserSession(
                browser_data_dir,
                headless=False,
                cdp_url=cdp_url,
            ) as session:
                result = fill_signup_with_session(session, target.url, candidate, form, cv_path)

                console.print("\n[bold green]Filled:[/bold green]")
                if result.filled_fields:
                    for field in result.filled_fields:
                        console.print(f"  ✓ {field}")
                else:
                    console.print(
                        "  [yellow]No fields were filled "
                        "(may need manual form inspection)[/yellow]"
                    )

                console.print(f"\n[bold]Stopped at:[/bold] {result.stopped_at}")
                console.print(
                    "\n[bold yellow]Complete the remaining fields yourself:[/bold yellow]"
                )
                for manual in result.plan.needs_manual[:5]:
                    console.print(f"  • {manual}")

                input("\nPress Enter when you're done (browser will close)...")

    elif open_page:
        from jobbot.adapters.ats.apply import open_ats_in_browser

        open_ats_in_browser(target.url)
        console.print(f"Opened {target.url}")


@companies_app.command("promote")
def companies_promote(
    company: Annotated[str, typer.Argument(help="Company id or name")],
    site: Annotated[
        str | None,
        typer.Option("--site", help="Promote only this career URL"),
    ] = None,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
) -> None:
    """Promote candidate knowledge to active (the only way it becomes truth)."""
    from jobbot.companies.models import KnowledgeStatus
    from jobbot.companies.registry import save_companies
    from jobbot.companies.urls import canonical_key

    config = load_config()
    registry, path = _companies_registry(config)
    record = registry.find_company(company)
    if record is None:
        err_console.print(f"[red]Unknown company {company!r}[/red]")
        raise typer.Exit(VALIDATION_FAILURE)
    targets = [
        s
        for s in record.career_sites
        if s.status != KnowledgeStatus.REJECTED
        and (site is None or s.key == canonical_key(site))
    ]
    if not targets:
        console.print("Nothing to promote.")
        raise typer.Exit(SUCCESS)
    narrator = _narrator()
    narrator.phase(Phase.RECEIVING_WORLD, f"company {record.id}", may_ask=not yes)
    promoted = 0
    for target in targets:
        narrator.note(
            f"{target.url} type={target.site_type.value} ats={target.ats.value} "
            f"evidence={target.observations[-1].evidence if target.observations else '—'}"
        )
        if not yes and not typer.confirm(f"Promote {target.url} to active?", default=True):
            continue
        registry.promote(record.id, url=target.url)
        promoted += 1
    if promoted:
        save_companies(registry, path)
    console.print(f"[green]Promoted[/green] {promoted} career site(s) → {path}")


@companies_app.command("reject")
def companies_reject(
    company: Annotated[str, typer.Argument(help="Company id or name")],
    site: Annotated[str, typer.Option("--site", help="Career URL to reject")],
) -> None:
    """Mark a discovered portal as wrong so it stops coming back."""
    from jobbot.companies.registry import save_companies

    config = load_config()
    registry, path = _companies_registry(config)
    rejected = registry.reject(company, url=site)
    if rejected is None:
        err_console.print(f"[red]No stored site {site} for {company!r}[/red]")
        raise typer.Exit(VALIDATION_FAILURE)
    save_companies(registry, path)
    console.print(f"[yellow]Rejected[/yellow] {rejected.url}")


@companies_app.command("discover")
def companies_discover(
    seeds_file: Annotated[Path, typer.Argument(help="YAML list of companies to seed")],
    out: Annotated[
        Path | None,
        typer.Option("--out", help="Where to write candidates (default: output/discovery/…)"),
    ] = None,
    limit: Annotated[int | None, typer.Option("--limit", help="Max companies to probe")] = None,
    search_results: Annotated[
        Path | None,
        typer.Option("--search-results", help="YAML with already-obtained web search hits"),
    ] = None,
    delay: Annotated[
        float,
        typer.Option("--delay", help="Seconds between HTTP requests (be polite)"),
    ] = 1.0,
) -> None:
    """One-shot: seed candidate career portals for a company list (never canonical)."""
    from jobbot.companies.oneshot import (
        CompanyPortalCandidate,
        CompanySeed,
        UrllibFetcher,
        group_candidates,
        load_search_hits,
        load_seeds,
        run_oneshot,
        write_candidates,
    )
    from jobbot.companies.registry import generated_candidates_path

    config = load_config()
    path = seeds_file.expanduser().resolve()
    if not path.is_file():
        err_console.print(f"[red]Seed file not found: {path}[/red]")
        raise typer.Exit(VALIDATION_FAILURE)
    try:
        seeds = load_seeds(path)
    except (ValueError, yaml.YAMLError) as exc:
        err_console.print(f"[red]Invalid seed file:[/red] {exc}")
        raise typer.Exit(VALIDATION_FAILURE) from exc
    hits = load_search_hits(search_results.expanduser().resolve()) if search_results else None

    narrator = _narrator()
    narrator.phase(Phase.EXPLORING, f"{len(seeds)} companies")

    def on_company(seed: CompanySeed, found: list[CompanyPortalCandidate]) -> None:
        narrator.note(f"{seed.name}: {len(found)} candidate portal(s)")

    report = run_oneshot(
        seeds,
        UrllibFetcher(delay=delay),
        search_hits=hits,
        limit=limit,
        on_company=on_company,
    )
    target = (out.expanduser().resolve() if out else generated_candidates_path(config.output_dir))
    write_candidates(report.candidates, target)
    narrator.phase(Phase.SURFACING, f"{len(report.candidates)} portal(s)")
    narrator.outcome(
        ExplorationOutcome(
            found=len({candidate.company_id for candidate in report.candidates}),
            refused=len(report.companies_blocked),
            unknown=len(report.companies_without_portal),
        )
    )
    console.print(
        f"Probed {report.companies_seen} companies with {report.requests_made} requests → "
        f"{len(report.candidates)} candidate portal(s)."
    )
    groups = group_candidates(report.candidates)
    if rows := groups.rows():
        table = Table(title="Portals found, grouped")
        table.add_column("Axis")
        table.add_column("Group")
        table.add_column("Portals", justify="right")
        table.add_column("Companies", justify="right")
        for axis, label, portals, companies in rows:
            table.add_row(axis, label, str(portals), str(companies))
        console.print(table)
    if report.companies_robots_skipped:
        console.print(
            "[yellow]Skipped by robots.txt (omitted, not absent):[/yellow] "
            + ", ".join(report.companies_robots_skipped[:10])
        )
    if report.companies_without_portal:
        console.print(
            "No public portal found for: "
            + ", ".join(report.companies_without_portal[:10])
        )
    if report.companies_blocked:
        console.print(
            "[yellow]Refused our requests (unknown, not absent):[/yellow] "
            + ", ".join(report.companies_blocked[:10])
        )
        console.print("Give those a hand: [bold]companies learn URL --company NAME[/bold]")
    console.print(f"Candidates (not truth yet): {target}")
    console.print(f"Next: [bold]jobbot companies import {target}[/bold]")


@companies_app.command("import")
def companies_import(
    candidates_file: Annotated[Path, typer.Argument(help="Generated candidates YAML")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Import without asking")] = False,
) -> None:
    """Merge oneshot candidates into the registry (still candidate, never active)."""
    from jobbot.companies.oneshot import CompanyPortalCandidate, import_candidates, load_candidates
    from jobbot.companies.registry import save_companies

    config = load_config()
    path = candidates_file.expanduser().resolve()
    if not path.is_file():
        err_console.print(f"[red]Candidates file not found: {path}[/red]")
        raise typer.Exit(VALIDATION_FAILURE)
    candidates = load_candidates(path)
    registry, registry_path = _companies_registry(config)
    narrator = _narrator()
    narrator.phase(Phase.UPDATING_WORLD, f"{len(candidates)} candidates", may_ask=not yes)

    def confirm(candidate: CompanyPortalCandidate) -> bool:
        narrator.note(
            f"{candidate.company}: {candidate.career_url} "
            f"type={candidate.site_type.value} ats={candidate.ats.value} "
            f"evidence={candidate.evidence or '—'}"
        )
        if yes:
            return True
        return typer.confirm("Keep as candidate knowledge?", default=True)

    outcomes = import_candidates(registry, candidates, confirm=confirm)
    save_companies(registry, registry_path)
    created = sum(1 for o in outcomes if o.created_site)
    merged = sum(1 for o in outcomes if o.merged)
    conflicts = [o.conflict for o in outcomes if o.conflict]
    console.print(
        f"[green]Imported[/green] {created} new, merged {merged} into existing → {registry_path}"
    )
    for conflict in conflicts:
        err_console.print(f"[yellow]Conflict:[/yellow] {conflict}")
    console.print("Promote what you verified: [bold]jobbot companies promote COMPANY[/bold]")


@companies_app.command("export")
def companies_export(
    out: Annotated[
        Path | None,
        typer.Option("--out", help="Destination file (default: output/discovery/…)"),
    ] = None,
) -> None:
    """Write a shareable snapshot: active entries only, no candidate PII."""
    from jobbot.companies.registry import shareable_payload, shared_export_path

    config = load_config()
    registry, _ = _companies_registry(config)
    payload = shareable_payload(registry)
    target = out.expanduser().resolve() if out else shared_export_path(config.output_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    companies = payload.get("companies")
    count = len(companies) if isinstance(companies, list) else 0
    console.print(f"[green]Exported[/green] {count} company(ies) with active portals → {target}")


@companies_app.command("sites")
def companies_sites(
    include_candidates: Annotated[
        bool,
        typer.Option("--include-candidates", help="Also list unverified knowledge"),
    ] = False,
) -> None:
    """Career portals reusable by later job discovery."""
    from jobbot.companies.registry import active_career_sites

    config = load_config()
    registry, _ = _companies_registry(config)
    pairs = active_career_sites(registry, include_candidates=include_candidates)
    if not pairs:
        console.print("No reusable career sites yet (promote some candidates first).")
        return
    for record, site in pairs:
        console.print(f"{record.id}\t{site.ats.value}\t{site.url}")


@browser_app.command("chrome-debug")
def browser_chrome_debug(
    port: Annotated[int, typer.Option("--port", help="Remote debugging port")] = 9222,
    site: Annotated[
        str,
        typer.Option("--site", help="indeed | linkedin | gmail | getonboard (profile + start URL)"),
    ] = "indeed",
    launch: Annotated[
        bool,
        typer.Option("--launch/--print-only", help="Launch Chrome (default) or only print argv"),
    ] = True,
) -> None:
    """Open a normal Chrome with CDP so challenges can be completed by hand."""
    import subprocess

    from jobbot.browser.cdp import cdp_http_url, chrome_debug_argv
    from jobbot.browser.sessions import (
        KNOWN_SITES,
        ProfileBusyError,
        ensure_profile_free,
        site_spec,
    )

    config = load_config()
    spec = site_spec(site)
    if spec is None:
        known = "|".join(KNOWN_SITES)
        err_console.print(f"[red]Unknown --site {site!r} (use {known})[/red]")
        raise typer.Exit(GENERIC_FAILURE)
    site_key = spec.site
    profile_dir = config.root / "browser-data" / spec.cdp_profile
    start_url = spec.start_url
    tip = spec.next_command.format(cdp=cdp_http_url(port))
    profile_dir.mkdir(parents=True, exist_ok=True)
    argv = chrome_debug_argv(profile_dir=profile_dir, port=port, start_url=start_url)
    url = cdp_http_url(port)
    console.print("[bold]HITL Chrome (no CAPTCHA bypass)[/bold]")
    console.print("1. Close any JobBot-automated Chrome/Chromium windows for this site.")
    console.print(f"2. In this Chrome window, log in / complete challenges for {site_key}.")
    console.print(f"3. Then: [bold]{tip}[/bold]")
    console.print("Command:")
    console.print(" ".join(argv))
    if not launch:
        return
    try:
        ensure_profile_free(profile_dir)
    except ProfileBusyError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(GENERIC_FAILURE) from exc
    subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # noqa: S603
    console.print(f"[green]Launched[/green] Chrome with CDP at {url}")


@browser_app.command("sessions")
def browser_sessions(
    site: Annotated[
        list[str] | None,
        typer.Option("--site", help="Limit to these sites (repeatable)"),
    ] = None,
    port: Annotated[
        list[int] | None,
        typer.Option("--port", help="Debugging ports to probe (repeatable)"),
    ] = None,
) -> None:
    """Report which browser sessions JobBot can reach (read-only; never attaches)."""
    from jobbot.browser.sessions import DEFAULT_PORTS, SessionStatus, inspect_sessions

    config = load_config()
    states = inspect_sessions(
        config.root,
        sites=site or None,
        ports=tuple(port) if port else DEFAULT_PORTS,
    )
    table = Table(title="Browser sessions")
    table.add_column("Site")
    table.add_column("Status")
    table.add_column("Endpoint")
    table.add_column("Evidence")
    for state in states:
        colour = {
            SessionStatus.READY: "green",
            SessionStatus.NEEDS_LOGIN: "yellow",
            SessionStatus.PROFILE_BUSY: "red",
        }.get(state.status, "white")
        table.add_row(
            state.site,
            f"[{colour}]{state.status.value}[/{colour}]",
            state.cdp_url or "-",
            state.evidence,
        )
    console.print(table)
    for state in states:
        if state.hint:
            console.print(f"  {state.site}: {state.hint}")


# ── ops (local failure observability) ────────────────────────────────────────


@ops_app.command("failures")
def ops_failures(
    status: Annotated[
        str | None,
        typer.Option("--status", help="Filter: new|triaged|fixed|wontfix (default: new)"),
    ] = "new",
    all_statuses: Annotated[
        bool,
        typer.Option("--all", help="List all statuses"),
    ] = False,
    limit: Annotated[int, typer.Option("--limit", help="Max rows")] = 50,
) -> None:
    """List stored failures (grouped by fingerprint)."""
    from jobbot.ops.failures import STATUSES, group_by_fingerprint, list_failures

    if all_statuses:
        status_filter: str | None = None
    else:
        status_filter = status
        if status_filter is not None and status_filter not in STATUSES:
            err_console.print(f"[red]Invalid --status {status_filter!r}[/red]")
            raise typer.Exit(GENERIC_FAILURE)

    session, _ = _session()
    records = list_failures(session, status=status_filter, limit=limit)
    if not records:
        console.print("No failures stored.")
        raise typer.Exit(SUCCESS)

    table = Table(title="ops failures")
    table.add_column("id")
    table.add_column("fp")
    table.add_column("n")
    table.add_column("component")
    table.add_column("exit")
    table.add_column("status")
    table.add_column("message")
    for fingerprint, group in group_by_fingerprint(records):
        head = group[0]
        msg = head.message.splitlines()[0] if head.message else head.error_class
        if len(msg) > 60:
            msg = msg[:57] + "…"
        table.add_row(
            head.id,
            fingerprint,
            str(len(group)),
            head.component,
            str(head.exit_code),
            head.status,
            msg,
        )
    console.print(table)
    console.print("Detail: [bold]jobbot ops failure show Fxxxx[/bold]")


@ops_failure_app.command("show")
def ops_failure_show(
    failure_id: Annotated[str, typer.Argument(help="Failure id, e.g. F0001")],
) -> None:
    """Show one failure record."""
    from jobbot.ops.failures import get_failure

    session, config = _session()
    record = get_failure(session, failure_id)
    if record is None:
        err_console.print(f"[red]Unknown failure {failure_id}[/red]")
        raise typer.Exit(GENERIC_FAILURE)
    console.print(
        Panel(
            f"[bold]{record.id}[/bold]  fingerprint={record.fingerprint}\n"
            f"component={record.component}  exit={record.exit_code}  "
            f"status={record.status}\n"
            f"command: {record.command}\n"
            f"error: {record.error_class}: {record.message}\n"
            f"ts: {record.ts.isoformat()}\n"
            f"issue: {record.issue_url or '(none)'}\n\n"
            f"context:\n{json.dumps(record.context, indent=2, ensure_ascii=False)}\n\n"
            f"traceback:\n{record.traceback or '(none)'}",
            title="failure",
        )
    )
    mirror = config.output_dir / "ops" / "failures" / f"{record.id}.json"
    if mirror.is_file():
        console.print(f"Mirror: {mirror}")


@ops_failure_app.command("triage")
def ops_failure_triage(
    failure_id: Annotated[str, typer.Argument(help="Failure id, e.g. F0001")],
    status: Annotated[
        str,
        typer.Option("--status", help="new|triaged|fixed|wontfix"),
    ] = "triaged",
) -> None:
    """Update failure status after review / fix."""
    from jobbot.ops.failures import STATUSES, mark_status

    if status not in STATUSES:
        err_console.print(f"[red]Invalid --status {status!r}[/red]")
        raise typer.Exit(GENERIC_FAILURE)
    session, _ = _session()
    record = mark_status(session, failure_id, status)
    if record is None:
        err_console.print(f"[red]Unknown failure {failure_id}[/red]")
        raise typer.Exit(GENERIC_FAILURE)
    console.print(f"[green]{record.id}[/green] → status={record.status}")


@ops_failure_app.command("issue")
def ops_failure_issue(
    failure_id: Annotated[str, typer.Argument(help="Failure id, e.g. F0001")],
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation"),
    ] = False,
) -> None:
    """Create a GitHub issue from a failure (HITL; uses gh). Never auto-fires on crash."""
    import subprocess

    from jobbot.ops.failures import get_failure, issue_body, issue_title, mark_status

    session, _ = _session()
    record = get_failure(session, failure_id)
    if record is None:
        err_console.print(f"[red]Unknown failure {failure_id}[/red]")
        raise typer.Exit(GENERIC_FAILURE)
    if record.issue_url:
        console.print(f"Already linked: {record.issue_url}")
        raise typer.Exit(SUCCESS)

    title = issue_title(record)
    body = issue_body(record)
    console.print(Panel(f"{title}\n\n{body}", title="proposed GitHub issue"))
    if not yes and not typer.confirm("Create GitHub issue with gh?"):
        console.print("Aborted.")
        raise typer.Exit(SUCCESS)

    proc = subprocess.run(  # noqa: S603
        ["gh", "issue", "create", "--title", title, "--body", body],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        err_console.print(f"[red]gh failed:[/red] {proc.stderr or proc.stdout}")
        raise typer.Exit(GENERIC_FAILURE)
    url = (proc.stdout or "").strip()
    mark_status(session, failure_id, "triaged", issue_url=url or None)
    console.print(f"[green]Created[/green] {url or '(see gh output)'}")


@ops_app.command("loop")
def ops_loop(
    cmd: Annotated[
        str,
        typer.Option("--cmd", help="Loop step: getonboard-prepare | getonboard-sync"),
    ] = "getonboard-prepare",
    interval: Annotated[
        float,
        typer.Option("--interval", help="Seconds between ticks"),
    ] = 300.0,
    fail_fast: Annotated[
        bool,
        typer.Option("--fail-fast", help="Stop on first failure"),
    ] = False,
    max_ticks: Annotated[
        int | None,
        typer.Option("--max-ticks", help="Stop after N ticks (default: forever)"),
    ] = None,
) -> None:
    """Run a maintainer step continuously; persist Fxxxx on crash and continue."""
    from jobbot.ops.loop import LOOP_COMMANDS, run_loop

    if cmd not in LOOP_COMMANDS:
        err_console.print(
            f"[red]Unknown --cmd {cmd!r}[/red]; expected one of {sorted(LOOP_COMMANDS)}"
        )
        raise typer.Exit(GENERIC_FAILURE)

    def _on_tick(result: object) -> None:
        from jobbot.ops.loop import LoopTickResult

        assert isinstance(result, LoopTickResult)
        if result.ok:
            console.print("[green]tick ok[/green]")
        else:
            fid = result.failure.id if result.failure else "?"
            console.print(
                f"[yellow]tick failed[/yellow] exit={result.exit_code} "
                f"failure={fid}  {result.detail}"
            )

    def _hitl(reason: str) -> None:
        err_console.print(f"[bold red]{reason}[/bold red]")
        err_console.print(
            "Auth/challenge — fix manually, then restart loop. "
            "No CAPTCHA bypass."
        )
        raise typer.Exit(AUTH_REQUIRED if "exit 3" in reason else MANUAL_CHALLENGE)

    console.print(
        f"Loop [bold]{cmd}[/bold] every {interval}s "
        f"(fail_fast={fail_fast}, max_ticks={max_ticks})"
    )
    code = run_loop(
        cmd,
        interval_sec=interval,
        fail_fast=fail_fast,
        max_ticks=max_ticks,
        on_tick=_on_tick,
        hitl_pause=_hitl,
    )
    raise typer.Exit(code)


@ops_app.command("capabilities")
def ops_capabilities(
    write: Annotated[
        bool,
        typer.Option("--write", help="Write docs/capabilities.md (default: print)"),
    ] = False,
) -> None:
    """Index of commands and modules, so work already done is not re-derived."""
    from jobbot.ops.capabilities import build_index, write_index
    from jobbot.workspace import repo_root

    root = repo_root()
    if not write:
        # Raw echo: rich would wrap the markdown at the console width.
        typer.echo(build_index(root, app), nl=False)
        return
    target = write_index(root, app)
    console.print(f"Wrote [bold]{target}[/bold]")


@app.command("probe-exit", hidden=True)
def probe_exit(
    code: Annotated[
        int,
        typer.Argument(help="Exit code to raise (e.g. 5 = UI_CHANGED)"),
    ] = 5,
) -> None:
    """Hidden helper for failure-capture drills and unit tests."""
    raise typer.Exit(code)


# ── recruiters (public hiring practice; practices only, never people) ─────────


def _recruiters_state(config: JobbotConfig) -> tuple[list[Any], Path]:
    from jobbot.recruiters.sources import default_recruiters_path, load_sources

    path = default_recruiters_path(config.root)
    return load_sources(path), path


@recruiters_app.command("discover")
def recruiters_discover(
    urls: Annotated[
        list[str] | None,
        typer.Argument(help="Public URLs about hiring practice"),
    ] = None,
    from_file: Annotated[
        Path | None,
        typer.Option("--from-file", help="Text/YAML file with one URL per line"),
    ] = None,
    fixture: Annotated[
        Path | None,
        typer.Option("--fixture", help="Read a saved HTML instead of fetching (single URL)"),
    ] = None,
    delay: Annotated[
        float,
        typer.Option("--delay", help="Seconds between requests (be polite)"),
    ] = 1.0,
) -> None:
    """Read public pages about hiring and store what they teach as candidates."""
    from jobbot.companies.oneshot import FetchResult, UrllibFetcher
    from jobbot.recruiters.discover import discover_sources
    from jobbot.recruiters.sources import save_sources, upsert_source

    config = load_config()
    targets = list(urls or [])
    if from_file is not None:
        path = from_file.expanduser().resolve()
        if not path.is_file():
            err_console.print(f"[red]File not found: {path}[/red]")
            raise typer.Exit(VALIDATION_FAILURE)
        targets.extend(
            line.strip().lstrip("- ").strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        )
    if not targets:
        err_console.print("Give at least one URL, or --from-file with a list.")
        raise typer.Exit(VALIDATION_FAILURE)

    narrator = _narrator()
    narrator.phase(Phase.EXPLORING, f"{len(targets)} public page(s)")

    if fixture is not None:
        saved = fixture.expanduser().resolve()
        if not saved.is_file():
            err_console.print(f"[red]Fixture not found: {saved}[/red]")
            raise typer.Exit(VALIDATION_FAILURE)
        html = saved.read_text(encoding="utf-8")

        class _FixtureFetcher:
            def fetch(self, url: str) -> FetchResult:
                return FetchResult(url=url, status=200, html=html)

        report = discover_sources(targets[:1], _FixtureFetcher(), respect_robots=False)
    else:
        report = discover_sources(targets, UrllibFetcher(delay=delay))

    narrator.phase(Phase.SURFACING, f"{len(report.sources)} source(s)")
    narrator.outcome(
        ExplorationOutcome(
            found=len(report.sources),
            refused=len(report.refused),
            unknown=len(report.skipped_robots)
            + len(report.skipped_login)
            + len(report.nothing_learned),
        )
    )
    if report.skipped_robots:
        console.print(
            "[yellow]robots.txt asked us not to read (omitted, not absent):[/yellow] "
            + ", ".join(report.skipped_robots[:5])
        )
    if report.skipped_login:
        console.print(
            "[yellow]Behind a login (not public knowledge):[/yellow] "
            + ", ".join(report.skipped_login[:5])
        )
    if report.refused:
        console.print(
            "[yellow]Refused our request (unknown, not empty):[/yellow] "
            + ", ".join(report.refused[:5])
        )
    if not report.sources:
        console.print("Nothing learned this run.")
        raise typer.Exit(SUCCESS)

    sources, path = _recruiters_state(config)
    for source in report.sources:
        sources = upsert_source(sources, source)
        console.print(
            f"[green]candidate[/green] {source.url}  ({len(source.practices)} practice(s))"
        )
    save_sources(sources, path)
    console.print(f"Stored (candidates): {path}")
    console.print("Only [bold]jobbot recruiters promote URL[/bold] lets these advise your CV.")


@recruiters_app.command("list")
def recruiters_list(
    status: Annotated[
        str | None,
        typer.Option("--status", help="candidate | active | rejected"),
    ] = None,
) -> None:
    """List known sources of hiring practice."""
    config = load_config()
    sources, _ = _recruiters_state(config)
    if status:
        wanted = status.strip().casefold()
        sources = [s for s in sources if s.status.value == wanted]
    if not sources:
        console.print("No sources yet. Try [bold]jobbot recruiters discover URL[/bold].")
        return
    table = Table(title="Hiring practice sources")
    table.add_column("Status")
    table.add_column("Practices", justify="right")
    table.add_column("Title")
    table.add_column("URL")
    for source in sources:
        table.add_row(
            source.status.value,
            str(len(source.practices)),
            (source.title or "—")[:38],
            source.url[:48],
        )
    console.print(table)


@recruiters_app.command("show")
def recruiters_show(
    url: Annotated[str, typer.Argument(help="Source URL")],
) -> None:
    """Show one source with every practice it taught."""
    from jobbot.companies.urls import canonical_key

    config = load_config()
    sources, _ = _recruiters_state(config)
    key = canonical_key(url)
    source = next((s for s in sources if canonical_key(s.url) == key), None)
    if source is None:
        err_console.print(f"[red]Unknown source: {url}[/red]")
        raise typer.Exit(VALIDATION_FAILURE)
    console.print(
        Panel(
            f"[bold]{source.title or source.url}[/bold]\n{source.url}\n"
            f"status: {source.status.value}   practices: {len(source.practices)}\n"
            f"{source.evidence}",
            title="Source",
        )
    )
    for practice in source.practices:
        console.print(f"  [{practice.kind.value}] {practice.text}")


@recruiters_app.command("promote")
def recruiters_promote(
    url: Annotated[str, typer.Argument(help="Source URL")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Promote without asking")] = False,
) -> None:
    """Let one source's practices reach `cv advise`."""
    from jobbot.recruiters.sources import promote_source, save_sources

    config = load_config()
    sources, path = _recruiters_state(config)
    if not yes and not typer.confirm(f"Let {url} advise your CV?", default=False):
        console.print("Aborted.")
        raise typer.Exit(SUCCESS)
    save_sources(promote_source(sources, url), path)
    console.print(f"[green]active[/green] {url} → its practices now reach cv advise")


@recruiters_app.command("reject")
def recruiters_reject(
    url: Annotated[str, typer.Argument(help="Source URL")],
) -> None:
    """Keep one source out for good."""
    from jobbot.recruiters.sources import reject_source, save_sources

    config = load_config()
    sources, path = _recruiters_state(config)
    save_sources(reject_source(sources, url), path)
    console.print(f"[yellow]rejected[/yellow] {url}")


@recruiters_app.command("export")
def recruiters_export(
    out: Annotated[
        Path | None,
        typer.Option("--out", help="Destination file (default: output/recruiters/…)"),
    ] = None,
) -> None:
    """Write a shareable snapshot: active practices only, no people, no PII."""
    from jobbot.recruiters.sources import export_payload

    config = load_config()
    sources, _ = _recruiters_state(config)
    payload = export_payload(sources)
    target = out.expanduser().resolve() if out else (
        config.output_dir / "recruiters" / "hiring_practice.yaml"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    listed = payload.get("sources")
    count = len(listed) if isinstance(listed, list) else 0
    console.print(f"[green]Exported[/green] {count} active source(s) → {target}")
