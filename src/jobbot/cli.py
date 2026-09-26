"""CLI entrypoint for JobBot."""

from __future__ import annotations

import json
import logging
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated

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
from jobbot.ops.narrate import Narrator, Phase
from jobbot.profile.diff import compare_summaries, summarize_profile
from jobbot.profile.importer_latex import (
    LatexImportError,
    import_latex_cv,
    write_generated_profile,
)
from jobbot.profile.loader import ProfileLoadError, load_profile, load_profile_raw
from jobbot.profile.validator import validate_candidate

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
portals_app = typer.Typer(help="Recruitment portal registry (ATS)", no_args_is_help=True)
companies_app = typer.Typer(
    help="Company ↔ career platform knowledge (candidate → promote; public data only)",
    no_args_is_help=True,
)
ops_app = typer.Typer(
    help="Local ops: failures, symptoms (appearances), loops (no telemetry)",
    no_args_is_help=True,
)
ops_failure_app = typer.Typer(help="Inspect / triage stored failures", no_args_is_help=True)
ops_symptom_app = typer.Typer(
    help="Symptoms: returning vibecode appearances (local, redacted; not a backlog)",
    no_args_is_help=True,
)

app.add_typer(profile_app, name="profile")
app.add_typer(cv_app, name="cv")
app.add_typer(jobs_app, name="jobs")
app.add_typer(application_app, name="application")
app.add_typer(applications_app, name="applications")
app.add_typer(indeed_app, name="indeed")
app.add_typer(linkedin_app, name="linkedin")
app.add_typer(getonboard_app, name="getonboard")
app.add_typer(browser_app, name="browser")
app.add_typer(portals_app, name="portals")
app.add_typer(companies_app, name="companies")
app.add_typer(ops_app, name="ops")
ops_app.add_typer(ops_failure_app, name="failure")
ops_app.add_typer(ops_symptom_app, name="symptom")

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
                f"[yellow]Recorded failure[/yellow] {record.id} (fingerprint={record.fingerprint})"
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
) -> None:
    """JobBot CLI."""
    _setup_logging(verbose)


@app.command("version")
def version_cmd() -> None:
    """Show JobBot version."""
    console.print(__version__)


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
        err_console.print("[red]Provide a .tex path or set paths.legacy_cv in .jobbot.toml[/red]")
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
        console.print("\nConfirm skills you [bold]actually have[/bold] (never invent):")
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

    plans = plan_propagation(config, candidate, targets=wanted, section=section)
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
            _propagate_getonboard(config)
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


def _propagate_getonboard(config: JobbotConfig) -> None:
    from jobbot.adapters.getonboard.client import GetOnBoardProfileClient

    client = GetOnBoardProfileClient.from_config(config)
    path, result = client.prepare_package()
    console.print(f"[green]Wrote[/green] {path}  (mode={result.mode})")
    console.print("Abriendo Editar perfil (pega profile_permanent.md)…")
    console.print(client.open_profile_edit())
    console.print("Abriendo zona profesional (navega a Tus CVs)…")
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
    query: Annotated[str, typer.Argument(help="Search query, e.g. Senior Data Scientist")],
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
        job for job in repo.list_all() if job.posted_at is not None and not is_fresh(job.posted_at)
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
        if yes or typer.confirm("Mark application as applied after you send?", default=False):
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
    if yes or typer.confirm("Mark application as applied?", default=False):
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
        str,
        typer.Argument(help="Content search keywords, e.g. 'hiring data scientist'"),
    ] = "hiring data scientist",
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
    console.print(f"experiencia_y_perfil: {len(fields.experiencia_y_perfil)} / {EXPERIENCE_MAX}")
    console.print(f"formacion_academica:  {len(fields.formacion_academica)} / {EDUCATION_MAX}")
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
    console.print("Reemplaza textos viejos con output/getonboard/profile_permanent.md")


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
        "En la UI: ve a [bold]Tus CVs / Your resumes[/bold], sube el PDF y márcalo default."
    )
    if cv_pdf.is_file():
        console.print(f"PDF local: {cv_pdf}")
    else:
        console.print(
            "No hay PDF — genera con [bold]jobbot cv build[/bold] (queda en output/base/cv.pdf)."
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
    console.print("HITL: reemplaza textos viejos, sube CV default, guarda. Luego postula.")


@getonboard_app.command("search")
def getonboard_search(
    query: Annotated[
        str,
        typer.Argument(help="Search query, e.g. data scientist"),
    ] = "data scientist",
    limit: Annotated[int, typer.Option("--limit", help="Max results (1-50)")] = 20,
) -> None:
    """Search Get on Board (Spanish/LATAM) and store jobs locally."""
    from jobbot.adapters.getonboard.jobs import GetOnBoardJobSource
    from jobbot.jobs.sources import JobSearchQuery

    if limit < 1 or limit > 50:
        err_console.print("--limit must be between 1 and 50")
        raise typer.Exit(GENERIC_FAILURE)

    session, config = _session()
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


# ── companies (collaborative career-platform knowledge) ──────────────────────


def _narrator(quiet: bool = False) -> Narrator:
    """Phase narration for the long loops (dim lines, local stdout only)."""
    return Narrator(sink=lambda line: console.print(f"[dim]{line}[/dim]"), quiet=quiet)


def _companies_registry(config: JobbotConfig) -> tuple[CompanyRegistry, Path]:
    from jobbot.companies.registry import default_companies_path, load_companies

    path = default_companies_path(config.root)
    return load_companies(path), path


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
        if s.status != KnowledgeStatus.REJECTED and (site is None or s.key == canonical_key(site))
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
    narrator.phase(Phase.RECEIVING_WORLD, f"{len(seeds)} companies", may_ask=False)

    def on_company(seed: CompanySeed, found: list[CompanyPortalCandidate]) -> None:
        narrator.note(f"{seed.name}: {len(found)} candidate portal(s)")

    report = run_oneshot(
        seeds,
        UrllibFetcher(delay=delay),
        search_hits=hits,
        limit=limit,
        on_company=on_company,
    )
    target = out.expanduser().resolve() if out else generated_candidates_path(config.output_dir)
    write_candidates(report.candidates, target)
    console.print(
        f"Probed {report.companies_seen} companies with {report.requests_made} requests → "
        f"{len(report.candidates)} candidate portal(s)."
    )
    if report.companies_without_portal:
        console.print(
            "No public portal found for: " + ", ".join(report.companies_without_portal[:10])
        )
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
        typer.Option("--site", help="indeed | linkedin | gmail (profile dir + start URL)"),
    ] = "indeed",
    launch: Annotated[
        bool,
        typer.Option("--launch/--print-only", help="Launch Chrome (default) or only print argv"),
    ] = True,
) -> None:
    """Open a normal Chrome with CDP so challenges can be completed by hand."""
    import subprocess

    from jobbot.browser.cdp import cdp_http_url, chrome_debug_argv

    config = load_config()
    site_key = site.strip().lower()
    if site_key == "linkedin":
        profile_dir = config.root / "browser-data" / "linkedin-cdp"
        start_url = "https://www.linkedin.com/login"
        tip = f"jobbot linkedin sync --section publications --apply --cdp {cdp_http_url(port)}"
    elif site_key == "indeed":
        profile_dir = config.root / "browser-data" / "indeed-cdp"
        start_url = "https://cl.indeed.com/"
        tip = f"jobbot jobs search … --cdp {cdp_http_url(port)}"
    elif site_key == "gmail":
        profile_dir = config.root / "browser-data" / "gmail-cdp"
        start_url = "https://mail.google.com/"
        tip = f"jobbot application apply J0001 --apply --cdp {cdp_http_url(port)}"
    else:
        err_console.print(f"[red]Unknown --site {site!r} (use indeed|linkedin|gmail)[/red]")
        raise typer.Exit(GENERIC_FAILURE)
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
    subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # noqa: S603
    console.print(f"[green]Launched[/green] Chrome with CDP at {url}")


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


@ops_symptom_app.command("note")
def ops_symptom_note(
    intent: Annotated[
        str,
        typer.Argument(help="Appearance that returns in vibecode (redacted at write)"),
    ],
    area: Annotated[
        str,
        typer.Option("--area", help="cv|jobs|portals|matching|ops|nlp|companies|profile|other"),
    ] = "other",
    title: Annotated[
        str | None,
        typer.Option("--title", help="Short label (redacted)"),
    ] = None,
    rule: Annotated[
        str,
        typer.Option(
            "--rule",
            help="Condition of possibility (structural, falsifiable; not a wish)",
        ),
    ] = "",
) -> None:
    """Note a returning appearance. Same fingerprint increments sightings."""
    from jobbot.ops.symptoms import note_symptom

    session, config = _session()
    try:
        record = note_symptom(
            session,
            intent=intent,
            area=area,
            title=title,
            rule_hypothesis=rule,
            output_dir=config.output_dir,
        )
    except ValueError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(VALIDATION_FAILURE) from exc
    console.print(
        f"[green]{record.id}[/green] area={record.area} "
        f"sightings={record.sightings} status={record.status} fp={record.fingerprint}"
    )
    console.print(f"Plan: [bold]jobbot ops symptom plan {record.id}[/bold]")


@ops_symptom_app.command("list")
def ops_symptom_list(
    status: Annotated[
        str | None,
        typer.Option("--status", help="latent|acknowledged|compressing|resolved|wontfix"),
    ] = None,
    area: Annotated[
        str | None,
        typer.Option("--area", help="Filter by area"),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", min=1, max=200)] = 50,
) -> None:
    """List symptoms (returning appearances), newest first."""
    from jobbot.ops.symptoms import list_symptoms

    session, _ = _session()
    rows = list_symptoms(session, status=status, area=area, limit=limit)
    if not rows:
        console.print("No symptoms stored.")
        raise typer.Exit(SUCCESS)
    table = Table(title="ops symptoms (appearances that return)")
    table.add_column("id")
    table.add_column("area")
    table.add_column("n")
    table.add_column("status")
    table.add_column("title")
    for r in rows:
        table.add_row(r.id, r.area, str(r.sightings), r.status, r.title[:60])
    console.print(table)


@ops_symptom_app.command("show")
def ops_symptom_show(
    symptom_id: Annotated[str, typer.Argument(help="Symptom id, e.g. S0001")],
) -> None:
    """Show one symptom (already redacted at write time)."""
    from jobbot.ops.symptoms import get_symptom

    session, config = _session()
    record = get_symptom(session, symptom_id)
    if record is None:
        err_console.print(f"[red]Unknown symptom {symptom_id}[/red]")
        raise typer.Exit(GENERIC_FAILURE)
    console.print(
        Panel(
            f"area={record.area}\nsightings={record.sightings}\nstatus={record.status}\n"
            f"fingerprint={record.fingerprint}\n\n"
            f"title: {record.title}\n\nappearance:\n{record.intent}\n\n"
            f"condition of possibility:\n{record.rule_hypothesis or '(none yet)'}\n\n"
            f"feature: {record.feature_path or '(none)'}\n"
            f"issue: {record.issue_url or '(none)'}",
            title=record.id,
        )
    )
    mirror = config.output_dir / "ops" / "symptoms" / f"{record.id}.json"
    if mirror.is_file():
        console.print(f"Mirror: {mirror}")


@ops_symptom_app.command("plan")
def ops_symptom_plan(
    symptom_id: Annotated[str, typer.Argument(help="Symptom id, e.g. S0001")],
) -> None:
    """Print conditions-of-possibility → System 1 plan (does not write code)."""
    from jobbot.ops.symptoms import get_symptom, promote_plan

    session, _ = _session()
    record = get_symptom(session, symptom_id)
    if record is None:
        err_console.print(f"[red]Unknown symptom {symptom_id}[/red]")
        raise typer.Exit(GENERIC_FAILURE)
    console.print(Panel(promote_plan(record), title="phenomenology → System 1"))


@ops_symptom_app.command("triage")
def ops_symptom_triage(
    symptom_id: Annotated[str, typer.Argument(help="Symptom id, e.g. S0001")],
    status: Annotated[
        str,
        typer.Option("--status", help="latent|acknowledged|compressing|resolved|wontfix"),
    ],
    feature: Annotated[
        str | None,
        typer.Option("--feature", help="Path where conditions were encoded"),
    ] = None,
) -> None:
    """Update symptom status after conditions are encoded (or declined)."""
    from jobbot.ops.symptoms import mark_symptom_status

    session, _ = _session()
    try:
        record = mark_symptom_status(session, symptom_id, status, feature_path=feature)
    except ValueError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(VALIDATION_FAILURE) from exc
    if record is None:
        err_console.print(f"[red]Unknown symptom {symptom_id}[/red]")
        raise typer.Exit(GENERIC_FAILURE)
    console.print(
        f"[green]{record.id}[/green] → status={record.status}"
        + (f" feature={record.feature_path}" if record.feature_path else "")
    )


@ops_symptom_app.command("issue")
def ops_symptom_issue(
    symptom_id: Annotated[str, typer.Argument(help="Symptom id, e.g. S0001")],
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation"),
    ] = False,
) -> None:
    """HITL GitHub issue from a redacted symptom (conditions, not a wish ticket). Never auto."""
    import subprocess

    from jobbot.ops.symptoms import get_symptom, issue_body, issue_title, mark_symptom_status

    session, _ = _session()
    record = get_symptom(session, symptom_id)
    if record is None:
        err_console.print(f"[red]Unknown symptom {symptom_id}[/red]")
        raise typer.Exit(GENERIC_FAILURE)
    if record.issue_url:
        console.print(f"Already linked: {record.issue_url}")
        raise typer.Exit(SUCCESS)

    title = issue_title(record)
    body = issue_body(record)
    console.print(Panel(f"{title}\n\n{body}", title="proposed GitHub issue (redacted)"))
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
    mark_symptom_status(session, symptom_id, "acknowledged", issue_url=url or None)
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
        err_console.print("Auth/challenge — fix manually, then restart loop. No CAPTCHA bypass.")
        raise typer.Exit(AUTH_REQUIRED if "exit 3" in reason else MANUAL_CHALLENGE)

    console.print(
        f"Loop [bold]{cmd}[/bold] every {interval}s (fail_fast={fail_fast}, max_ticks={max_ticks})"
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


@app.command("probe-exit", hidden=True)
def probe_exit(
    code: Annotated[
        int,
        typer.Argument(help="Exit code to raise (e.g. 5 = UI_CHANGED)"),
    ] = 5,
) -> None:
    """Hidden helper for failure-capture drills and unit tests."""
    raise typer.Exit(code)
