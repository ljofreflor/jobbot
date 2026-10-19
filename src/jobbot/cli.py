"""CLI entrypoint for JobBot."""

from __future__ import annotations

import json
import logging
import re
import shutil
import sys
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from jobbot.adapters.indeed.client import IndeedAdapter

from jobbot import __version__
from jobbot.applications.manager import (
    ApplicationRepository,
    prepare_application_package,
)
from jobbot.browser.background import background_notice
from jobbot.companies.models import DiscoverySource
from jobbot.companies.registry import CompanyRegistry
from jobbot.config import ConfigError, JobbotConfig, load_config
from jobbot.cv.build import BuildTarget, build_cv
from jobbot.cv.renderer import CvStyle
from jobbot.db.engine import make_engine, make_session_factory
from jobbot.exit_codes import (
    AUTH_REQUIRED,
    GENERIC_FAILURE,
    MANUAL_CHALLENGE,
    SUCCESS,
    UI_CHANGED,
    UPDATE_AVAILABLE,
    USER_CANCEL,
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
from jobbot.portals.detect import AtsKind
from jobbot.profile.diff import compare_summaries, summarize_profile
from jobbot.profile.importer_common import write_generated_profile
from jobbot.profile.importer_latex import LatexImportError, import_latex_cv
from jobbot.profile.importer_pdf import PdfImportError, import_pdf_cv
from jobbot.profile.loader import ProfileLoadError, load_profile, load_profile_raw
from jobbot.profile.validator import unknown_profile_keys, validate_candidate
from jobbot.self_update import update_jobbot
from jobbot.self_update_schedule import ScheduleAction
from jobbot.workspace import (
    DEFAULT_LABEL,
    STAMP_NAME,
    WorkspaceExistsError,
    WorkspaceOwnerError,
    active_workspace,
    init_workspace,
    list_workspaces,
    read_stamp,
    resolve_root,
    sandboxes_dir,
    set_active_workspace,
    workspace_root,
)
from jobbot.workspace import adopt as adopt_workspace

# Profile searches a board command runs when no query is typed.
_DEFAULT_MAX_QUERIES = 3


def _restamp_after_profile_promote(config: JobbotConfig) -> None:
    """Promoting a CV is a deliberate identity change: refresh the owner stamp."""
    label = active_workspace() or DEFAULT_LABEL
    adopt_workspace(config.profile_path, config.output_dir, label=label)


app = typer.Typer(
    name="jobbot",
    help=(
        "Start here: profile, cv, get, capture. "
        "Local terminal tool for job search and structured CV management."
    ),
    no_args_is_help=True,
)
profile_app = typer.Typer(help="Candidate profile operations", no_args_is_help=True)
answers_app = typer.Typer(
    help="Local application answers (preferences, not professional facts)",
    no_args_is_help=True,
)
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
    help="Browser helpers (HITL Chrome/Edge/Brave via CDP — no CAPTCHA bypass)",
    no_args_is_help=True,
)
getonboard_app = typer.Typer(
    help="Get on Board: perfil/CVs HITL + job discovery (LATAM)",
    no_args_is_help=True,
)
torre_app = typer.Typer(help="Torre: job discovery (LATAM / remoto)", no_args_is_help=True)
empleospublicos_app = typer.Typer(
    help="Empleos Públicos (Chile): concursos abiertos vía datos abiertos del Servicio Civil",
    no_args_is_help=True,
)
portals_app = typer.Typer(help="Recruitment portal registry (ATS)", no_args_is_help=True)
portals_profile_app = typer.Typer(
    help="Profile coverage and fill sheets from the source of truth (no browser)",
    no_args_is_help=True,
)
companies_app = typer.Typer(
    help="Company ↔ career platform knowledge (candidate → promote; public data only)",
    no_args_is_help=True,
)
recruiters_app = typer.Typer(
    help="Public hiring practice that feeds cv advise (practices only, never people)",
    no_args_is_help=True,
)
ops_app = typer.Typer(
    help="Local ops: failures, symptoms (appearances), loops (no telemetry)",
    no_args_is_help=True,
)
ops_failure_app = typer.Typer(help="Inspect / triage stored failures", no_args_is_help=True)
ops_symptom_app = typer.Typer(
    help="Appearances that return (symptoms) → System 1 compression (local, redacted)",
    no_args_is_help=True,
)
workspace_app = typer.Typer(
    help="Isolated homes for extra candidates (test CVs) in this checkout",
    no_args_is_help=True,
)
secrets_app = typer.Typer(
    help="Opt-in local password vault (0600; never invents; never prints)",
    no_args_is_help=True,
)

app.add_typer(workspace_app, name="workspace")
app.add_typer(secrets_app, name="secrets")
profile_app.add_typer(answers_app, name="answers")
app.add_typer(profile_app, name="profile")
app.add_typer(cv_app, name="cv")
app.add_typer(jobs_app, name="jobs")
app.add_typer(application_app, name="application")
app.add_typer(applications_app, name="applications")
app.add_typer(indeed_app, name="indeed")
app.add_typer(linkedin_app, name="linkedin")
app.add_typer(getonboard_app, name="getonboard")
app.add_typer(torre_app, name="torre")
app.add_typer(empleospublicos_app, name="empleospublicos")
app.add_typer(browser_app, name="browser")
app.add_typer(portals_app, name="portals")
portals_app.add_typer(portals_profile_app, name="profile")
app.add_typer(companies_app, name="companies")
app.add_typer(recruiters_app, name="recruiters")
app.add_typer(ops_app, name="ops")
ops_app.add_typer(ops_failure_app, name="failure")
ops_app.add_typer(ops_symptom_app, name="symptom")

console = Console()
err_console = Console(stderr=True)


class _QuietExit(Exception):
    """The command refused on purpose (closed vacancy, and the like). Not a defect."""

    def __init__(self, code: int) -> None:
        self.code = code


class _RecordedExit(Exception):
    """Non-zero exit that must land in ops_failures with a real fingerprint.

    Autopoietic lane for product gaps (novel URL shapes, missing fetchers):
    exception → observability → ``ops failure work`` → issue → PR. A bare
    ``typer.Exit`` drops the message and collapses every gap into one useless
    ``Exit:`` fingerprint.
    """

    def __init__(self, code: int, *, error_class: str, message: str) -> None:
        self.code = code
        self.error_class = error_class
        self.message = message


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
    recorded_class: str | None = None
    recorded_message: str | None = None
    try:
        result = app(args, prog_name=prog_name, standalone_mode=False)
        if isinstance(result, int):
            exit_code = result
    except typer.Exit as exc:
        exit_code = int(exc.exit_code)
        if exit_code == USER_CANCEL:
            # Ctrl-C. typer rewrites KeyboardInterrupt as Exit(130); that is the
            # user stopping, not a defect, and it must not become an ops failure.
            err_console.print("Cancelled.")
            if standalone_mode:
                raise SystemExit(exit_code) from exc
            return exit_code
        caught = exc
    except KeyboardInterrupt:
        err_console.print("Cancelled.")
        if standalone_mode:
            raise SystemExit(USER_CANCEL) from None
        return USER_CANCEL
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
    except ConfigError as exc:
        err_console.print(f"[bold red]Invalid config[/bold red]\n{exc}")
        if standalone_mode:
            raise SystemExit(VALIDATION_FAILURE) from exc
        return VALIDATION_FAILURE
    except _QuietExit as exc:
        if standalone_mode:
            raise SystemExit(exc.code) from exc
        return exc.code
    except _RecordedExit as exc:
        exit_code = exc.code
        recorded_class = exc.error_class
        recorded_message = exc.message
        caught = exc.__cause__ if isinstance(exc.__cause__, BaseException) else None
    except Exception as exc:  # noqa: BLE001 — CLI boundary capture
        if "click" in type(exc).__module__ and hasattr(exc, "show"):
            exc.show()
            exit_code = int(getattr(exc, "exit_code", VALIDATION_FAILURE))
            if standalone_mode:
                raise SystemExit(exit_code) from exc
            return exit_code
        exit_code = GENERIC_FAILURE
        caught = exc
        err_console.print(f"[red]Unhandled error:[/red] {exc}")

    if exit_code != SUCCESS:
        from jobbot.ops.failures import ABORT_MESSAGE, capture_cli_failure, runtime_context

        record = capture_cli_failure(
            exit_code,
            argv=["jobbot", *args],
            exc=caught if not isinstance(caught, typer.Exit) else None,
            error_class=(
                recorded_class if recorded_class is not None else ("Abort" if aborted else None)
            ),
            message=(
                recorded_message
                if recorded_message is not None
                else (ABORT_MESSAGE if aborted else None)
            ),
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


def _print_version_and_exit(value: bool) -> None:
    if value:
        console.print(__version__)
        raise typer.Exit(code=SUCCESS)


def _update_and_exit(value: bool) -> None:
    """``jobbot -U`` is ``jobbot update``: reinstall from main, then stop."""
    if not value:
        return
    update_cmd()
    raise typer.Exit(code=SUCCESS)


@app.callback()
def main(
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Enable debug logging"),
    ] = False,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-V",
            callback=_print_version_and_exit,
            is_eager=True,
            help="Show JobBot version and exit",
        ),
    ] = False,
    update: Annotated[
        bool,
        typer.Option(
            "--update",
            "-U",
            callback=_update_and_exit,
            is_eager=True,
            help="Reinstall JobBot from main and exit (same as `jobbot update`)",
        ),
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
        from jobbot.advisor import retention_warning

        notice = retention_warning(workspace_root(workspace))
        if notice:
            console.print(f"[yellow]{notice}[/yellow]")


@app.command("version")
def version_cmd() -> None:
    """Show JobBot version."""
    console.print(__version__)


@app.command("init")
def workspace_init(
    directory: Annotated[
        Path,
        typer.Argument(
            help=(
                "Folder that becomes the workspace (default: .). "
                ".jobbot.toml and .local/ are created inside this folder"
            ),
        ),
    ] = Path("."),
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite an existing .jobbot.toml / seeds"),
    ] = False,
) -> None:
    """Create a portable workspace with ``.local/`` inside DIR (cold install; no git clone)."""
    try:
        result = init_workspace(directory, force=force)
    except WorkspaceExistsError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(GENERIC_FAILURE) from exc
    except OSError as exc:
        err_console.print(f"[red]Could not create workspace: {exc}[/red]")
        raise typer.Exit(GENERIC_FAILURE) from exc

    console.print("[bold green]Workspace ready[/bold green]")
    console.print(f"Root: {result.root}")
    console.print("JobBot is installed globally; this folder is your syncable workspace.")
    console.print(
        Panel(
            "Next:\n"
            "  1. Read AGENTS.md  (operating guide for you and AI assistants)\n"
            "  2. Edit .local/profile.yaml  (or: jobbot profile import-pdf CV.pdf)\n"
            "  3. jobbot profile validate\n"
            "  4. jobbot getonboard search\n"
            "Sync this whole folder (including .local/) with Drive/Dropbox/Syncthing/…\n"
            "If you later run jobbot secrets init, exclude .local/.vault.yaml from sync.",
            title="Cold start",
        )
    )


@app.command("update")
def update_cmd(
    ref: Annotated[
        str | None,
        typer.Option("--ref", help="Git ref to install (default: JOBBOT_REF or main)"),
    ] = None,
    schedule: Annotated[
        ScheduleAction | None,
        typer.Option(
            "--schedule",
            help=(
                "daily: run `jobbot update` every day (launchd on macOS, crontab on Linux); "
                "off: remove it; status: show it"
            ),
        ),
    ] = None,
    check: Annotated[
        bool,
        typer.Option(
            "--check",
            help=f"Only compare installed vs latest commit; exit {UPDATE_AVAILABLE} if newer",
        ),
    ] = False,
    scheduled: Annotated[
        bool,
        typer.Option("--scheduled", hidden=True, help="Run by the daily scheduled job"),
    ] = False,
) -> None:
    """Upgrade the ``jobbot`` executable on PATH (uv tool reinstall from GitHub)."""
    if sum((schedule is not None, check, scheduled)) > 1 or (
        ref is not None and (schedule is not None or scheduled)
    ):
        err_console.print(
            "[red]--schedule, --check and --scheduled are exclusive; "
            "the scheduled job follows main (or JOBBOT_REF), not --ref.[/red]"
        )
        raise _QuietExit(VALIDATION_FAILURE)
    if scheduled:
        _run_scheduled_update()
        return
    if check:
        _check_update(ref)
        return
    if schedule is not None:
        _schedule_update(schedule)
        return
    console.print(f"Current: {__version__}")
    result = update_jobbot(ref=ref)
    if not result.ok:
        err_console.print(f"[red]{result.message}[/red]")
        raise typer.Exit(GENERIC_FAILURE)
    console.print(f"[green]{result.message}[/green]")
    if result.version_line:
        console.print(f"Now: {result.version_line}")
    else:
        console.print("Run [bold]jobbot version[/bold] in a new shell if PATH changed.")


def _check_update(ref: str | None) -> None:
    from jobbot.self_update import _in_docker, check_for_update, docker_hint

    if _in_docker():
        err_console.print(docker_hint(), markup=False)
        raise _QuietExit(GENERIC_FAILURE)
    result = check_for_update(ref=ref)
    if result.status == "up_to_date":
        console.print(f"[green]{result.message}[/green]")
        return
    if result.status == "available":
        console.print(f"[yellow]{result.message}[/yellow]")
        console.print("Run [bold]jobbot update[/bold] to install it.")
        raise _QuietExit(UPDATE_AVAILABLE)
    err_console.print(result.message, style="red", markup=False)
    raise _QuietExit(GENERIC_FAILURE)


def _schedule_update(action: ScheduleAction) -> None:
    from jobbot.self_update import _in_docker, docker_hint, installed_info
    from jobbot.self_update_schedule import (
        Scheduler,
        auto_update_opt_out,
        resolve_binary,
        user_config_path,
    )

    if _in_docker():
        err_console.print(docker_hint(), markup=False)
        raise _QuietExit(GENERIC_FAILURE)
    scheduler = Scheduler()
    if action is ScheduleAction.status:
        status = scheduler.status()
        for line in status.lines():
            console.print(line, markup=False, highlight=False)
        if status.backend is None:
            raise _QuietExit(GENERIC_FAILURE)
        return
    if action is ScheduleAction.off:
        outcome = scheduler.remove()
    else:
        if installed_info().editable:
            err_console.print(
                "[red]Editable install (development checkout): not scheduling. Use git pull.[/red]"
            )
            raise _QuietExit(VALIDATION_FAILURE)
        binary = resolve_binary()
        if binary is None:
            err_console.print("[red]jobbot not found on PATH; run scripts/install.sh first.[/red]")
            raise _QuietExit(GENERIC_FAILURE)
        uv = shutil.which("uv")
        if uv is None:
            err_console.print(
                "[yellow]uv not found on PATH; the job will fail until it is.[/yellow]"
            )
        outcome = scheduler.install(
            scheduler.spec(binary, extra_path=[Path(uv).parent if uv else None])
        )
    if not outcome.ok:
        err_console.print(outcome.message, style="red", markup=False)
        raise typer.Exit(GENERIC_FAILURE)
    console.print(outcome.message, markup=False, highlight=False)
    reason = auto_update_opt_out(scheduler.env, user_config_path(scheduler.home))
    if action is ScheduleAction.daily and reason:
        console.print(f"[yellow]Opt-out active ({reason}): the job will skip.[/yellow]")


def _run_scheduled_update() -> None:
    import os

    from jobbot.self_update import _in_docker
    from jobbot.self_update_schedule import run_scheduled_update, user_config_path

    run = run_scheduled_update(
        env=os.environ,
        config_path=user_config_path(Path.home()),
        in_docker=_in_docker,
    )
    for line in run.lines:
        typer.echo(line)
    if run.exit_code != SUCCESS:
        raise _QuietExit(run.exit_code)


@app.command("status")
def status_cmd(
    as_json: Annotated[bool, typer.Option("--json", help="Machine-readable rows")] = False,
) -> None:
    """Show which permanent CVs / profiles and active company portals are up."""
    _print_cv_status(as_json=as_json)


def _print_cv_status(*, as_json: bool) -> None:
    from jobbot.cv.status import build_cv_status
    from jobbot.profile.loader import load_profile

    config = load_config()
    report = build_cv_status(config, load_profile(config.profile_path))
    if as_json:
        console.print_json(data=report.to_dict())
        return
    table = Table(title="CV / profile presence (evidence only)")
    table.add_column("Destination")
    table.add_column("Artifact")
    table.add_column("State")
    table.add_column("Evidence")
    table.add_column("Hint")
    for row in report.rows:
        table.add_row(
            row.destination,
            row.artifact,
            row.state.value,
            row.evidence,
            row.hint or "",
        )
    console.print(table)
    console.print(
        "[dim]Evidence only — missing receipt means unknown, not absent on the portal. "
        "Active company portals need page evidence; a yes is never a receipt. "
        "Per-job apply stages: jobbot applications list[/dim]"
    )
    from jobbot.applications.feedback import interview_reminders

    for line in interview_reminders(config.root):
        console.print(line)


def _ingest_with_progress(
    config: JobbotConfig,
    session: Session,
    portal: Any,
    *,
    candidate: Candidate,
    html: str | None,
    ingest_hard_link: Any,
    cdp_url: str | None = None,
) -> Any:
    """Download a Get on Board page with a progress bar. Fixtures and other ATS skip it."""
    from jobbot.portals.detect import AtsKind

    downloading = html is None and portal.ats_kind == AtsKind.GETONBOARD
    if not downloading:
        return ingest_hard_link(
            config,
            session,
            portal.url,
            candidate=candidate,
            html=html,
            cdp_url=cdp_url,
        )
    from rich.progress import (
        BarColumn,
        DownloadColumn,
        Progress,
        SpinnerColumn,
        TextColumn,
        TimeElapsedColumn,
    )

    with Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("descargando la oferta", total=None)

        def on_chunk(done: int, total: int | None) -> None:
            progress.update(task, completed=done, total=total)

        return ingest_hard_link(
            config,
            session,
            portal.url,
            candidate=candidate,
            html=html,
            cdp_url=cdp_url,
            on_chunk=on_chunk,
        )


@app.command("postulate")
def postulate_cmd(
    fixture: Annotated[
        str | None,
        typer.Option("--fixture", help="Post text to classify. This command does not fetch."),
    ] = None,
) -> None:
    """Classify a post as email, portal, or unknown. Does not write portals.yaml."""
    from pathlib import Path

    from jobbot.portals.postulate import known_portal_domains, plan_postulate, render_plan

    if not fixture:
        err_console.print("postulate needs --fixture; the post was not read.")
        raise _QuietExit(VALIDATION_FAILURE)
    path = Path(fixture)
    if not path.is_file():
        err_console.print("postulate needs --fixture; the post was not read.")
        raise _QuietExit(VALIDATION_FAILURE)
    config = load_config()
    text = path.read_text(encoding="utf-8")
    plan = plan_postulate(text, known_domains=known_portal_domains(config))
    for line in render_plan(plan):
        console.print(line)
    raise typer.Exit(SUCCESS)


@app.command("get")
def get_hard_link(
    url: Annotated[
        str | None,
        typer.Argument(
            help="Hard job URL. Live download: Get on Board / Indeed / Workday (CXS). "
            "With --fixture, also reads saved career-page or Indeed viewjob HTML. "
            "With --park, only queues the URL (phone-friendly; no fetch).",
        ),
    ] = None,
    apply_changes: Annotated[
        bool,
        typer.Option(
            "--apply",
            help="After preparing the package, open the ATS assist (you submit)",
        ),
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Skip confirmation")] = False,
    cdp: Annotated[
        str | None,
        typer.Option("--cdp", help="Attach to your logged-in Chrome (see browser chrome-debug)"),
    ] = None,
    fixture: Annotated[
        Path | None,
        typer.Option(
            "--fixture",
            help=(
                "Saved HTML instead of a live download. "
                "Get on Board, Indeed viewjob, or generic career pages (e.g. Phenom)."
            ),
            exists=True,
            dir_okay=False,
            readable=True,
        ),
    ] = None,
    park: Annotated[
        bool,
        typer.Option(
            "--park",
            help=(
                "Queue the URL under data/hard-link-inbox.txt without fetching "
                "(use from a phone / when CAPTCHA would block). Drain later with --parked."
            ),
        ),
    ] = False,
    parked: Annotated[
        bool,
        typer.Option(
            "--parked",
            help=(
                "Ingest every URL parked in data/hard-link-inbox.txt "
                "(desktop + Chrome CDP for Indeed challenges)."
            ),
        ),
    ] = False,
) -> None:
    """Ingest a hard job link: know the portal → JD → CV → package (HITL apply)."""
    if park and parked:
        err_console.print("[red]Use either --park or --parked, not both.[/red]")
        raise typer.Exit(VALIDATION_FAILURE)
    if parked:
        if url is not None:
            err_console.print("[red]--parked does not take a URL argument.[/red]")
            raise typer.Exit(VALIDATION_FAILURE)
        if fixture is not None:
            err_console.print("[red]--parked cannot combine with --fixture.[/red]")
            raise typer.Exit(VALIDATION_FAILURE)
        _drain_parked_hard_links(apply_changes=apply_changes, yes=yes, cdp=cdp)
        return
    if url is None:
        err_console.print(
            "[red]Provide a hard job URL[/red], or pass [bold]--parked[/bold] "
            "to drain data/hard-link-inbox.txt."
        )
        raise typer.Exit(VALIDATION_FAILURE)
    if park:
        _park_hard_link(url)
        return
    _ingest_one_hard_link(
        url,
        apply_changes=apply_changes,
        yes=yes,
        cdp=cdp,
        fixture=fixture,
    )


def _park_hard_link(url: str) -> None:
    """Save a share link for later (no Indeed fetch, no CAPTCHA)."""
    from jobbot.jobs.inbox import inbox_path, park_url

    _, config = _session()
    try:
        stored, existed = park_url(config, url)
    except ValueError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(VALIDATION_FAILURE) from exc
    path = inbox_path(config)
    if existed:
        console.print(f"[dim]Already parked[/dim] {stored}")
    else:
        console.print(f"[green]Parked[/green] {stored}")
    console.print(f"Inbox: {path}")
    console.print(
        "On a desktop with Chrome: "
        "[bold]jobbot browser chrome-debug --site indeed[/bold], then "
        "[bold]jobbot get --parked --cdp http://127.0.0.1:9222[/bold]"
    )


def _drain_parked_hard_links(
    *,
    apply_changes: bool,
    yes: bool,
    cdp: str | None,
) -> None:
    from jobbot.jobs.inbox import inbox_path, list_parked, remove_parked

    _, config = _session()
    urls = list_parked(config)
    if not urls:
        console.print(f"Inbox empty ({inbox_path(config)}).")
        return
    console.print(f"Draining {len(urls)} parked URL(s)…")
    failures = 0
    for item in urls:
        console.print(f"\n[bold]→[/bold] {item}")
        try:
            _ingest_one_hard_link(
                item,
                apply_changes=apply_changes,
                yes=yes,
                cdp=cdp,
                fixture=None,
            )
        except _RecordedExit as exc:
            failures += 1
            from jobbot.ops.failures import capture_cli_failure, runtime_context

            record = capture_cli_failure(
                exc.code,
                argv=["jobbot", "get", item],
                exc=exc.__cause__ if isinstance(exc.__cause__, BaseException) else None,
                error_class=exc.error_class,
                message=exc.message,
                context=runtime_context(),
            )
            if record is not None:
                err_console.print(
                    f"[yellow]Recorded failure[/yellow] {record.id} "
                    f"(fingerprint={record.fingerprint})"
                )
            err_console.print(f"[yellow]Left in inbox[/yellow] (exit {exc.code}): {item}")
            continue
        except (_QuietExit, typer.Exit) as exc:
            failures += 1
            if isinstance(exc, _QuietExit):
                code = exc.code
            else:
                code = exc.exit_code if isinstance(exc.exit_code, int) else 1
            err_console.print(f"[yellow]Left in inbox[/yellow] (exit {code}): {item}")
            continue
        remove_parked(config, item)
        console.print(f"[dim]Removed from inbox:[/dim] {item}")
    if failures:
        # Per-URL gaps already landed in ops_failures; the drain summary is not a
        # new defect (avoid a second empty Exit fingerprint).
        raise _QuietExit(GENERIC_FAILURE if failures == len(urls) else SUCCESS)


def _ingest_one_hard_link(
    url: str,
    *,
    apply_changes: bool,
    yes: bool,
    cdp: str | None,
    fixture: Path | None,
) -> None:
    from jobbot.browser.cdp import resolve_cdp_url
    from jobbot.jobs.from_url import (
        ClosedPostingError,
        InvalidPostingUrlError,
        PortalDisallowedError,
        PortalShapeChangedError,
        UnknownPortalError,
        UnsupportedPortalFetchError,
        ingest_hard_link,
    )
    from jobbot.portals.knowledge import lookup_portal

    session, config = _session()
    portal = lookup_portal(config, url)
    console.print(
        f"portal: [bold]{portal.domain or '(none)'}[/bold]  "
        f"ats={portal.ats_kind.value}  knowledge={portal.source.value}"
    )
    narrator = _narrator()
    narrator.phase(Phase.RECEIVING_WORLD, portal.domain or url)
    html = fixture.read_text(encoding="utf-8") if fixture is not None else None
    if not portal.known and html is None:
        err_console.print(
            f"[red]Unknown employment domain:[/red] {portal.domain or url}\n"
            "Pass [bold]--fixture[/bold] with saved career HTML, or add the host "
            "with [bold]jobbot portals add[/bold] / "
            "[bold]jobbot companies learn[/bold]."
        )
        raise typer.Exit(VALIDATION_FAILURE)

    try:
        candidate = load_profile(config.profile_path)
    except ProfileLoadError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(VALIDATION_FAILURE) from exc

    cdp_url = resolve_cdp_url(cdp)
    try:
        result = _ingest_with_progress(
            config,
            session,
            portal,
            candidate=candidate,
            html=html,
            ingest_hard_link=ingest_hard_link,
            cdp_url=cdp_url,
        )
    except ClosedPostingError as exc:
        err_console.print(f"[red]Vacancy looks filled[/red] ({exc.evidence}). Not stored.")
        raise _QuietExit(VALIDATION_FAILURE) from exc
    except PortalDisallowedError as exc:
        err_console.print(f"[yellow]{exc}[/yellow]")
        raise _QuietExit(VALIDATION_FAILURE) from exc
    except (UnknownPortalError, InvalidPostingUrlError) as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(VALIDATION_FAILURE) from exc
    except UnsupportedPortalFetchError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise _RecordedExit(
            UI_CHANGED if isinstance(exc, PortalShapeChangedError) else GENERIC_FAILURE,
            error_class=type(exc).__name__,
            message=str(exc),
        ) from exc
    except OSError as exc:
        err_console.print(f"[red]Could not fetch job page:[/red] {exc}")
        raise _RecordedExit(
            GENERIC_FAILURE,
            error_class=type(exc).__name__,
            message=f"Could not fetch job page: {exc}",
        ) from exc

    job = result.job
    _learn_company_knowledge(config, job, narrator=narrator)
    console.print(
        f"[green]Stored[/green] {job.id}  {job.company}  {job.title}  "
        f"(match {job.match_score if job.match_score is not None else '—'})"
    )
    console.print(f"Wrote {result.job_json}")
    if result.match is not None:
        console.print(Panel(format_match_report(result.match), title="match"))
    if result.package_dir is not None:
        console.print(f"[green]Prepared[/green] {result.package_dir}")
        gob = result.package_dir / "getonboard_es.md"
        if gob.is_file():
            console.print(f"Get on Board Spanish drafts: {gob}")

    if not apply_changes:
        console.print(
            f"Package ready. Re-run with "
            f"[bold]jobbot application apply {job.id} --apply[/bold] "
            "to open the portal (you submit), or pass [bold]--apply[/bold] here."
        )
        return

    application_apply(job.id, apply_changes=True, yes=yes, cdp=cdp)


@app.command("capture")
def capture_share_url(
    url: Annotated[
        str | None,
        typer.Argument(
            help="Share URL from phone (Indeed vacancy, company career portal, or unknown).",
        ),
    ] = None,
    list_all: Annotated[
        bool,
        typer.Option(
            "--list",
            help="Show unfinished candidates (parked hard links, company portals, unrecognized)",
        ),
    ] = False,
    company: Annotated[
        str | None,
        typer.Option("--company", help="Company name when capturing a career portal"),
    ] = None,
    country: Annotated[
        str | None,
        typer.Option("--country", help="ISO country, e.g. CL"),
    ] = None,
) -> None:
    """Keep a share URL as a candidate — no fetch, no CAPTCHA (phone-friendly)."""
    from jobbot.jobs.capture import (
        CaptureKind,
        capture_paths,
        capture_url,
        list_candidates,
    )

    _, config = _session()
    if list_all:
        inv = list_candidates(config)
        paths = capture_paths(config)
        console.print("[bold]Candidate URLs (not finished yet)[/bold]")
        console.print(f"Hard links ({paths['hard_links']}):")
        if inv.hard_links:
            for item in inv.hard_links:
                console.print(f"  · {item}")
        else:
            console.print("  (none)")
        console.print(f"Company portals ({paths['companies']}):")
        if inv.company_portals:
            for company_id, site_url, status in inv.company_portals:
                console.print(f"  · {company_id}  {site_url}  [{status}]")
        else:
            console.print("  (none)")
        console.print(f"Unrecognized ({paths['unrecognized']}):")
        if inv.unrecognized:
            for item in inv.unrecognized:
                console.print(f"  · {item}")
        else:
            console.print("  (none)")
        return

    if url is None:
        err_console.print("[red]Provide a URL[/red], or [bold]jobbot capture --list[/bold].")
        raise typer.Exit(VALIDATION_FAILURE)

    try:
        result = capture_url(config, url, company=company, country=country)
    except ValueError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(VALIDATION_FAILURE) from exc

    label = {
        CaptureKind.HARD_LINK: "Hard link candidate",
        CaptureKind.COMPANY_PORTAL: "Company portal candidate",
        CaptureKind.UNRECOGNIZED: "Unrecognized candidate",
    }[result.kind]
    verb = "Already had" if result.already_present else "Captured"
    console.print(f"[green]{verb}[/green] {label}: {result.url}")
    if result.company_id:
        console.print(f"company_id={result.company_id}")
    console.print(result.detail)
    console.print(
        "Later on desktop: "
        "[bold]jobbot get --parked[/bold] (hard links) · "
        "[bold]jobbot companies recon …[/bold] (portals) · "
        "[bold]jobbot capture --list[/bold]"
    )


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


@workspace_app.command("delete")
def workspace_delete(
    name: Annotated[str, typer.Argument(help="Sandbox to remove")],
    yes: Annotated[bool, typer.Option("--yes", help="Skip confirmation")] = False,
) -> None:
    """Delete one sandbox. Never touches the checkout's own data/."""
    from jobbot.advisor import WorkspaceDeleteRefused, delete_workspace

    root = workspace_root(name)
    console.print(f"Delete {root}")
    if not yes and not typer.confirm("This removes that candidate's sandbox. Continue?"):
        raise typer.Abort
    try:
        delete_workspace(name, confirmed=True)
    except WorkspaceDeleteRefused as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(GENERIC_FAILURE) from exc
    console.print(f"Deleted {name}")


@workspace_app.command("consent")
def workspace_consent(
    name: Annotated[str, typer.Argument()],
    consented_at: Annotated[str, typer.Option("--at", help="ISO date the client agreed")],
    scope: Annotated[str, typer.Option("--scope", help="What the client agreed to")],
    delete_after: Annotated[
        str, typer.Option("--delete-after", help="ISO date to erase the sandbox")
    ],
) -> None:
    """Record local consent and a retention date for one sandbox."""
    from jobbot.advisor import Consent, write_consent

    root = workspace_root(name)
    if not root.is_dir():
        err_console.print(f"[red]No workspace {name}[/red]")
        raise typer.Exit(GENERIC_FAILURE)
    path = write_consent(
        root,
        Consent(consented_at=consented_at, scope=scope, delete_after=delete_after),
    )
    console.print(f"Wrote {path}")


def _vault_file() -> Path:
    from jobbot.vault import vault_path

    return vault_path(load_config().profile_path)


def _die_vault(exc: BaseException) -> None:
    err_console.print(f"[red]{exc}[/red]")
    raise typer.Exit(VALIDATION_FAILURE) from exc


@secrets_app.command("init")
def secrets_init() -> None:
    """Create an empty 0600 vault next to profile.yaml. Does not invent passwords."""
    from jobbot.vault import VaultError, init_vault

    path = _vault_file()
    try:
        init_vault(path)
    except VaultError as exc:
        _die_vault(exc)
    console.print(f"Created {path} (mode 0600). JobBot never invents entries.")
    console.print("[dim]Do not sync this file to Drive/Dropbox. Hidden is not encryption.[/dim]")


@secrets_app.command("list")
def secrets_list() -> None:
    """List stored site keys. Never prints a password."""
    from jobbot.vault import VaultError, load_vault

    path = _vault_file()
    try:
        vault = load_vault(path, missing_ok=True)
    except VaultError as exc:
        _die_vault(exc)
    if vault is None:
        console.print(f"No vault at {path} — run [bold]jobbot secrets init[/bold].")
        return
    sites = vault.sites()
    fill = "on" if vault.fill_login else "off"
    console.print(f"Vault {path}  fill_login={fill}  entries={len(sites)}")
    if not sites:
        console.print("[dim]Empty. jobbot secrets set SITE stores a password you type.[/dim]")
        return
    for site in sites:
        entry = vault.get(site)
        user = entry.username if entry and entry.username else "(profile email)"
        console.print(f"  {site}  user={user}  password=***")


@secrets_app.command("set")
def secrets_set(
    site: Annotated[str, typer.Argument(help="Portal key, e.g. indeed / getonboard / acme")],
    username: Annotated[
        str | None,
        typer.Option("--username", help="Login id if not the profile email"),
    ] = None,
    password_stdin: Annotated[
        bool,
        typer.Option(
            "--password-stdin",
            help="Read the password from stdin (never from argv / ps)",
        ),
    ] = False,
) -> None:
    """Store a password the human types. Empty values are refused, never invented."""
    import getpass

    from jobbot.vault import VaultError, put_entry

    if password_stdin:
        password = sys.stdin.read().rstrip("\r\n")
    else:
        password = getpass.getpass(f"Password for {site}: ")
        again = getpass.getpass("Repeat password: ")
        if password != again:
            _die_vault(VaultError("passwords do not match"))
    path = _vault_file()
    try:
        put_entry(path, site, password, username=username)
    except VaultError as exc:
        _die_vault(exc)
    console.print(f"Stored {site} in the vault (password not shown).")


@secrets_app.command("delete")
def secrets_delete(
    site: Annotated[str, typer.Argument(help="Portal key to remove")],
) -> None:
    """Drop one stored login. Does not delete the vault file."""
    from jobbot.vault import VaultError, delete_entry

    try:
        delete_entry(_vault_file(), site)
    except VaultError as exc:
        _die_vault(exc)
    console.print(f"Removed {site}.")


@secrets_app.command("allow-fill")
def secrets_allow_fill(
    yes: Annotated[bool, typer.Option("--yes", help="Skip the confirmation prompt")] = False,
) -> None:
    """Consent flag only: a later fill driver may type the password. Submit stays HITL."""
    from jobbot.vault import VaultError, set_fill_login

    if not yes and not typer.confirm(
        "Allow JobBot to type stored passwords into login fields later? "
        "CAPTCHA, 2FA, terms and submit stay yours.",
        default=False,
    ):
        console.print("fill_login left off.")
        return
    try:
        set_fill_login(_vault_file(), True)
    except VaultError as exc:
        _die_vault(exc)
    console.print(
        "fill_login=on. Typing into the browser is not shipped yet; CAPTCHA/2FA/submit stay human."
    )


@secrets_app.command("deny-fill")
def secrets_deny_fill() -> None:
    """Turn off the fill_login flag. Stored entries stay."""
    from jobbot.vault import VaultError, set_fill_login

    try:
        set_fill_login(_vault_file(), False)
    except VaultError as exc:
        _die_vault(exc)
    console.print("fill_login=off.")


advisor_app = typer.Typer(
    help="Cross-workspace status and a per-client report (no other candidate's data)",
    no_args_is_help=True,
)
app.add_typer(advisor_app, name="advisor")


@advisor_app.command("status")
def advisor_status() -> None:
    """One line per sandbox: fingerprint, counts, proposal, retention. No profile PII."""
    from datetime import UTC, datetime

    from jobbot.advisor import status_lines

    names = list_workspaces()
    lines = status_lines([(name, workspace_root(name)) for name in names], today=datetime.now(UTC))
    if not lines:
        console.print(f"No workspaces yet in {sandboxes_dir()}.")
        return
    for line in lines:
        console.print(line)


@advisor_app.command("report")
def advisor_report(
    since: Annotated[str, typer.Option("--since", help="Window, e.g. 7d")] = "7d",
) -> None:
    """Write a redacted report into the selected workspace's output/."""
    from datetime import UTC, datetime

    from jobbot.advisor import parse_since, write_report

    name = active_workspace()
    if not name:
        err_console.print("[red]Pass --workspace NAME[/red]")
        raise typer.Exit(VALIDATION_FAILURE)
    now = datetime.now(UTC)
    path = write_report(workspace_root(name), since=parse_since(since, now=now), now=now)
    console.print(f"Wrote {path}")


# ── profile ──────────────────────────────────────────────────────────────────


@profile_app.command("validate")
def profile_validate(
    strict: Annotated[
        bool,
        typer.Option(
            "--strict",
            help="Treat unknown YAML keys as errors (default: warn and exit 0)",
        ),
    ] = False,
    lang: Annotated[
        str | None,
        typer.Option("--lang", help="Check profile.<lang>.yaml ids and numbers (en)"),
    ] = None,
) -> None:
    """Validate data/profile.yaml and application_answers.yaml."""
    config = load_config()
    try:
        candidate = load_profile(config.profile_path)
        raw = load_profile_raw(config.profile_path)
    except ProfileLoadError as exc:
        err_console.print("[bold red]PROFILE INVALID[/bold red]")
        err_console.print(str(exc))
        raise typer.Exit(VALIDATION_FAILURE) from exc

    result = validate_candidate(candidate)
    unknowns = unknown_profile_keys(raw)
    if lang is not None:
        _reject_overlay(candidate, config.profile_path, lang)
    _reject_presentations(candidate, raw)
    if not result.ok or (strict and unknowns):
        err_console.print("[bold red]PROFILE INVALID[/bold red]")
        for issue in result.issues:
            err_console.print(str(issue))
        if strict:
            for issue in unknowns:
                err_console.print(f"{issue.path}: {issue.message}")
        raise typer.Exit(VALIDATION_FAILURE)

    from jobbot.jobs.eligibility import (
        default_answers_path,
        load_application_answers,
        salary_migration_hint,
    )

    answers_path = default_answers_path(config.root)
    try:
        answers = load_application_answers(answers_path)
    except ValueError as exc:
        err_console.print("[bold red]ANSWERS INVALID[/bold red]")
        err_console.print(str(exc))
        raise typer.Exit(VALIDATION_FAILURE) from exc

    console.print("[bold green]PROFILE VALID[/bold green]")
    for issue in result.warnings:
        err_console.print(f"[yellow]{issue.path}: {issue.message}[/yellow]")
    hint = salary_migration_hint(answers)
    if hint:
        console.print(hint, markup=False)
    for issue in unknowns:
        err_console.print(f"[yellow]{issue.path}: {issue.message}[/yellow]")
    console.print(f"Experiences: {len(candidate.experience)}")
    console.print(f"Achievements: {candidate.achievement_count()}")
    console.print(f"Skills: {candidate.skills.count()}")
    console.print(f"Publications: {len(candidate.publications)}")
    raise typer.Exit(SUCCESS)


def _reject_overlay(candidate: Candidate, profile_path: Path, lang: str) -> None:
    """An overlay id the base does not have, or a changed number, is exit 2."""
    from jobbot.profile.overlay import overlay_problems, read_overlay

    if lang != "en":
        err_console.print("--lang must be en")
        raise _QuietExit(VALIDATION_FAILURE)
    path = profile_path.with_name("profile.en.yaml")
    if not path.is_file():
        return
    try:
        texts = read_overlay(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        err_console.print(str(exc))
        raise _QuietExit(VALIDATION_FAILURE) from exc
    problems = overlay_problems(candidate, texts)
    if not problems:
        return
    err_console.print("[bold red]OVERLAY INVALID[/bold red]")
    for problem in problems:
        err_console.print(problem)
    raise _QuietExit(VALIDATION_FAILURE)


def _reject_presentations(candidate: Candidate, raw: dict[str, Any]) -> None:
    """A variant that changes the headline or adds a figure is exit 2."""
    from jobbot.profile.presentations import presentation_problems, presentations_block

    block = presentations_block(raw)
    if block is None:
        return
    problems = presentation_problems(candidate, block)
    if not problems:
        return
    err_console.print("[bold red]PRESENTATION INVALID[/bold red]")
    for problem in problems:
        err_console.print(problem)
    raise _QuietExit(VALIDATION_FAILURE)


@answers_app.command("show")
def profile_answers_show(
    reveal: Annotated[
        bool,
        typer.Option("--reveal", help="Print stored values. Default: block names only"),
    ] = False,
) -> None:
    """Show which application-answer blocks are filled, without values."""
    from jobbot.jobs.eligibility import (
        default_answers_path,
        format_answers_show,
        load_application_answers,
    )

    config = load_config()
    try:
        answers = load_application_answers(default_answers_path(config.root))
    except ValueError as exc:
        err_console.print(str(exc))
        raise typer.Exit(VALIDATION_FAILURE) from exc
    if reveal:
        import yaml

        payload = answers.model_dump(mode="json")
        console.print(
            yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
            markup=False,
        )
    else:
        console.print(format_answers_show(answers), markup=False)
    raise typer.Exit(SUCCESS)


@answers_app.command("set")
def profile_answers_set(
    key: Annotated[str, typer.Argument(help="Dotted key, such as salary.amount")],
    value: Annotated[str, typer.Argument(help="Value to store")],
    yes: Annotated[bool, typer.Option("--yes", help="Write the file. Default: print only")] = False,
) -> None:
    """Set one application answer. Refuses a national id. Writes only with --yes."""
    import yaml
    from pydantic import ValidationError

    from jobbot.jobs.eligibility import (
        ApplicationAnswers,
        answer_key_refused,
        assign_answer,
        default_answers_path,
        read_answers_mapping,
    )

    if answer_key_refused(key):
        err_console.print(f"no se guarda un identificador nacional: {key}")
        raise typer.Exit(VALIDATION_FAILURE)
    config = load_config()
    path = default_answers_path(config.root)
    try:
        data = read_answers_mapping(path)
        assign_answer(data, key, value)
        ApplicationAnswers.model_validate(data)
    except ValueError as exc:
        err_console.print(str(exc))
        raise typer.Exit(VALIDATION_FAILURE) from exc
    except ValidationError as exc:
        err_console.print(f"{key}: {exc}")
        raise typer.Exit(VALIDATION_FAILURE) from exc
    if not yes:
        console.print(f"no se escribió: {key}", markup=False)
        raise typer.Exit(SUCCESS)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    console.print(f"escrito: {key}", markup=False)
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
    for edu in candidate.education:
        table.add_row("Education", f"{edu.degree} ({edu.resolved_status()})")
    console.print(table)
    if candidate.summary:
        console.print(Panel(candidate.summary.strip(), title="Summary"))


@profile_app.command("skills-map")
def profile_skills_map(
    unbacked: Annotated[
        bool,
        typer.Option("--unbacked", help="Skills with no evidence, and achievements with no skill"),
    ] = False,
    apply_changes: Annotated[
        bool,
        typer.Option("--apply", help="Write the evidence links into profile.yaml after confirm"),
    ] = False,
) -> None:
    """Map each declared skill to the role or degree that already shows it."""
    from jobbot.cv.tune import backup_profile
    from jobbot.profile.skill_map import evidence_records, format_map, format_unbacked, map_skills

    config = load_config()
    try:
        candidate = load_profile(config.profile_path)
        raw = load_profile_raw(config.profile_path)
    except ProfileLoadError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(VALIDATION_FAILURE) from exc

    uses = map_skills(candidate)
    lines = format_unbacked(candidate) if unbacked else format_map(uses)
    if not lines:
        console.print("No skill evidence.")
    for line in lines:
        console.print(line, markup=False)
    if not apply_changes:
        raise typer.Exit(SUCCESS)
    records = evidence_records(uses)
    if not records:
        console.print("Nothing to write.")
        raise typer.Exit(SUCCESS)
    if not typer.confirm("Write skill evidence into profile.yaml?", default=False):
        console.print("Nothing written.")
        raise typer.Exit(SUCCESS)
    raw["skill_evidence"] = [record.model_dump() for record in records]
    backup = backup_profile(config.profile_path)
    config.profile_path.write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    stored = load_profile(config.profile_path)
    check = validate_candidate(stored)
    if not check.ok:
        for issue in check.issues:
            err_console.print(str(issue))
        raise typer.Exit(VALIDATION_FAILURE)
    console.print(f"Wrote skill evidence. Backup: {backup.name}", markup=False)
    raise typer.Exit(SUCCESS)


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
    promote: Annotated[
        bool,
        typer.Option(
            "--promote",
            help="Also copy generated YAML over profile.yaml (after validate)",
        ),
    ] = False,
) -> None:
    """Import a PDF CV into profile.generated.yaml (and optionally profile.yaml)."""
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

    if promote:
        try:
            candidate = load_profile(destination)
        except ProfileLoadError as exc:
            err_console.print(f"[red]Generated profile invalid: {exc}[/red]")
            raise typer.Exit(VALIDATION_FAILURE) from exc
        check = validate_candidate(candidate)
        if not check.ok:
            for issue in check.issues:
                err_console.print(f"[red]- {issue}[/red]")
            raise typer.Exit(VALIDATION_FAILURE)
        shutil.copy2(destination, config.profile_path)
        _restamp_after_profile_promote(config)
        console.print(f"[green]Promoted[/green] → {config.profile_path}")
    else:
        console.print(
            Panel(
                "A PDF carries no structure, so every field is a guess.\n"
                "Review the generated YAML, then:\n"
                "  jobbot profile promote-generated\n"
                "  jobbot profile validate\n"
                "Or re-run with --promote after a quick review.",
                title="Next steps",
            )
        )


@profile_app.command("import-folder")
def profile_import_folder(
    folder: Annotated[Path, typer.Argument(help="Directory of PDF CVs. Nothing is written.")],
) -> None:
    """List role ids a folder would add or replace. Does not write profile.yaml."""
    from jobbot.profile.folder_import import folder_report
    from jobbot.profile.loader import ProfileLoadError, load_profile

    if not folder.is_dir():
        err_console.print("import-folder needs a directory.")
        raise _QuietExit(VALIDATION_FAILURE)
    config = load_config()
    stored: set[str] = set()
    if config.profile_path.is_file():
        try:
            candidate = load_profile(config.profile_path)
        except ProfileLoadError as exc:
            err_console.print(str(exc))
            raise _QuietExit(VALIDATION_FAILURE) from exc
        stored = {exp.id for exp in candidate.experience}
    new, conflict, unread = folder_report(folder, stored)
    for role_id in new:
        console.print(f"new: {role_id}")
    for role_id in conflict:
        console.print(f"conflict: {role_id}")
    for name in unread:
        err_console.print(f"unread: {name}")
    if not new and not conflict and not unread:
        console.print("no pdfs")
    raise typer.Exit(SUCCESS)


@profile_app.command("rejection")
def profile_rejection(
    text: Annotated[str, typer.Option("--text", help="Why the suggestion does not fit")],
) -> None:
    """Classify a rejection. A preference or a condition does not edit the profile."""
    from jobbot.profile.rejection import may_edit_profile, rejection_kind

    kind = rejection_kind(text)
    if may_edit_profile(kind):
        console.print(f"{kind}: not written")
    else:
        console.print(f"{kind}: profile unchanged")
    raise typer.Exit(SUCCESS)


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
    _restamp_after_profile_promote(config)
    console.print(f"[green]Promoted[/green] {generated} → {target}")


@profile_app.command("suggest-from-market")
def profile_suggest_from_market(
    min_count: Annotated[
        int,
        typer.Option("--min-count", help="Min JD occurrences for a market term"),
    ] = 2,
    job_id: Annotated[
        str | None,
        typer.Option("--job", help="Limit market read to one stored job (Jxxxx)"),
    ] = None,
    ask: Annotated[
        bool,
        typer.Option(
            "--ask/--no-ask",
            help="Confirm suspected gaps on stdin (off by default; also used with --promote)",
        ),
    ] = False,
    promote: Annotated[
        bool,
        typer.Option(
            "--promote",
            help="Write confirmed skills into profile.yaml (after confirmation)",
        ),
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y")] = False,
) -> None:
    """Write market suggestions. Asks on stdin only with --ask or when promoting."""
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

    repo = JobRepository(session)
    if job_id:
        job = repo.get(job_id)
        if job is None:
            err_console.print(f"[red]Job not found: {job_id}[/red]")
            raise typer.Exit(VALIDATION_FAILURE)
        jobs = [job]
        # One posting: a single occurrence is enough to surface the term.
        min_count = min(min_count, 1)
    else:
        jobs = repo.list_all()
    if not jobs:
        console.print("No stored jobs. Run jobs search or linkedin sweep first.")
        raise typer.Exit(SUCCESS)

    narrator = _narrator()
    scope = f"job {jobs[0].id}" if job_id else f"{len(jobs)} job descriptions"
    narrator.phase(Phase.RECEIVING_WORLD, scope, may_ask=ask)
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


_QUERY_ORIGIN_LABEL = {
    "competency": "skill a role mentions",
    "achievements": "repeated in achievements",
    "title": "title held",
}


@profile_app.command("queries")
def profile_queries(
    limit: Annotated[int, typer.Option("--limit", help="How many queries to derive")] = 8,
    apply_changes: Annotated[
        bool,
        typer.Option(
            "--apply",
            help="Save the derived set as search_queries in profile.yaml (confirm; backup)",
        ),
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
    check: Annotated[
        bool,
        typer.Option(
            "--check",
            help="Measure each query against text-search sources; stores nothing",
        ),
    ] = False,
    as_json: Annotated[
        bool,
        typer.Option("--json", help="With --check, print rows as JSON"),
    ] = False,
    source: Annotated[
        list[str] | None,
        typer.Option("--source", help="Text-search source to measure (repeatable)"),
    ] = None,
) -> None:
    """Job searches from your experience; --check measures them, --apply saves them."""
    from jobbot.profile.search_queries import derive_search_queries

    if check and apply_changes:
        err_console.print("[red]--check no escribe; no se combina con --apply.[/red]")
        raise typer.Exit(VALIDATION_FAILURE)
    config = load_config()
    try:
        candidate = load_profile(config.profile_path)
    except ProfileLoadError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(VALIDATION_FAILURE) from exc
    if check:
        _check_profile_queries(config, candidate, source=source, as_json=as_json, limit=limit)
        return

    if candidate.search_queries:
        console.print("[bold]Saved in profile.yaml[/bold] (searches use these):")
        for text in candidate.search_queries:
            console.print(f"  • {text}")
    derived = derive_search_queries(candidate, limit=max(1, limit))
    if not derived:
        console.print("Nothing to derive: the profile has no experience to search from.")
        return

    table = Table(title="Derived from your experience")
    table.add_column("Query")
    table.add_column("From")
    table.add_column("Backed by", justify="right")
    for query in derived:
        table.add_row(
            query.text,
            _QUERY_ORIGIN_LABEL[query.origin.value],
            f"{len(query.evidence)} role(s)",
        )
    console.print(table)

    if not apply_changes:
        console.print(
            "Dry-run. Re-run with [bold]--apply[/bold] to save them as search_queries; "
            "edit the list in profile.yaml afterwards."
        )
        return
    texts = [query.text for query in derived]
    if texts == candidate.search_queries:
        console.print("Already saved.")
        return
    question = f"Save these {len(texts)} queries as search_queries in profile.yaml?"
    if not yes and not typer.confirm(question, default=False):
        console.print("Nothing written.")
        return
    raw = load_profile_raw(config.profile_path)
    raw["search_queries"] = texts
    backup = config.profile_path.with_suffix(config.profile_path.suffix + ".bak")
    shutil.copy2(config.profile_path, backup)
    config.profile_path.write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    console.print(f"Backup: {backup}")
    console.print(f"[green]Saved[/green] {len(texts)} search queries → {config.profile_path}")
    console.print("Next: [bold]jobbot getonboard search[/bold] (no query needed)")


def _check_profile_queries(
    config: JobbotConfig,
    candidate: Candidate,
    *,
    source: list[str] | None,
    as_json: bool,
    limit: int,
) -> None:
    from jobbot.profile.query_check import (
        format_cell,
        measure_queries,
        search_source_titles,
        sources_or_reject,
    )
    from jobbot.profile.search_queries import search_queries_for

    chosen = sources_or_reject(source)
    if isinstance(chosen, str):
        err_console.print(f"[red]{chosen}[/red]")
        raise typer.Exit(VALIDATION_FAILURE)
    queries = search_queries_for(candidate, limit=max(1, limit)).queries
    if not queries:
        err_console.print("[red]No hay consultas que medir.[/red]")
        raise typer.Exit(VALIDATION_FAILURE)

    def search(source_id: str, query: str) -> list[str]:
        return search_source_titles(source_id, query, config=config)

    report = measure_queries(candidate, queries, chosen, search)
    if as_json:
        console.print_json(data=report.to_dict())
    else:
        table = Table(title="Query check (nothing stored)")
        table.add_column("Query")
        table.add_column("Source")
        table.add_column("Result")
        for cell in report.cells:
            table.add_row(cell.query, cell.source, format_cell(cell))
        console.print(table)
        for warning in report.warnings:
            where = f" [{warning.source}]" if warning.source else ""
            console.print(f"{warning.code}{where}: {warning.suggestion}")
    if report.cells and all(cell.error for cell in report.cells):
        err_console.print("[red]Todas las fuentes fallaron.[/red]")
        raise typer.Exit(GENERIC_FAILURE)


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


@cv_app.command("status")
def cv_status(
    as_json: Annotated[bool, typer.Option("--json", help="Machine-readable rows")] = False,
) -> None:
    """Alias for `jobbot status`: permanent + active company presence."""
    _print_cv_status(as_json=as_json)


@cv_app.command("gap")
def cv_gap(
    job_id: Annotated[str, typer.Option("--job", help="Stored posting id")],
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Print the stable gap schema"),
    ] = False,
) -> None:
    """Show which posting terms the profile already evidences."""
    from jobbot.cv.gap import gap_report, write_gap_report

    config = load_config()
    try:
        candidate = load_profile(config.profile_path)
    except ProfileLoadError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(VALIDATION_FAILURE) from exc
    session, _ = _session()
    job = JobRepository(session).get(job_id)
    if job is None:
        err_console.print(f"[red]Job not found: {job_id}[/red]")
        raise typer.Exit(GENERIC_FAILURE)
    report = gap_report(candidate, job)
    path = write_gap_report(report, config.output_dir)
    if as_json:
        console.print_json(data=report.as_dict())
    else:
        for line in report.lines():
            console.print(line)
    err_console.print(f"[dim]{path}[/dim]")


@cv_app.command("check")
def cv_check(
    job_id: Annotated[
        str | None,
        typer.Option("--job", help="Also list posting terms the profile does not cover"),
    ] = None,
) -> None:
    """Print a structural CV checklist. Never rewrites the profile."""
    from jobbot.cv.check import check_cv, write_cv_check

    config = load_config()
    try:
        candidate = load_profile(config.profile_path)
    except ProfileLoadError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(VALIDATION_FAILURE) from exc
    job = None
    if job_id:
        session, _ = _session()
        job = JobRepository(session).get(job_id)
        if job is None:
            err_console.print(f"[red]Job not found: {job_id}[/red]")
            raise _QuietExit(VALIDATION_FAILURE)
    report = check_cv(candidate, job)
    path = write_cv_check(report, config.output_dir)
    for line in report.lines():
        console.print(line)
    err_console.print(f"[dim]{path}[/dim]")


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
    full: Annotated[
        bool,
        typer.Option(
            "--full",
            help="With --job: keep every role and achievement, most related first per role",
        ),
    ] = False,
    strict: Annotated[
        bool,
        typer.Option("--strict", help="Exit 2 when the text layer has a finding"),
    ] = False,
    lang: Annotated[
        str | None,
        typer.Option("--lang", help="ATS headings: es or en"),
    ] = None,
    highlights: Annotated[
        bool,
        typer.Option(
            "--highlights",
            help="Open with quantified bullets already in the profile.",
        ),
    ] = False,
) -> None:
    """Build CV from profile.yaml (base or job-specific)."""
    if full and not job_id:
        raise typer.BadParameter(
            "--full only applies with --job; the base CV already keeps every fact.",
            param_hint="--full",
        )
    if lang is not None and lang not in ("es", "en"):
        raise typer.BadParameter("--lang must be es or en", param_hint="--lang")
    config = load_config()
    try:
        candidate = load_profile(config.profile_path)
        raw = load_profile_raw(config.profile_path)
    except ProfileLoadError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(VALIDATION_FAILURE) from exc

    result = validate_candidate(candidate)
    if not result.ok:
        err_console.print("[bold red]PROFILE INVALID[/bold red]")
        for issue in result.issues:
            err_console.print(str(issue))
        raise typer.Exit(VALIDATION_FAILURE)

    unknowns = unknown_profile_keys(raw)
    if unknowns:
        err_console.print(
            f"[yellow]{len(unknowns)} claves desconocidas en profile.yaml se ignoran "
            "(jobbot profile validate).[/yellow]"
        )

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

    highlight_lines: tuple[str, ...] = ()
    if highlights:
        from jobbot.cv.highlights import select_highlights

        plan = select_highlights(candidate, job)
        highlight_lines = plan.lines
        if plan.warning:
            err_console.print(f"[yellow]{plan.warning}[/yellow]")

    from jobbot.cv.build import application_log_options

    try:
        outputs = build_cv(
            candidate=candidate,
            templates_dir=config.templates_dir,
            output_dir=config.output_dir,
            target=target,
            job=job,
            match=match,
            style=style,
            application_log=application_log_options(config.cv),
            credit=config.cv.jobbot_signature,
            full=full,
            language=lang,
            configured_language=config.cv.language,
            compact_before=config.cv.compact_before,
            max_pages=config.cv.max_pages,
            highlight_lines=highlight_lines,
        )
    except (FileNotFoundError, RuntimeError) as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(GENERIC_FAILURE) from exc

    for path in outputs:
        console.print(f"[green]Wrote[/green] {path}")
    if job is not None and match is not None:
        from jobbot.cv.selection import select_for_job

        picked = select_for_job(candidate, job, match, full=full)
        if not picked.used_posting_terms:
            err_console.print(
                "selección sin términos del aviso; revisa selection.json o re-parsea el aviso"
            )
    from jobbot.cv.text_layer import issues_for_outputs

    layer = issues_for_outputs(outputs, candidate, job)
    for finding in layer:
        err_console.print(f"text layer: {finding.kind}: {finding.detail}")
    if strict and layer:
        raise typer.Exit(VALIDATION_FAILURE)


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
    job_id: Annotated[
        str | None,
        typer.Option("--job", help="Scope suggestions to one stored job (Jxxxx)"),
    ] = None,
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
    from jobbot.cv.tune import backup_profile, char_delta_label, prompt_advice_decision
    from jobbot.portals.form_learn import default_form_knowledge_path, load_form_knowledge
    from jobbot.recruiters.playbook import advisor_notes

    session, config = _session()
    try:
        candidate = load_profile(config.profile_path)
    except ProfileLoadError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(VALIDATION_FAILURE) from exc

    repo = JobRepository(session)
    if job_id:
        job = repo.get(job_id)
        if job is None:
            err_console.print(f"[red]Job not found: {job_id}[/red]")
            raise typer.Exit(VALIDATION_FAILURE)
        jobs = [job]
    else:
        jobs = repo.list_all()
    forms = load_form_knowledge(default_form_knowledge_path(config.root))
    notes = advisor_notes(config.root)
    log_path = default_advice_log_path(config.output_dir)

    narrator = _narrator()
    scope = f"job {jobs[0].id}" if job_id and jobs else f"{len(jobs)} JD"
    narrator.phase(
        Phase.RECEIVING_WORLD,
        f"{scope} · {len(forms)} formulario(s) · {len(notes)} práctica(s)",
    )
    suggestions = advise(
        candidate,
        jobs=jobs,
        forms=forms,
        playbook=notes,
        limit=max(1, min(limit, 5)),
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
            body.append(f"delta:    {char_delta_label(item.before, item.after)}")
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
        console.print(f"  delta:    {char_delta_label(item.before, item.after)}")
        decision = prompt_advice_decision(prompt=lambda msg: typer.prompt(msg, default="N"))
        if decision == "skip_all":
            console.print("Stopped — remaining suggestions left untouched.")
            break
        if decision != "yes":
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
    backup = backup_profile(config.profile_path)
    config.profile_path.write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    console.print(f"Backup: {backup}")
    console.print(f"[green]Applied[/green] {applied} rewording(s) → {config.profile_path}")
    console.print("Next: [bold]jobbot cv build[/bold] then [bold]jobbot cv propagate[/bold]")


@cv_app.command("tune-for")
def cv_tune_for(
    ref: Annotated[
        str,
        typer.Argument(help="Stored job id (Jxxxx) or a hard-link URL to ingest first"),
    ],
    apply_changes: Annotated[
        bool,
        typer.Option("--apply", help="Confirm each suggestion and write profile.yaml"),
    ] = False,
    limit: Annotated[
        int,
        typer.Option("--limit", help="Max suggestions this posting may make (cap 5)"),
    ] = 3,
) -> None:
    """Bounded baseline improvement from one posting (~5% delta; #54).

    Stores the URL if needed, then runs density/clarity advise scoped to that job.
    Never invents; never deletes facts. HITL before any write.
    """
    from jobbot.cv.tune import resolve_tune_ref

    try:
        kind, value = resolve_tune_ref(ref)
    except ValueError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(VALIDATION_FAILURE) from exc

    session, config = _session()
    job_id = value
    if kind == "url":
        try:
            candidate = load_profile(config.profile_path)
        except ProfileLoadError as exc:
            err_console.print(f"[red]{exc}[/red]")
            raise typer.Exit(VALIDATION_FAILURE) from exc
        from jobbot.jobs.from_url import ingest_hard_link

        try:
            result = ingest_hard_link(
                config,
                session,
                value,
                candidate=candidate,
                build=False,
                prepare=False,
            )
        except Exception as exc:  # noqa: BLE001 — surface ingest refusal to the user
            err_console.print(f"[red]Could not ingest URL:[/red] {exc}")
            raise typer.Exit(VALIDATION_FAILURE) from exc
        job_id = result.job.id
        console.print(f"[green]Stored[/green] {job_id} from hard link")

    # Reuse advise with the same HITL path; scope via --job.
    cv_advise(
        limit=max(1, min(limit, 5)),
        apply_changes=apply_changes,
        job_id=job_id,
        axis=None,
        llm=False,
        llm_deep=False,
        max_llm_calls=3,
        dry_run=False,
    )


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


@cv_app.command("update")
def cv_update() -> None:
    """List active portals this workspace has not integrated. Does not write the profile."""
    from jobbot.companies.registry import load_companies
    from jobbot.cv.portal_update import (
        format_new_portals,
        integration_log_path,
        load_seen,
        unseen_active_portals,
    )

    config = load_config()
    registry = load_companies(config.companies_path)
    seen = load_seen(integration_log_path(config.output_dir))
    for line in format_new_portals(unseen_active_portals(registry, seen)):
        console.print(line)
    raise typer.Exit(SUCCESS)


@cv_app.command("translate")
def cv_translate(
    lang: Annotated[
        str,
        typer.Option("--lang", help="Check output/cv/<lang>.yaml against the profile (en)"),
    ] = "en",
) -> None:
    """Check a derived translation keeps the source numbers, names, and skills."""
    from jobbot.cv.translate_check import translation_problems
    from jobbot.profile.loader import ProfileLoadError, load_profile
    from jobbot.profile.overlay import read_overlay

    if lang != "en":
        err_console.print("--lang must be en")
        raise _QuietExit(VALIDATION_FAILURE)
    config = load_config()
    try:
        candidate = load_profile(config.profile_path)
    except ProfileLoadError as exc:
        err_console.print(str(exc))
        raise _QuietExit(VALIDATION_FAILURE) from exc
    path = config.output_dir / "cv" / "en.yaml"
    if not path.is_file():
        console.print("no translation; the source text stays")
        raise typer.Exit(SUCCESS)
    try:
        texts = read_overlay(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        err_console.print(str(exc))
        raise _QuietExit(VALIDATION_FAILURE) from exc
    problems = translation_problems(candidate, texts)
    if problems:
        err_console.print("[bold red]TRANSLATION INVALID[/bold red]")
        for problem in problems:
            err_console.print(problem)
        raise _QuietExit(VALIDATION_FAILURE)
    console.print("translation keeps the source")
    raise typer.Exit(SUCCESS)


@cv_app.command("propagate")
def cv_propagate(
    targets: Annotated[
        str,
        typer.Option(
            "--targets",
            help=(
                "Permanent profiles only: all|permanent|cv,getonboard,indeed,linkedin "
                "(company portals: jobbot cv sync)"
            ),
        ),
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
        UnknownTargetError,
        parse_targets,
        plan_propagation,
        summarize_plans,
    )

    config = load_config()
    candidate = _load_valid_candidate(config)
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
    _print_permanent_plan_table(plans, title="CV propagation plan")

    if not apply_changes:
        console.print(
            "Dry-run. Re-run with [bold]--apply[/bold] to rebuild the CV and open/write "
            "each destination (you confirm one by one). "
            "For active company portals see [bold]jobbot cv sync[/bold]."
        )
        raise typer.Exit(SUCCESS)

    _apply_permanent_plans(
        plans,
        config=config,
        candidate=candidate,
        style=style,
        section=section,
        cdp=cdp,
        yes=yes,
        apply_changes=apply_changes,
    )


@cv_app.command("sync")
def cv_sync(
    apply_changes: Annotated[
        bool,
        typer.Option(
            "--apply",
            help="Write permanent portals and active company fill/signup (default: dry-run)",
        ),
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
    """Standing presence: permanent profiles + active company portals (issue #43)."""
    from jobbot.browser.sessions import inspect_sessions
    from jobbot.cv.propagate import PropagationTarget, summarize_plans
    from jobbot.cv.sync import page_urls_from_cdp, plan_sync

    config = load_config()
    candidate = _load_valid_candidate(config)
    sessions = inspect_sessions(
        config.root,
        sites=[t.value for t in PropagationTarget if t != PropagationTarget.CV],
    )
    plan = plan_sync(
        config,
        candidate,
        section=section,
        sessions=sessions,
        cdp_url=cdp,
        page_urls=page_urls_from_cdp(cdp),
    )
    narrator = _narrator()
    narrator.phase(Phase.PROPAGATING_CV, summarize_plans(plan.permanent))
    _print_permanent_plan_table(plan.permanent, title="CV sync — permanent profiles")

    company_table = Table(title="CV sync — active company portals")
    company_table.add_column("Company")
    company_table.add_column("ATS")
    company_table.add_column("Action")
    company_table.add_column("Hint")
    if plan.companies:
        for row in plan.companies:
            company_table.add_row(
                row.company_name,
                row.ats.value,
                row.action,
                row.hint,
            )
        console.print(company_table)
    else:
        console.print(
            "[dim]No active company portals in data/companies.yaml — "
            "promote candidates first, or import a shared export.[/dim]"
        )

    if not apply_changes:
        console.print(
            "Dry-run. Re-run with [bold]--apply[/bold] to write permanent destinations "
            "and handle active company portals one by one (HITL). "
            "Needs-account without local evidence → signup fill (#44); "
            "with account evidence → login only (#56); "
            "fill rows open the career URL and type only profile facts — you submit. "
            "A yes is not a receipt."
        )
        raise typer.Exit(SUCCESS)

    _apply_permanent_plans(
        plan.permanent,
        config=config,
        candidate=candidate,
        style=style,
        section=section,
        cdp=cdp,
        yes=yes,
        apply_changes=apply_changes,
    )
    _apply_company_sync_rows(plan.companies, config=config, candidate=candidate, cdp=cdp, yes=yes)


def _apply_company_sync_rows(
    rows: Sequence[Any],
    *,
    config: JobbotConfig,
    candidate: Candidate,
    cdp: str | None,
    yes: bool,
) -> None:
    from jobbot.adapters.getonboard.cv_upload import resolve_base_cv
    from jobbot.cv.company_apply import company_apply_intent, has_receipt_for
    from jobbot.cv.sync import CompanySyncRow

    for row in rows:
        assert isinstance(row, CompanySyncRow)
        evidenced = row.session_evidenced or has_receipt_for(config.output_dir, row.url)
        intent = company_apply_intent(
            row,
            candidate,
            cv_path=resolve_base_cv(config.output_dir),
            has_account_evidence=evidenced,
        )
        if intent.mode == "skip":
            console.print(f"{row.company_name}: skipped — {intent.note}")
            continue
        if intent.mode == "login":
            if not yes and not typer.confirm(
                f"Open login for {row.company_name}? (you type the password)",
                default=False,
            ):
                console.print(f"{row.company_name}: skipped.")
                continue
            _run_company_fill(intent, config=config, candidate=candidate, cdp=cdp)
            continue
        if intent.mode == "signup_fill":
            prompt = (
                f"Fill known signup fields for {row.company_name} "
                "(password/terms/create stay with you; gaps become learned issues)?"
            )
        else:
            prompt = (
                f"Open {row.company_name} career site and fill known profile fields "
                "(you submit; a yes is not a receipt)?"
            )
        if not yes and not typer.confirm(prompt, default=False):
            console.print(f"{row.company_name}: skipped.")
            continue
        _run_company_fill(intent, config=config, candidate=candidate, cdp=cdp)


def _print_company_signup_sheet(intent: Any) -> None:
    console.print(
        Panel(
            f"[bold]{intent.company_name}[/bold] ({intent.company_id})\n"
            f"{intent.url}\n\n{intent.note}",
            title="Registration (you complete it)",
        )
    )
    table = Table(title="Have this at hand")
    table.add_column("The portal asks")
    table.add_column("Your profile answers")
    table.add_column("From")
    for item in intent.sheet:
        value = item.value or "[yellow]you decide[/yellow]"
        table.add_row(item.label[:40], value[:46], item.source[:34])
    console.print(table)
    console.print(
        "[dim]JobBot does not create the account, does not invent a password, "
        "does not accept terms, and does not solve CAPTCHA/2FA.[/dim]"
    )


def _run_company_fill(
    intent: Any,
    *,
    config: JobbotConfig,
    candidate: Candidate,
    cdp: str | None,
    ats: str = "unknown",
    open_gap_issue: bool = False,
    yes: bool = False,
) -> None:
    from jobbot.browser.cdp import resolve_cdp_url
    from jobbot.browser.session import BrowserSession
    from jobbot.cv.company_apply import MissingAdaptedCvError, perform_company_apply
    from jobbot.portals.field_gap_issue import create_field_gap_issue
    from jobbot.portals.form_learn import (
        default_form_knowledge_path,
        load_form_knowledge,
        save_form_knowledge,
        upsert_form,
    )

    cdp_url = resolve_cdp_url(cdp)
    try:
        with BrowserSession(
            profile_dir=config.root / "browser-data" / "companies-sync-cdp",
            headless=False,
            cdp_url=cdp_url,
            debug_root=config.output_dir / "debug",
        ) as browser:
            result = perform_company_apply(
                intent,
                candidate,
                page=browser.page,
                output_dir=config.output_dir,
                ats=ats,
            )
    except MissingAdaptedCvError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(VALIDATION_FAILURE) from exc

    if intent.mode == "login":
        console.print(f"[green]Opened login[/green] {intent.url} — type the password yourself.")
        return

    console.print(
        f"[green]Opened[/green] {intent.url} · filled {len(result.filled)} field(s)"
        + (" · CV attached" if result.attached else "")
    )
    assert result.submitted is False
    if result.form is not None and result.form.readable:
        path = default_form_knowledge_path(config.root)
        forms = upsert_form(load_form_knowledge(path), result.form)
        save_form_knowledge(forms, path)
        console.print(f"Learned form → {path}")
    if result.gap_labels or result.new_fields:
        console.print(
            f"[cyan]Learned {len(result.gap_labels) + len(result.new_fields)} gap(s)[/cyan] "
            "— not invented. Resolve via GitHub issue (HITL)."
        )
        for label in result.gap_labels:
            console.print(f"  • {label}")
    if result.gap_issue is not None:
        console.print(
            Panel(
                f"{result.gap_issue.title}\n\n{result.gap_issue.body}",
                title="field gap issue",
            )
        )
        if open_gap_issue:
            if yes or typer.confirm("Create GitHub issue with gh?", default=False):
                try:
                    url = create_field_gap_issue(result.gap_issue)
                    console.print(f"[green]Created[/green] {url or '(see gh output)'}")
                except RuntimeError as exc:
                    err_console.print(f"[red]gh failed:[/red] {exc}")
            else:
                console.print("Issue not created (draft above still stands).")
    if result.receipt_path is not None:
        console.print(f"Page receipt: {result.receipt_path}")
    else:
        console.print(
            "[yellow]No page receipt[/yellow] — status stays unknown until the portal "
            "shows a profile fact. Submit yourself; JobBot does not click submit."
        )


def _load_valid_candidate(config: JobbotConfig) -> Candidate:
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
    return candidate


def _print_permanent_plan_table(plans: Sequence[Any], *, title: str) -> None:
    from jobbot.cv.propagate import TargetPlan

    table = Table(title=title)
    table.add_column("Destination")
    table.add_column("Operations")
    table.add_column("Detail")
    for plan in plans:
        assert isinstance(plan, TargetPlan)
        detail = plan.blocked_reason or plan.note or ""
        if plan.hint:
            detail = f"{detail} → {plan.hint}"
        table.add_row(
            plan.target.value,
            "blocked" if not plan.ready else str(len(plan.operations)),
            detail,
        )
    console.print(table)
    narrator = _narrator()
    for plan in plans:
        assert isinstance(plan, TargetPlan)
        for operation in plan.operations:
            narrator.note(f"{plan.target.value}: {operation}")


def _apply_permanent_plans(
    plans: Sequence[Any],
    *,
    config: JobbotConfig,
    candidate: Candidate,
    style: CvStyle,
    section: str,
    cdp: str | None,
    yes: bool,
    apply_changes: bool,
) -> None:
    from jobbot.cv.propagate import PropagationTarget, TargetPlan

    for plan in plans:
        assert isinstance(plan, TargetPlan)
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
                credit=config.cv.jobbot_signature,
                compact_before=config.cv.compact_before,
                max_pages=config.cv.max_pages,
                language=None,
                configured_language=config.cv.language,
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
        ProfileEditError,
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
        try:
            writes = plan_writes(read_current(page), desired, page=page)
        except ProfileEditError as exc:
            err_console.print(f"[red]{exc}[/red]")
            raise typer.Exit(GENERIC_FAILURE) from exc
        if not writes:
            console.print("getonboard: el portal ya tiene estos textos.")
        else:
            for write in writes:
                console.print(f"  {write.describe()}")
            if not yes and not typer.confirm(
                f"Write these {len(writes)} field(s) on Get on Board?",
                default=False,
            ):
                console.print("getonboard: skipped profile fields.")
            else:
                try:
                    done = apply_writes(page, writes)
                except ProfileEditError as exc:
                    err_console.print(f"[red]{exc}[/red]")
                    raise typer.Exit(GENERIC_FAILURE) from exc
                console.print(f"[green]Wrote[/green] {len(done)} field(s) on Get on Board.")
    _propagate_getonboard_cv(config, cdp=cdp, yes=yes)


def _propagate_getonboard_cv(
    config: JobbotConfig,
    *,
    cdp: str | None,
    yes: bool,
) -> None:
    """Upload output/base/cv.pdf after validating it; mark default when confirmed."""
    from jobbot.adapters.getonboard.cv_upload import (
        PROFILE_REWRITE_WARNING,
        resolve_base_cv,
        upload_cv,
        validate_cv_for_upload,
        write_upload_receipt,
    )

    path = resolve_base_cv(config.output_dir)
    check = validate_cv_for_upload(path)
    for line in check.summary_lines():
        console.print(f"  {line}", soft_wrap=False, overflow="ignore", crop=False)
    if not check.ok:
        err_console.print("[yellow]CV not uploaded: local validation failed.[/yellow]")
        return
    if not yes and not typer.confirm(
        "Upload this PDF to Get on Board Tus CVs and mark it default?",
        default=False,
    ):
        console.print("getonboard CV: skipped.")
        return
    with _getonboard_session(config, cdp) as browser:
        result = upload_cv(
            browser.page,
            path,
            label="CV base",
            make_default=True,
            check=check,
        )
    write_upload_receipt(config.output_dir, check, result)
    console.print(
        f"[green]Uploaded[/green] {result.path.name} as {result.label!r} "
        f"(default={result.is_default}) → {result.resumes_url}"
    )
    console.print(PROFILE_REWRITE_WARNING)


def _propagate_indeed(config: JobbotConfig, *, section: str, cdp: str | None, yes: bool) -> None:
    from jobbot.adapters.indeed.client import IndeedAdapter
    from jobbot.adapters.indeed.resume_edit import IndeedUiChanged
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
    try:
        console.print(adapter.apply_sync_plan(plan, section=section).message)
    except IndeedUiChanged as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(UI_CHANGED) from exc


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


def _add_buk_list(session: Session, config: JobbotConfig, html: str, url: str) -> None:
    """Store each card of a saved Buk list. A page without cards is a shape change."""
    from jobbot.adapters.buk.listings import BukShapeError, jobs_from_list_html

    try:
        jobs = jobs_from_list_html(html, page_url=url)
    except BukShapeError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(UI_CHANGED) from exc
    repo = JobRepository(session)
    for job in jobs:
        stored = repo.upsert_external(job)
        path = write_job_json(stored, config.output_dir)
        console.print(f"[green]Added[/green] {stored.id}  {stored.company}  {stored.title}")
        console.print(f"Wrote {path}")


@jobs_app.command("add")
def jobs_add(
    file: Annotated[
        Path | None,
        typer.Option("--file", "-f", help="Path to JD text file"),
    ] = None,
    url: Annotated[
        str | None,
        typer.Option(
            "--url",
            help="Posting URL. A Workday URL downloads itself; a PDF URL reads its text layer",
        ),
    ] = None,
    stdin: Annotated[
        bool,
        typer.Option("--stdin", help="Read JD from stdin"),
    ] = False,
) -> None:
    """Add a job posting from a text file, stdin, or a public PDF URL."""
    from jobbot.portals.detect import AtsKind, detect_ats

    session, config = _session()
    if url:
        from jobbot.jobs.open_signals import trabajando_needs_slug

        if trabajando_needs_slug(url):
            err_console.print(
                "trabajando.cl needs the slug in the URL, not the id alone. Not stored."
            )
            raise _QuietExit(VALIDATION_FAILURE)
    if file is not None and url and detect_ats(url) == AtsKind.BUK:
        _add_buk_list(session, config, file.read_text(encoding="utf-8"), url)
        return
    if file is not None:
        text = file.read_text(encoding="utf-8")
    elif stdin:
        if sys.stdin.isatty():
            err_console.print(
                "Waiting for a job description on stdin. Paste the text, then press Ctrl-D."
            )
        text = typer.get_text_stream("stdin").read()
    elif url and detect_ats(url) == AtsKind.WORKDAY:
        _add_workday_url(session, config, url)
        return
    elif url:
        from jobbot.jobs.pdf_posting import NotAPdf

        try:
            _add_pdf_url(session, config, url)
        except NotAPdf:
            err_console.print(
                "Provide --file or --stdin (a Workday --url downloads by itself; "
                "a PDF URL reads its text layer)"
            )
            raise typer.Exit(GENERIC_FAILURE) from None
        return
    else:
        err_console.print(
            "Provide --file or --stdin (a Workday --url downloads by itself; "
            "prefer: jobbot jobs search)"
        )
        raise typer.Exit(GENERIC_FAILURE)

    from jobbot.jobs.closure import closure_evidence, fetch_posting_text

    filled = closure_evidence(text)
    if filled is None and url:
        try:
            filled = closure_evidence(fetch_posting_text(url))
        except OSError:
            filled = None
    if filled:
        err_console.print(f"[red]Vacancy is filled[/red] ({filled}). Not stored.")
        raise _QuietExit(VALIDATION_FAILURE)

    repo = JobRepository(session)
    job = repo.add_from_text(text, url=url)
    path = write_job_json(job, config.output_dir)
    console.print(f"[green]Added[/green] {job.id}  {job.company}  {job.title}")
    console.print(f"Wrote {path}")
    _learn_company_knowledge(config, job)


def _add_pdf_url(session: Session, config: JobbotConfig, url: str) -> None:
    """Store one bases PDF. A missing text layer or a closed contest is not stored."""
    from jobbot.jobs.pdf_posting import PdfAddError, PdfFetchError, job_from_public

    try:
        draft = job_from_public(url)
    except PdfAddError as exc:
        err_console.print(f"[red]{exc}[/red]")
        code = GENERIC_FAILURE if isinstance(exc, PdfFetchError) else VALIDATION_FAILURE
        raise _QuietExit(code) from exc
    stored = JobRepository(session).upsert_external(draft.job)
    path = write_job_json(stored, config.output_dir)
    console.print(f"[green]Added[/green] {stored.id}  {stored.company}  {stored.title}")
    if draft.unverified:
        console.print("vigencia no verificable (#207)", markup=False)
    else:
        console.print(f"Closes: {_closing_line(stored)}", markup=False)
    console.print(f"Wrote {path}")


def _add_workday_url(session: Session, config: JobbotConfig, url: str) -> None:
    """`jobs add --url` for Workday: live CXS detail, no pasted text (#215)."""
    from jobbot.jobs.from_url import (
        ClosedPostingError,
        InvalidPostingUrlError,
        PortalShapeChangedError,
        UnsupportedPortalFetchError,
        fetch_workday_posting,
    )

    try:
        job = fetch_workday_posting(url)
    except ClosedPostingError as exc:
        err_console.print(f"[red]Vacancy looks closed[/red] ({exc.evidence}). Not stored.")
        raise _QuietExit(VALIDATION_FAILURE) from exc
    except InvalidPostingUrlError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(VALIDATION_FAILURE) from exc
    except UnsupportedPortalFetchError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise _RecordedExit(
            UI_CHANGED if isinstance(exc, PortalShapeChangedError) else GENERIC_FAILURE,
            error_class=type(exc).__name__,
            message=str(exc),
        ) from exc
    stored = JobRepository(session).upsert_external(job)
    path = write_job_json(stored, config.output_dir)
    console.print(f"[green]Added[/green] {stored.id}  {stored.company}  {stored.title}")
    console.print(f"Closes: {_closing_line(stored)}", markup=False)
    console.print(f"Wrote {path}")
    _learn_company_knowledge(config, stored)


def _discover_pdf_index(page_url: str | None, *, match: str) -> None:
    """List same-host PDF links. This source never writes."""
    from jobbot.jobs.pdf_index import fetch_page, matching_pdfs
    from jobbot.jobs.pdf_posting import PdfAddError

    if not page_url or not page_url.strip():
        err_console.print("[red]pdf-index needs --url[/red]")
        raise typer.Exit(VALIDATION_FAILURE)
    if not match.strip():
        err_console.print("[red]--match needs a value[/red]")
        raise typer.Exit(VALIDATION_FAILURE)
    try:
        html = fetch_page(page_url)
    except PdfAddError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise _QuietExit(GENERIC_FAILURE) from exc
    links = matching_pdfs(html, page_url, match=match)
    for link in links:
        console.print(link, markup=False, highlight=False)
    console.print(f"{len(links)} pdf", markup=False)
    console.print("Nothing written.", markup=False)


def _closing_line(job: JobPosting, *, evidence: bool = True) -> str:
    from jobbot.jobs.closing import describe_closing

    local = datetime.now().astimezone().tzinfo
    line = describe_closing(job.closes_at, job.closes_on, local_tz=local)
    return f"{line}  [{job.closes_text}]" if evidence and job.closes_text else line


def _closing_now() -> datetime:
    from jobbot.jobs import closing

    return closing.utc_now()


def _evidenced_portals(registry: CompanyRegistry) -> list[tuple[str, str]]:
    """Career-site hosts whose ATS was observed, not guessed from a hostname."""
    from jobbot.portals.detect import AtsKind

    sites: list[tuple[str, str]] = []
    for company in registry.companies:
        for site in company.career_sites:
            if site.ats == AtsKind.UNKNOWN:
                continue
            evidenced = any(obs.ats == site.ats for obs in site.observations)
            if evidenced or site.status.value == "active":
                sites.append((site.domain, site.ats.value))
    return sites


def _events_by_job(
    repo: ApplicationRepository,
) -> dict[str, list[tuple[str, str | None, datetime]]]:
    grouped: dict[str, list[tuple[str, str | None, datetime]]] = {}
    for app in repo.list_all():
        grouped[app.job_id] = [
            (event.event_type, event.detail, event.created_at) for event in repo.events_for(app.id)
        ]
    return grouped


def _opacity_line(session: Session, config: JobbotConfig, job: JobPosting) -> str:
    """One line for show/match. Local rows only."""
    from jobbot.companies.registry import load_companies
    from jobbot.jobs.opacity import assess
    from jobbot.jobs.repository import JobRepository

    repo = JobRepository(session)
    stored = repo.list_all()
    peers = stored if any(item.id == job.id for item in stored) else [*stored, job]
    signal = assess(
        job,
        peers=peers,
        sites=_evidenced_portals(load_companies(config.companies_path)),
        events=_events_by_job(ApplicationRepository(session)).get(job.id, []),
        now=_closing_now(),
        max_age_days=config.search.max_age_days,
    )
    return (
        f"Opacity: {signal.band} ({signal.score:.2f})  "
        f"freshness={signal.freshness}  closure={signal.closure}  "
        f"repost={'yes' if signal.repost else 'no'}  "
        f"portal={'known' if signal.portal_known else 'unknown'}  "
        f"silence={signal.silence}"
    )


def _closing_flag(job: JobPosting, now: datetime, *, soon_days: int) -> str:
    from jobbot.jobs.closing import ClosingState, closing_state
    from jobbot.jobs.closure import closure_evidence

    stated = closure_evidence(job.raw_description or "") or closure_evidence(job.description or "")
    state = closing_state(job.closes_at, job.closes_on, now=now, soon_days=soon_days)
    if stated or state is ClosingState.EXPIRED:
        return "vencido"
    if state is ClosingState.SOON:
        return "cierra pronto"
    return ""


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
    cdp_timeout: Annotated[
        float,
        typer.Option("--cdp-timeout", help="Seconds to wait for a CDP attach (default 15)"),
    ] = 15,
) -> None:
    """Search Indeed and store job postings locally (small volumes)."""
    from jobbot.adapters.indeed.jobs import IndeedChallengePending, IndeedJobSource
    from jobbot.browser.cdp import resolve_cdp_url
    from jobbot.jobs.sources import JobSearchQuery

    if limit < 1 or limit > 50:
        err_console.print("--limit must be between 1 and 50")
        raise typer.Exit(GENERIC_FAILURE)

    session, config = _session()
    cdp_url = resolve_cdp_url(cdp)
    source = IndeedJobSource(config, cdp_url=cdp_url, cdp_attach_s=cdp_timeout)
    q = JobSearchQuery(query=query, location=location, remote=remote, limit=limit)

    if cdp_url:
        console.print(f"Using CDP Chrome at [bold]{cdp_url}[/bold]")
    console.print(f"Searching Indeed ({source.base}) for [bold]{query}[/bold]…")
    try:
        found = source.search_jobs(q) if enrich else source.search_cards(q)
    except IndeedChallengePending as exc:
        err_console.print(
            f"[red]Indeed challenge on {exc.context} was not cleared. Not an empty search.[/red]"
        )
        raise _QuietExit(MANUAL_CHALLENGE) from exc
    except Exception as exc:
        from jobbot.browser.cdp import CdpAttachInterrupted, CdpAttachTimeout

        if isinstance(exc, (CdpAttachTimeout, CdpAttachInterrupted)):
            err_console.print(f"[red]{exc}[/red]")
            raise _RecordedExit(GENERIC_FAILURE, error_class="CdpAttach", message=str(exc)) from exc
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


@jobs_app.command("describe")
def jobs_describe(
    job_id: Annotated[str, typer.Argument(help="Stored job id")],
    file: Annotated[
        Path | None,
        typer.Option("--file", help="Plain text that replaces the stored description"),
    ] = None,
) -> None:
    """Replace one stored posting's description. The id, URL, note and application stay."""
    if file is None:
        err_console.print("[red]Pass --file with the posting text.[/red]")
        raise typer.Exit(VALIDATION_FAILURE)
    text = file.expanduser().read_text(encoding="utf-8").strip()
    if not text:
        err_console.print("[red]--file is empty.[/red]")
        raise typer.Exit(VALIDATION_FAILURE)
    session, config = _session()
    try:
        job = JobRepository(session).replace_description(job_id, text)
    except KeyError:
        err_console.print(f"[red]Job not found: {job_id}[/red]")
        raise typer.Exit(GENERIC_FAILURE) from None
    write_job_json(job, config.output_dir)
    console.print(f"Updated {job.id} description ({len(text)} characters).")


def _iso_territory(code: str) -> bool:
    from babel import Locale

    return Locale("en").territories.get(code.upper()) is not None


@jobs_app.command("discover")
def jobs_discover(
    source: Annotated[
        str,
        typer.Option(
            "--source",
            help=(
                "Public source to read: workday, un-careers, buk, pdf-index, "
                "lumesse, cornerstone, avature, unops, impactpool, "
                "pageup, unicef, pjud, smartrecruiters, greenhouse, "
                "oracle_orc, bne, chiletrabajos, vacantes, laborum"
            ),
        ),
    ],
    site: Annotated[
        list[str] | None,
        typer.Option(
            "--site",
            help="Career site URL (repeatable), e.g. https://acme.wd3.myworkdayjobs.com/en-US/"
            "External. Default: that ATS's sites in the company registry "
            "(un-careers: its one public feed)",
        ),
    ] = None,
    query: Annotated[
        str | None,
        typer.Option("--query", "-q", help="Search text (default: your profile's searches)"),
    ] = None,
    company: Annotated[
        str | None,
        typer.Option("--company", help="SmartRecruiters company identifier"),
    ] = None,
    country: Annotated[
        str | None,
        typer.Option("--country", help="ISO 3166 country (SmartRecruiters or Vacantes)"),
    ] = None,
    all_sitemap: Annotated[
        bool,
        typer.Option(
            "--all-sitemap",
            help="Vacantes: vacancy sitemap instead of the country landing",
        ),
    ] = False,
    board_token: Annotated[
        str | None,
        typer.Option("--board", help="Greenhouse board token"),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", help="Max postings per site and query (1-200)"),
    ] = 50,
    max_queries: Annotated[
        int,
        typer.Option("--max-queries", help="Profile searches to run when no --query is given"),
    ] = _DEFAULT_MAX_QUERIES,
    location: Annotated[
        str | None,
        typer.Option(
            "--location",
            help="Keep postings whose place contains this text (local; 'remote' also keeps "
            "home-based)",
        ),
    ] = None,
    level: Annotated[
        list[str] | None,
        typer.Option(
            "--level",
            help="Keep these grades only (repeatable or comma-separated), e.g. CON,P-3,NO-B",
        ),
    ] = None,
    details: Annotated[
        bool | None,
        typer.Option(
            "--details/--no-details",
            help="Read each posting for closing date and description (1 request/s per host). "
            "Default: on for workday, off for un-careers (each read adds a view to the posting)",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview: writes nothing (no DB, job JSON, companies.yaml)"),
    ] = False,
    page_url: Annotated[
        str | None,
        typer.Option("--url", help="Page whose PDF links pdf-index lists"),
    ] = None,
    name_match: Annotated[
        str,
        typer.Option("--match", help="pdf-index keeps PDF filenames containing this text"),
    ] = "concurso",
) -> None:
    """Discover postings through a public source; --dry-run previews without writing."""
    from jobbot.companies.registry import load_companies
    from jobbot.jobs.discover import (
        JobFilters,
        SiteOutcome,
        SiteStatus,
        SiteTarget,
        decide,
        discover_adapter,
        exit_code_for,
        feed_summary,
    )
    from jobbot.jobs.repository import StoredJobIndex

    ceiling = 300 if source == "smartrecruiters" else 200
    if limit < 1 or limit > ceiling:
        err_console.print(f"[red]--limit must be between 1 and {ceiling}[/red]")
        raise typer.Exit(VALIDATION_FAILURE)
    if source == "pdf-index":
        _discover_pdf_index(page_url, match=name_match)
        return
    levels = tuple(part.strip() for raw in level or [] for part in raw.split(","))
    if any(not part for part in levels) or (location is not None and not location.strip()):
        err_console.print("[red]--level and --location need a value[/red]")
        raise typer.Exit(VALIDATION_FAILURE)
    filters = JobFilters(location=location, levels=levels)
    try:
        adapter = discover_adapter(source)
    except ValueError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(VALIDATION_FAILURE) from exc

    config = load_config()
    if source == "smartrecruiters":
        from jobbot.adapters.smartrecruiters.discover import SmartRecruitersDiscover
        from jobbot.jobs.geo import normalize_country

        if not isinstance(adapter, SmartRecruitersDiscover):
            raise typer.Exit(VALIDATION_FAILURE)
        if company is not None and not company.strip():
            err_console.print("[red]--company needs an identifier[/red]")
            raise typer.Exit(VALIDATION_FAILURE)
        if country is None:
            adapter.countries = config.search.countries
        else:
            country_code = normalize_country(country)
            if country_code is None or not _iso_territory(country_code):
                err_console.print(f"[red]{country} is not an ISO 3166 country[/red]")
                raise typer.Exit(VALIDATION_FAILURE)
            adapter.countries = (country_code,)
    known = adapter.registry_targets(load_companies(config.companies_path))
    targets: list[SiteTarget] = []
    if source == "smartrecruiters" and company and company.strip():
        try:
            targets = [adapter.site_target(company.strip())]
        except ValueError as exc:
            err_console.print(f"[red]{exc}[/red]")
            raise typer.Exit(VALIDATION_FAILURE) from exc
    if source == "greenhouse" and board_token is not None:
        if not board_token.strip():
            err_console.print("[red]--board needs a token[/red]")
            raise typer.Exit(VALIDATION_FAILURE)
        try:
            targets = [adapter.site_target(board_token.strip())]
        except ValueError as exc:
            err_console.print(f"[red]{exc}[/red]")
            raise typer.Exit(VALIDATION_FAILURE) from exc
    for raw in site or []:
        try:
            target = adapter.site_target(raw)
        except ValueError as exc:
            err_console.print(f"[red]{exc}[/red]")
            raise typer.Exit(VALIDATION_FAILURE) from exc
        named = next((k for k in known if k.url == target.url), None)
        targets.append(named or target)
    if not site and not targets:
        targets = known
    if not targets:
        err_console.print(
            f"[red]No {source} career sites to read.[/red] Pass --site URL, or register one: "
            "jobbot companies learn URL && jobbot companies promote NAME"
        )
        raise typer.Exit(VALIDATION_FAILURE)

    if source == "greenhouse":
        from jobbot.adapters.greenhouse.discover import GreenhouseDiscover

        if isinstance(adapter, GreenhouseDiscover) and not dry_run:
            adapter.known_ids = StoredJobIndex.read_only(config.database_path).ids_for("greenhouse")
    if source == "oracle_orc":
        from jobbot.adapters.oracle_orc.discover import OracleOrcDiscover

        if isinstance(adapter, OracleOrcDiscover) and not dry_run:
            adapter.known_ids = StoredJobIndex.read_only(config.database_path).ids_for("oracle_orc")
    if source == "vacantes":
        from jobbot.adapters.vacantes.discover import LANDINGS, VacantesDiscover

        if isinstance(adapter, VacantesDiscover):
            chosen = country or (config.search.countries[0] if config.search.countries else "CL")
            chosen = chosen.upper()
            if chosen not in LANDINGS:
                listed = ", ".join(sorted(LANDINGS))
                err_console.print(
                    f"[red]{chosen} has no Vacantes landing.[/red] Available: {listed}"
                )
                raise typer.Exit(VALIDATION_FAILURE)
            adapter.country = chosen
            adapter.all_sitemap = all_sitemap
            if not dry_run:
                adapter.known_ids = StoredJobIndex.read_only(config.database_path).ids_for(
                    "vacantes"
                )
    if source in {"pjud", "greenhouse"} and query is None:
        queries = [""]
    else:
        queries = _search_queries(config, query, max_queries)
    read_details = adapter.default_details if details is None else details
    narrator = _narrator()
    outcomes: list[SiteOutcome] = []
    for target in targets:
        for text in queries:
            narrator.phase(Phase.RECEIVING_WORLD, f"{source}: {target.url} «{text}»")
            outcome = adapter.discover_site(
                target, query=text, limit=limit, details=read_details, filters=filters
            )
            outcomes.append(outcome)
            line = f"{outcome.site} «{text}»: {outcome.status.value}"
            if outcome.detail:
                line += f" ({outcome.detail})"
            style = "green" if outcome.answered else "yellow"
            console.print(line, style=style, markup=False, highlight=False, soft_wrap=True)
    fed = feed_summary(outcomes)
    if fed is not None:
        console.print(
            f"{source}: {fed[0]} ítems en el feed, {fed[1]} tras el filtro"
            + (" (dry-run)" if dry_run else ""),
            markup=False,
            highlight=False,
        )

    found = [job for outcome in outcomes for job in outcome.jobs]
    now = _closing_now()
    session: Session | None = None
    if dry_run:
        index = StoredJobIndex.read_only(config.database_path)
    else:
        session, _ = _session()
        index = StoredJobIndex.from_repository(JobRepository(session))
    decisions = decide(found, index, now=now)

    stored_ids: dict[int, str] = {}
    if not dry_run and session is not None:
        try:
            candidate: Candidate | None = load_profile(config.profile_path)
        except ProfileLoadError:
            candidate = None
        repo = JobRepository(session)
        analyzer = RuleBasedJobAnalyzer()
        for position, decision in enumerate(decisions):
            if not decision.stores:
                continue
            job = repo.upsert_external(decision.job)
            if candidate is not None:
                match = analyzer.analyze(candidate, job)
                repo.update_match_score(job.id, match.score)
                job.match_score = match.score
            write_job_json(job, config.output_dir)
            _learn_company_knowledge(config, job, narrator=narrator)
            stored_ids[position] = job.id

    table = Table(title=f"{source}: {len(decisions)} avisos" + (" (dry-run)" if dry_run else ""))
    if stored_ids:
        table.add_column("ID")
    table.add_column("Título")
    table.add_column("Organización")
    table.add_column("Ubicación")
    table.add_column("Nivel")
    table.add_column("Cierre")
    table.add_column("Decisión")
    for position, decision in enumerate(decisions):
        job = decision.job
        cells = [
            job.title[:60],
            job.company[:60],
            _place_cell(job),
            job.seniority or "—",
            _closing_cell(job),
            decision.label,
        ]
        if stored_ids:
            cells.insert(0, stored_ids.get(position, "—"))
        table.add_row(*cells)
    if decisions:
        console.print(table)

    counts: dict[str, int] = {}
    for decision in decisions:
        key = decision.action.value + (f" ({decision.reason})" if decision.reason else "")
        counts[key] = counts.get(key, 0) + 1
    summary = ", ".join(f"{n} {label}" for label, n in counts.items()) or "0 avisos"
    if dry_run:
        console.print(f"Dry-run: {summary}. Nothing written.")
    else:
        console.print(f"Stored {len(stored_ids)} of {len(decisions)}: {summary}.")
        if stored_ids:
            first = next(iter(stored_ids.values()))
            console.print(f"Next: [bold]jobbot jobs show {first}[/bold] or jobbot jobs shortlist")

    code = exit_code_for(outcomes)
    if any(outcome.detail.startswith("captcha:") for outcome in outcomes):
        code = MANUAL_CHALLENGE
    elif source in {"lumesse", "cornerstone", "impactpool", "laborum"} and code != SUCCESS:
        code = VALIDATION_FAILURE
    if code == UI_CHANGED and not dry_run:
        changed = next(o for o in outcomes if o.status is SiteStatus.CHANGED)
        raise _RecordedExit(
            UI_CHANGED, error_class=f"ShapeChanged[{source}]", message=changed.detail
        )
    if code != SUCCESS:
        err_console.print("[red]No site answered.[/red]")
        raise _QuietExit(code)


def _place_cell(job: JobPosting) -> str:
    place = (job.location or "—")[:28]
    if (job.remote_type or "").casefold() == "remote" and "remot" not in place.casefold():
        place += " · remoto"
    return place


def _closing_cell(job: JobPosting) -> str:
    if job.closes_at is not None:
        from jobbot.jobs.closing import describe_closing

        return describe_closing(job.closes_at, None)
    if job.closes_on is not None:
        return f"{job.closes_on.isoformat()} (sin hora)"
    return "—"


@jobs_app.command("queries")
def jobs_queries(
    region: Annotated[
        list[str] | None,
        typer.Option(
            "--region",
            help="Geo token for the query (repeatable), e.g. Spain, Europe, EMEA, Chile",
        ),
    ] = None,
    remote: Annotated[
        bool,
        typer.Option("--remote/--no-remote", help='Include "remote" in the query'),
    ] = True,
    ats: Annotated[
        list[str] | None,
        typer.Option(
            "--ats",
            help="ATS kinds to target (repeatable): ashby, greenhouse, lever",
        ),
    ] = None,
    keyword: Annotated[
        list[str] | None,
        typer.Option("--keyword", "-k", help="Extra quoted keyword (repeatable)"),
    ] = None,
) -> None:
    """Print web-search queries for ATS hosts (Ashby/Greenhouse/Lever). Does not search."""
    from jobbot.jobs.ats_queries import build_ats_search_queries, format_queries_help
    from jobbot.portals.detect import AtsKind

    kinds: tuple[AtsKind, ...] | None = None
    if ats:
        parsed: list[AtsKind] = []
        for raw in ats:
            try:
                parsed.append(AtsKind(raw.casefold().strip()))
            except ValueError:
                err_console.print(f"[red]Unknown --ats {raw!r}[/red]; use ashby, greenhouse, lever")
                raise typer.Exit(VALIDATION_FAILURE) from None
        kinds = tuple(parsed)

    queries = build_ats_search_queries(
        kinds=kinds,
        regions=tuple(region or ()),
        remote=remote,
        keywords=tuple(keyword or ()),
    )
    if not queries:
        err_console.print("[red]No queries for the selected ATS kinds[/red]")
        raise typer.Exit(VALIDATION_FAILURE)

    console.print(format_queries_help(queries))
    raise typer.Exit(SUCCESS)


@jobs_app.command("show")
def jobs_show(
    job_id: Annotated[str, typer.Argument()],
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Show a stored job posting."""
    session, config = _session()
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
    if job.open_status:
        from jobbot.jobs.check_open import verification_label

        console.print(f"Online: {verification_label(job)}", markup=False)
    if job.closes_on or job.closes_at:
        flag = _closing_flag(job, _closing_now(), soon_days=3)
        console.print(
            f"Closes: {_closing_line(job)}" + (f"  ⚠ {flag}" if flag else ""), markup=False
        )
    if job.ats_signals.get("resume_parsing") is False:
        console.print("ATS: the CV upload does not prefill the profile; fill it field by field.")
    if job.ats_signals.get("questionnaire"):
        console.print("ATS: the application has a questionnaire.")
    console.print(f"Skills: {', '.join(job.skills) or '—'}")
    if job.requirements:
        console.print("Requirements:")
        for req in job.requirements:
            console.print(f"  - {req}")
    console.print(_opacity_line(session, config, job), markup=False)
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
    console.print(_opacity_line(session, config, job), markup=False)


@jobs_app.command("conditions")
def jobs_conditions(
    job_ids: Annotated[list[str] | None, typer.Argument(help="Job IDs (J0001 …)")] = None,
    all_prepared: Annotated[
        bool, typer.Option("--all-prepared", help="Every job with a prepared application")
    ] = False,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Review a posting's special conditions against you before applying (exit 1: dealbreaker)."""
    from jobbot.jobs.conditions import posting_conditions
    from jobbot.jobs.eligibility import (
        assess_conditions,
        default_answers_path,
        format_conditions_report,
        has_dealbreaker,
        job_answers_path,
        load_application_answers,
    )

    session, config = _session()
    try:
        candidate = load_profile(config.profile_path)
    except ProfileLoadError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(VALIDATION_FAILURE) from exc
    ids = list(job_ids or [])
    if all_prepared:
        for application in ApplicationRepository(session).list_all():
            if application.status == ApplicationStatus.PREPARED and application.job_id not in ids:
                ids.append(application.job_id)
    if not ids:
        err_console.print("Give one or more job IDs, or --all-prepared.")
        raise typer.Exit(VALIDATION_FAILURE)

    repo = JobRepository(session)
    answers_path = default_answers_path(config.root)
    reports: list[dict[str, object]] = []
    texts: list[str] = []
    blocked = False
    for job_id in ids:
        job = repo.get(job_id)
        if job is None:
            err_console.print(f"[red]Job not found: {job_id}[/red]")
            raise typer.Exit(GENERIC_FAILURE)
        try:
            answers = load_application_answers(
                answers_path, job_answers=job_answers_path(config.output_dir, job.id)
            )
        except ValueError as exc:
            err_console.print(f"[red]{exc}[/red]")
            raise typer.Exit(VALIDATION_FAILURE) from exc
        verdicts = assess_conditions(posting_conditions(job), candidate, answers)
        blocked = blocked or has_dealbreaker(verdicts)
        reports.append(
            {
                "job_id": job.id,
                "title": job.title,
                "company": job.company,
                "dealbreaker": has_dealbreaker(verdicts),
                "verdicts": [v.to_dict() for v in verdicts],
            }
        )
        texts.append(format_conditions_report(job, verdicts))

    if as_json:
        console.print_json(data=reports)
    else:
        state = "found" if answers_path.is_file() else "missing; copy the .example.yaml"
        texts.append(f"Answers: {answers_path} ({state})")
        console.print("\n\n".join(texts), markup=False, highlight=False, soft_wrap=True)
    if blocked:
        raise _QuietExit(GENERIC_FAILURE)


_OPEN_STATUS_LABELS = {"open": "abierto", "closed": "cerrado", "unknown": "desconocido"}


@jobs_app.command("check-open")
def jobs_check_open(
    job_ids: Annotated[list[str] | None, typer.Argument(help="Job IDs (J0001 …)")] = None,
    check_all: Annotated[
        bool,
        typer.Option("--all", help="Every stored job, except closed ones checked < 24 h ago"),
    ] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Check and print; writes nothing to the database")
    ] = False,
    as_json: Annotated[
        bool, typer.Option("--json", help="Machine-readable output with full URLs")
    ] = False,
) -> None:
    """Re-check online whether stored postings are still open (read-only; unknown if unsure)."""
    from sqlalchemy.exc import SQLAlchemyError

    from jobbot.db.engine import make_readonly_engine
    from jobbot.jobs.check_open import OpenCheck, OpenChecker, OpenStatus, due_for_check

    ids = list(dict.fromkeys(job_ids or []))
    if not ids and not check_all:
        err_console.print("Give one or more job IDs, or --all.")
        raise typer.Exit(VALIDATION_FAILURE)

    config = load_config()
    if dry_run:
        if not config.database_path.is_file():
            console.print("No stored jobs. Nothing to check.")
            return
        session = make_session_factory(make_readonly_engine(config.database_path))()
    else:
        session, _ = _session()
    repo = JobRepository(session)
    now = _closing_now()
    try:
        if check_all:
            stored = repo.list_all()
            jobs = [job for job in stored if job.id in ids or due_for_check(job, now=now)]
            skipped = len(stored) - len(jobs)
        else:
            jobs, skipped = [], 0
            for job_id in ids:
                found = repo.get(job_id)
                if found is None:
                    err_console.print(f"[red]Job not found: {job_id}[/red]")
                    raise typer.Exit(VALIDATION_FAILURE)
                jobs.append(found)
    except SQLAlchemyError as exc:
        err_console.print(f"[red]Cannot read the job database:[/red] {exc}")
        raise typer.Exit(GENERIC_FAILURE) from exc

    checker = OpenChecker(now=_closing_now)
    results: list[OpenCheck] = []
    for job in jobs:
        if not as_json:
            console.print(f"{job.id}: checking…", markup=False, highlight=False)
        results.append(checker.check(job))

    if not dry_run:
        try:
            for result in results:
                repo.record_open_check(
                    result.job_id,
                    status=result.status.value,
                    evidence=result.evidence,
                    checked_at=result.checked_at,
                    closes=result.closes,
                )
        except SQLAlchemyError as exc:
            err_console.print(f"[red]Cannot write the job database:[/red] {exc}")
            raise typer.Exit(GENERIC_FAILURE) from exc

    if as_json:
        titles = {job.id: job.title for job in jobs}
        payload = [{**r.to_dict(), "title": titles.get(r.job_id)} for r in results]
        console.print_json(data={"dry_run": dry_run, "skipped": skipped, "jobs": payload})
        return

    table = Table(title="Vigencia en línea" + (" (dry-run)" if dry_run else ""))
    table.add_column("ID")
    table.add_column("Estado")
    table.add_column("Motivo", overflow="fold")
    table.add_column("Aviso")
    styles = {OpenStatus.OPEN: "green", OpenStatus.CLOSED: "red", OpenStatus.UNKNOWN: "yellow"}
    titles = {job.id: job.title for job in jobs}
    for result in results:
        table.add_row(
            result.job_id,
            f"[{styles[result.status]}]{_OPEN_STATUS_LABELS[result.status.value]}[/]",
            result.evidence,
            titles.get(result.job_id, "")[:50],
        )
    if results:
        console.print(table)
    counts = {status: sum(r.status is status for r in results) for status in OpenStatus}
    summary = ", ".join(f"{counts[s]} {_OPEN_STATUS_LABELS[s.value]}" for s in OpenStatus)
    stamp = now.strftime("%Y-%m-%d %H:%M UTC")
    console.print(f"{len(results)} avisos: {summary}. Verificado {stamp}.", markup=False)
    if skipped:
        console.print(f"{skipped} omitidos: cerrados y verificados hace menos de 24 h.")
    console.print("Dry-run: nothing written." if dry_run else "Next: jobbot jobs shortlist")


@jobs_app.command("shortlist")
def jobs_shortlist(
    include_closed: Annotated[
        bool,
        typer.Option("--include-closed", help="Also list postings check-open found closed"),
    ] = False,
    soon_days: Annotated[
        int,
        typer.Option(
            "--soon-days",
            help="Flag a published closing within this many days (default 3)",
        ),
    ] = 3,
) -> None:
    """Rank stored jobs by match score; flag a close and a finished posting."""
    if soon_days < 1:
        err_console.print("[red]--soon-days must be at least 1[/red]")
        raise typer.Exit(VALIDATION_FAILURE)
    from jobbot.jobs.admissibility import shortlist_mark
    from jobbot.jobs.check_open import is_verified_closed, verification_label

    session, config = _session()
    try:
        candidate = load_profile(config.profile_path)
    except ProfileLoadError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(VALIDATION_FAILURE) from exc

    from jobbot.companies.registry import load_companies
    from jobbot.jobs.opacity import Opacity, assess, shortlist_key
    from jobbot.matching.scoring import match_reasons

    repo = JobRepository(session)
    analyzer = RuleBasedJobAnalyzer()
    now = _closing_now()
    stored = repo.list_all()
    sites = _evidenced_portals(load_companies(config.companies_path))
    events = _events_by_job(ApplicationRepository(session))
    signals = {
        job.id: assess(
            job,
            peers=stored,
            sites=sites,
            events=events.get(job.id, []),
            now=now,
            max_age_days=config.search.max_age_days,
        )
        for job in stored
    }
    rows: list[tuple[tuple[int, int, float], float, str, str, str, str, list[str], Opacity]] = []
    hidden = 0
    for job in stored:
        if is_verified_closed(job) and not include_closed:
            hidden += 1
            continue
        match = analyzer.analyze(candidate, job)
        repo.update_match_score(job.id, match.score)
        label = _closing_flag(job, now, soon_days=soon_days)
        flag = ""
        if label and (job.closes_at or job.closes_on):
            flag = f"  [{label}: {_closing_line(job, evidence=False)}]"
        elif label:
            flag = f"  [{label}]"
        if is_verified_closed(job):
            flag += f"  [{verification_label(job)}]"
        opacity = signals[job.id]
        rows.append(
            (
                shortlist_key(
                    closed=opacity.closure == "closed",
                    band=opacity.band,
                    fit=match.score,
                ),
                match.score,
                job.id,
                job.title,
                job.company,
                flag,
                match_reasons(match),
                opacity,
            )
        )
    rows.sort(key=lambda r: r[0])
    console.print("[bold]TOP MATCHES[/bold]")
    for _key, score, jid, title, company, flag, reasons, opacity in rows:
        mark = shortlist_mark(config.output_dir / "jobs" / jid / "admissibility.json")
        line = f"{score:5.1f}%  {jid}  {title}  {company}{flag}{mark}"
        console.print(line, markup=False, highlight=False)
        console.print(f"         opacity {opacity.label()}", markup=False, highlight=False)
        for reason in reasons:
            console.print(f"         {reason}", markup=False, highlight=False, soft_wrap=True)
    if hidden:
        console.print(
            f"{hidden} hidden: verified closed by jobs check-open (--include-closed to list them)."
        )
    _warn_if_matcher_blind([row[1] for row in rows])


@jobs_app.command("admissibility")
def jobs_admissibility(
    job_ids: Annotated[list[str] | None, typer.Argument(help="Stored job ids")] = None,
    source: Annotated[
        str | None,
        typer.Option("--source", help="Only stored postings from this source"),
    ] = None,
    open_only: Annotated[
        bool,
        typer.Option("--open", help="Skip postings already marked closed"),
    ] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Print the verdicts as JSON")] = False,
) -> None:
    """Admissibility of a stored posting against the profile (offline). Sends nothing."""
    import json

    from jobbot.jobs.admissibility import assess, contest_code, extract_rules
    from jobbot.jobs.open_signals import OpenStatus

    session, config = _session()
    try:
        candidate = load_profile(config.profile_path)
    except ProfileLoadError as exc:
        err_console.print(str(exc))
        raise typer.Exit(VALIDATION_FAILURE) from exc
    repo = JobRepository(session)
    if job_ids:
        jobs = []
        for job_id in job_ids:
            job = repo.get(job_id)
            if job is None:
                err_console.print(f"aviso desconocido: {job_id}")
                raise typer.Exit(VALIDATION_FAILURE)
            jobs.append(job)
    elif source:
        jobs = [job for job in repo.list_all() if job.source == source]
        if open_only:
            jobs = [job for job in jobs if job.open_status != OpenStatus.CLOSED.value]
        if not jobs:
            err_console.print("fuente sin concursos guardados")
            raise typer.Exit(VALIDATION_FAILURE)
    else:
        err_console.print("indica un id o --source")
        raise typer.Exit(VALIDATION_FAILURE)
    payload = []
    for job in jobs:
        text = job.raw_description or ""
        verdict = assess(
            extract_rules(text),
            candidate,
            contest_code=contest_code(text, job.id),
        )
        path = config.output_dir / "jobs" / job.id / "admissibility.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(verdict.as_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        payload.append({"job_id": job.id, **verdict.as_dict()})
        if not as_json:
            console.print(
                f"{job.id}  {verdict.status}  {verdict.rule}",
                markup=False,
                highlight=False,
            )
            detail = verdict.question or verdict.evidence
            if detail:
                console.print(f"  {detail}", markup=False, highlight=False)
    if as_json:
        console.print(json.dumps(payload, ensure_ascii=False, indent=2), markup=False)


@jobs_app.command("digest")
def jobs_digest(
    since: Annotated[
        str | None,
        typer.Option("--since", help="Include postings after this date (YYYY-MM-DD)"),
    ] = None,
    fmt: Annotated[
        str,
        typer.Option("--format", help="whatsapp or md"),
    ] = "whatsapp",
    limit: Annotated[int, typer.Option("--limit", min=1)] = 10,
    include_doubtful: Annotated[
        bool,
        typer.Option("--include-doubtful", help="Also list postings marked dudoso"),
    ] = False,
    out: Annotated[
        str | None,
        typer.Option("--out", help="Write the text under output/"),
    ] = None,
) -> None:
    """Shareable summary of new open postings (WhatsApp or Markdown). Sends nothing."""
    from jobbot.jobs.digest import (
        DigestError,
        load_eligibility,
        output_path,
        parse_since,
        refuse_pii,
        render_markdown,
        render_whatsapp,
        resolve_timezone,
        save_last_digest,
        select_entries,
        why_line,
    )

    if fmt not in {"whatsapp", "md"}:
        err_console.print("[red]--format debe ser whatsapp o md.[/red]")
        raise typer.Exit(VALIDATION_FAILURE)
    from datetime import UTC

    session, config = _session()
    try:
        candidate = load_profile(config.profile_path)
    except ProfileLoadError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(VALIDATION_FAILURE) from exc
    try:
        zone = resolve_timezone(config, candidate.personal.country)
        now = datetime.now(UTC)
        state = config.root / "data" / "digest_state.json"
        start = parse_since(since, now=now, zone=zone, state_path=state)
        marks = load_eligibility(config.root / "data" / "eligibility.yaml")
        destination = output_path(config, out) if out else None
    except DigestError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(VALIDATION_FAILURE) from exc

    repo = JobRepository(session)
    jobs = repo.list_all(include_invalid=True)
    reasons = {job.id: text for job in jobs if (text := why_line(candidate, job))}
    entries = select_entries(
        jobs,
        since=start,
        zone=zone,
        eligibility=marks,
        reasons=reasons,
        include_doubtful=include_doubtful,
        limit=limit,
    )
    messages = (
        render_whatsapp(entries, since=start)
        if fmt == "whatsapp"
        else [render_markdown(entries, since=start)]
    )
    text = "\n\n".join(messages)
    try:
        refuse_pii(text)
    except DigestError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(VALIDATION_FAILURE) from exc
    for message in messages:
        console.print(message, markup=False, highlight=False)
    if destination is not None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8")
        console.print(f"Wrote {destination}", markup=False)
    save_last_digest(state, now)


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


@jobs_app.command("reparse")
def jobs_reparse(
    job_id: Annotated[str, typer.Argument(help="Stored job id, kept as-is")],
) -> None:
    """Re-read a stored posting's text and keep its id (offline)."""
    from jobbot.jobs.backfill import reparse_stored

    session, _ = _session()
    try:
        job = reparse_stored(JobRepository(session), job_id)
    except KeyError as exc:
        err_console.print(f"[red]Unknown job {job_id}[/red]")
        raise typer.Exit(GENERIC_FAILURE) from exc
    console.print(f"[green]Reparsed[/green] {job.id}: {job.title} — {job.company}")


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


@jobs_app.command("audit")
def jobs_audit(
    source: Annotated[
        str,
        typer.Option("--source", help="Job source to audit (only 'indeed' today)"),
    ],
    apply: Annotated[
        bool,
        typer.Option("--apply", help="Mark decoys/duplicates invalid (skip submitted)"),
    ] = False,
) -> None:
    """List (or mark) stored Indeed decoys and title/company duplicates (#211)."""
    from jobbot.jobs.audit import audit_indeed_jobs

    if source.casefold() != "indeed":
        err_console.print(f"[red]Unknown audit source:[/red] {source} (supported: indeed)")
        raise typer.Exit(VALIDATION_FAILURE)

    try:
        session, _ = _session()
        findings = audit_indeed_jobs(
            JobRepository(session),
            ApplicationRepository(session),
            apply=apply,
        )
    except OSError as exc:
        err_console.print(f"[red]Could not open job store:[/red] {exc}")
        raise typer.Exit(GENERIC_FAILURE) from exc

    if not findings:
        console.print("[green]No suspicious Indeed jobs.[/green]")
        return

    console.print("[bold]Indeed audit[/bold]" + (" (--apply)" if apply else " (dry-run)"))
    for finding in findings:
        flag = " [protected: submitted]" if finding.protected else ""
        action = "marked" if apply and not finding.protected else "suspect"
        console.print(f"  {finding.job_id}  {action}  {finding.reason}{flag}")


# ── application(s) ───────────────────────────────────────────────────────────


def _filled_vacancy(job: JobPosting) -> str | None:
    """Phrase that says this posting is gone, from the stored text or the live page."""
    from jobbot.jobs.closure import closure_evidence_for_job, fetch_posting_text

    return closure_evidence_for_job(job, fetch=fetch_posting_text)


def _stop_if_filled(session: Session, job: JobPosting) -> None:
    """Refuse to open or mark applied when the vacancy itself says it is filled."""
    evidence = _filled_vacancy(job)
    if evidence is None:
        return
    from datetime import UTC, datetime

    from jobbot.jobs.open_signals import OpenStatus
    from jobbot.jobs.repository import JobRepository

    JobRepository(session).record_open_check(
        job.id,
        status=OpenStatus.CLOSED.value,
        evidence=evidence,
        checked_at=datetime.now(UTC),
    )
    url = job.ats_url or job.url or job.id
    err_console.print(f"[red]Vacancy is filled[/red] ({evidence}). Not opening {url}.")
    err_console.print("No portal receipt — status stays unknown, not applied.")
    existing = ApplicationRepository(session).get_for_job(job.id)
    if existing is not None:
        ApplicationRepository(session).add_event(existing.id, "closed", f"{evidence} | {url}")
    raise _QuietExit(VALIDATION_FAILURE)


def _note_no_receipt(session: Session, job_id: str, package_dir: str, url: str) -> None:
    """Opening a portal is not a submission. Record the URL and leave status prepared."""
    repo = ApplicationRepository(session)
    app = repo.upsert_for_job(
        job_id,
        status=ApplicationStatus.PREPARED,
        package_dir=package_dir,
    )
    repo.add_event(app.id, "no_receipt", url)
    console.print(
        f"[yellow]No portal receipt[/yellow] for {url}. "
        "Status stays prepared — unknown whether it was submitted."
    )


def _build_job_cv(config: JobbotConfig, candidate: Candidate, job: JobPosting) -> None:
    """Build the CV adapted to this job, unless the one on disk is still current."""
    from jobbot.cv.build import build_adapted_cv

    job_dir = config.output_dir / "jobs" / job.id
    existed = (job_dir / "cv.pdf").is_file() or (job_dir / "cv_ats.txt").is_file()
    match = RuleBasedJobAnalyzer().analyze(candidate, job)
    written = build_adapted_cv(config, candidate, job, match)
    if not written:
        return
    if existed:
        console.print(f"Rebuilt the CV for {job.id} (profile or CV settings changed).")
    else:
        console.print(f"Built CV adapted to {job.id}.")
    if not any(path.suffix == ".pdf" for path in written):
        # PDF may fail without xelatex; ATS text is enough for the package
        err_console.print("[yellow]PDF not built (XeLaTeX unavailable); ATS text written.[/yellow]")


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


@application_app.command("interview")
def application_interview(job_id: Annotated[str, typer.Argument()]) -> None:
    """Preguntas de entrevista desde lo enviado, sin inventar un logro."""
    from jobbot.applications.interview import (
        cards_for,
        format_cards,
        load_sent_selection,
        sent_selection_path,
    )

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
    path = sent_selection_path(config.output_dir, job.id)
    if path is None:
        err_console.print(f"[red]No selection.json for {job.id}[/red]")
        raise typer.Exit(VALIDATION_FAILURE)
    cards = cards_for(job, candidate, load_sent_selection(path))
    console.print(format_cards(cards))


@application_app.command("open")
def application_open(job_id: Annotated[str, typer.Argument()]) -> None:
    """Open the job URL (or ATS URL) in the default browser (does not apply)."""
    session, _ = _session()
    job = JobRepository(session).get(job_id)
    if job is None:
        err_console.print(f"[red]Job not found: {job_id}[/red]")
        raise typer.Exit(GENERIC_FAILURE)
    from jobbot.adapters.ats.apply import open_ats_in_browser, resolve_ats_url

    _stop_if_filled(session, job)
    ats_url, _kind = resolve_ats_url(job)
    target = ats_url or job.url
    if not target:
        err_console.print(f"[red]No URL for job {job_id}[/red]")
        raise typer.Exit(GENERIC_FAILURE)
    console.print(open_ats_in_browser(target))


def _warn_if_login_needed(
    config: JobbotConfig,
    ats_kind: AtsKind,
    cdp: str | None,
    *,
    host: str | None = None,
) -> None:
    from urllib.parse import urlparse

    from jobbot.applications.login_gate import login_warning, session_site
    from jobbot.browser import sessions as browser_sessions
    from jobbot.companies.signup import AccountNeed, account_need

    if account_need(ats_kind) is not AccountNeed.NEEDED:
        return
    site = session_site(ats_kind)
    if cdp and site is not None:
        _warn_from_named_cdp(ats_kind, site, cdp)
        return
    states: list[browser_sessions.SessionState] = []
    if site is not None:
        ports = list(browser_sessions.DEFAULT_PORTS)
        cdp_port = urlparse(cdp).port if cdp else None
        if cdp_port is not None and cdp_port not in ports:
            ports.append(cdp_port)
        states = browser_sessions.inspect_sessions(config.root, sites=[site], ports=ports)
    warning = login_warning(ats_kind, states, host=host)
    if warning:
        console.print(f"[bold yellow]{warning}[/bold yellow]")


def _warn_from_named_cdp(ats_kind: AtsKind, site: str, cdp: str) -> None:
    """Session on the exact ``--cdp`` host. A silent port is not a missing login."""
    from jobbot.applications.login_gate import _MUST_SIGN_IN, _PORTAL_NAMES
    from jobbot.browser.cdp import cdp_endpoint
    from jobbot.browser.sessions import CdpSessionStatus, probe_cdp_session

    report = probe_cdp_session(cdp, site)
    portal = _PORTAL_NAMES.get(ats_kind, ats_kind.value)
    where = cdp_endpoint(report.url)
    console.print(f"{portal}: {report.status.value} ({where})")
    if report.status is CdpSessionStatus.SIGNED_IN:
        return
    if report.status is CdpSessionStatus.UNREACHABLE:
        console.print(
            f"[bold yellow]{portal}: {where} did not answer. "
            "That is not a missing session.[/bold yellow]"
        )
        return
    console.print(f"[bold yellow]No iniciaste sesión en {portal}: {_MUST_SIGN_IN}.[/bold yellow]")


def _ats_target_url(adapter: Any, job: JobPosting, ats_url: str) -> str:
    """The page `adapter.open` would show (Indeed routes to its apply step)."""
    from jobbot.adapters.ats.indeed_apply import IndeedApplyAdapter, apply_target

    if isinstance(adapter, IndeedApplyAdapter):
        return apply_target(job) or ats_url
    return ats_url


def _fill_ats_over_cdp(
    cdp: str,
    url: str,
    candidate: Candidate,
    config: JobbotConfig,
    job_id: str,
    *,
    foreground: bool = False,
    attach_timeout_s: float = 15,
) -> bool:
    """Fill known fields in the requested Chrome. A failure does not open another browser."""
    from jobbot.adapters.ats import apply_fill
    from jobbot.adapters.ats.email_apply import resolve_cv_path

    cv_pdf = resolve_cv_path(config.output_dir, job_id)
    try:
        result = apply_fill.open_and_fill_over_cdp(
            cdp,
            url,
            candidate,
            cv_path=cv_pdf,
            focus=foreground,
            attach_timeout_s=attach_timeout_s,
        )
    except apply_fill.ApplyFillError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise _RecordedExit(GENERIC_FAILURE, error_class="CdpAttach", message=str(exc)) from exc
    if result.opened:
        where = f"Chrome ({cdp})"
        if foreground:
            where = f"primer plano en Chrome ({cdp})"
        console.print(background_notice(result.url, where=where, focus=foreground))
    if result.login_required:
        console.print(
            "[yellow]The page asks you to sign in. JobBot typed nothing: sign in in that "
            "tab yourself, then re-run this command.[/yellow]"
        )
    elif not result.readable:
        console.print(f"[yellow]{result.note}. Fill it by hand with the prefill sheet.[/yellow]")
    for label in result.filled:
        console.print(f"  [green]filled[/green] {label}")
    for label in result.kept:
        console.print(f"  [cyan]kept (already had a value)[/cyan] {label}")
    if result.attached and cv_pdf is not None:
        console.print(f"  [green]attached[/green] {cv_pdf.name}  ({cv_pdf})")
    console.print("Left for you:")
    for label in result.left_for_human:
        console.print(f"  • {label}")
    console.print("Tab left open. Review everything; you submit — JobBot never clicks it.")
    return True


@application_app.command("apply")
def application_apply(
    job_id: Annotated[
        str | None,
        typer.Argument(help="Job id (omit with --all)"),
    ] = None,
    all_jobs: Annotated[
        bool,
        typer.Option(
            "--all",
            help="Assist every eligible stored job, one at a time (HITL between jobs)",
        ),
    ] = False,
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
    cdp_timeout: Annotated[
        float,
        typer.Option("--cdp-timeout", help="Seconds to wait for a CDP attach (default 15)"),
    ] = 15,
    foreground: Annotated[
        bool,
        typer.Option(
            "--foreground",
            help="With --cdp, allow a frontmost tab. Default keeps the OS focus where it is",
        ),
    ] = False,
    limit: Annotated[
        int | None,
        typer.Option("--limit", help="With --all, open at most N jobs"),
    ] = None,
    min_match: Annotated[
        float,
        typer.Option(
            "--min-match",
            help="Warn before --apply below this match. 0.7 means 70%. Default 70.",
        ),
    ] = 70,
) -> None:
    """Plan or open ATS/Gmail apply for a job (HITL; no CAPTCHA bypass; no invented answers).

    ``--all`` queues eligible jobs (URL present, not already applied) and assists
    one by one. Portal Next/Submit stays human; between jobs JobBot asks before
    opening the next.
    """
    if all_jobs and job_id:
        err_console.print("[red]Pass a job id or --all, not both.[/red]")
        raise typer.Exit(VALIDATION_FAILURE)
    from jobbot.applications.preflight import MatchThresholdError, threshold_percent

    try:
        minimum = threshold_percent(min_match)
    except MatchThresholdError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise _QuietExit(VALIDATION_FAILURE) from exc
    if all_jobs:
        _application_apply_all(
            apply_changes=apply_changes,
            yes=yes,
            attach=attach,
            cdp=cdp,
            cdp_timeout=cdp_timeout,
            foreground=foreground,
            limit=limit,
        )
        return
    if not job_id:
        err_console.print("[red]Job id required (or pass --all).[/red]")
        raise typer.Exit(VALIDATION_FAILURE)
    _application_apply_one(
        job_id,
        apply_changes=apply_changes,
        yes=yes,
        attach=attach,
        cdp=cdp,
        cdp_timeout=cdp_timeout,
        foreground=foreground,
        min_match=minimum,
    )


def _confirm_low_match(candidate: Candidate, job: JobPosting, *, minimum: float, yes: bool) -> None:
    """Print the gap list and stop unless the person confirms. --yes still warns."""
    from jobbot.applications.preflight import below_threshold
    from jobbot.cv.gap import GapStatus, gap_report

    if not below_threshold(job.match_score, minimum):
        return
    score = job.match_score or 0
    console.print(f"match {score:.0f}% is below {minimum:.0f}%")
    missing = [
        term.term
        for term in gap_report(candidate, job).terms
        if term.kind == "hard" and term.status is GapStatus.GAP
    ]
    if missing:
        console.print("gaps: " + ", ".join(missing))
    if yes:
        return
    if not typer.confirm("The match is below the threshold. Continue?", default=False):
        console.print("Aborted.")
        raise _QuietExit(USER_CANCEL)


def _application_apply_all(
    *,
    apply_changes: bool,
    yes: bool,
    attach: bool,
    cdp: str | None,
    cdp_timeout: float,
    foreground: bool,
    limit: int | None,
) -> None:
    """Dry-run lists the queue; --apply opens one job at a time with a pause between."""
    from jobbot.applications.batch import select_batch_apply_jobs

    session, config = _session()
    try:
        load_profile(config.profile_path)
    except ProfileLoadError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(VALIDATION_FAILURE) from exc

    items = select_batch_apply_jobs(
        JobRepository(session).list_all(),
        ApplicationRepository(session).list_all(),
        limit=limit,
    )
    if not items:
        console.print("No eligible jobs (need a URL; skip applied/rejected/…).")
        return

    console.print(f"[bold]Batch apply[/bold] — {len(items)} job(s)")
    console.print(
        "[dim]JobBot opens the portal and stops. Next/Submit are yours. "
        "Between jobs it asks before opening the next.[/dim]"
    )
    for item in items:
        console.print(f"  {item.label}")

    if not apply_changes:
        console.print(
            "Dry-run only. Re-run with [bold]--all --apply[/bold] "
            "to open one at a time (you submit each)."
        )
        return

    opened = 0
    for index, item in enumerate(items):
        console.print()
        console.print(f"[bold]({index + 1}/{len(items)})[/bold] {item.label}")
        if not yes and not typer.confirm(
            f"Open assisted apply for {item.job.id}? "
            "(finish Next/Submit yourself before continuing)",
            default=True,
        ):
            console.print("Skipped.")
            if not typer.confirm("Continue with the remaining jobs?", default=True):
                console.print("Stopped.")
                break
            continue
        try:
            _application_apply_one(
                item.job.id,
                apply_changes=True,
                yes=True,
                attach=attach,
                cdp=cdp,
                cdp_timeout=cdp_timeout,
                foreground=foreground,
            )
            opened += 1
        except _QuietExit:
            console.print(f"[yellow]Skipped[/yellow] {item.job.id} (filled or refused).")
        if index + 1 >= len(items):
            break
        if yes:
            console.print(
                "[dim]Next job — finish any open wizard first "
                "(JobBot does not click Next/Submit).[/dim]"
            )
            continue
        if not typer.confirm(
            "Ready for the next job? (only after you finished Next/Submit here)",
            default=False,
        ):
            console.print("Stopped.")
            break
    console.print(
        f"Opened assist for [bold]{opened}[/bold] job(s). "
        "Status stays prepared without a portal receipt."
    )


def _application_apply_one(
    job_id: str,
    *,
    apply_changes: bool,
    yes: bool,
    attach: bool,
    cdp: str | None,
    cdp_timeout: float = 15,
    foreground: bool = False,
    min_match: float = 70,
) -> None:
    """Assist apply for a single job id (same behaviour as before --all)."""
    from jobbot.adapters.ats.apply import (
        build_apply_plan,
        prefill_field_map,
        prefill_sheet_fields,
    )
    from jobbot.adapters.ats.email_apply import build_email_draft, open_gmail_compose
    from jobbot.adapters.ats.registry import adapter_for_job
    from jobbot.adapters.base import ApplyMethod
    from jobbot.applications.manager import FilesystemApplicationPackage

    session, config = _session()
    job = JobRepository(session).get(job_id)
    if job is None:
        err_console.print(f"[red]Job not found: {job_id}[/red]")
        raise typer.Exit(GENERIC_FAILURE)
    _stop_if_filled(session, job)
    try:
        candidate = load_profile(config.profile_path)
    except ProfileLoadError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(VALIDATION_FAILURE) from exc

    if apply_changes:
        _confirm_low_match(candidate, job, minimum=min_match, yes=yes)

    plan = build_apply_plan(candidate, job)
    adapter = adapter_for_job(job)
    adapter_name = adapter.name if adapter is not None else plan.ats_kind.value
    console.print(f"[bold]{job.id}[/bold]  {job.title} @ {job.company}")
    console.print(f"ATS: {plan.ats_kind.value}  adapter={adapter_name}  {plan.ats_url or '(none)'}")
    console.print(f"Method: {plan.method.value}")
    console.print(plan.message)
    if plan.ats_kind.value == "indeed" and plan.ats_url:
        from jobbot.adapters.indeed.external import IndeedVerificationRequired, gate_indeed_entry

        try:
            gate_indeed_entry(plan.ats_url)
        except IndeedVerificationRequired as exc:
            err_console.print(f"[yellow]{exc}[/yellow]")
            raise _QuietExit(MANUAL_CHALLENGE) from exc
    from urllib.parse import urlparse

    _warn_if_login_needed(
        config,
        plan.ats_kind,
        cdp,
        host=urlparse(plan.ats_url).hostname if plan.ats_url else None,
    )

    if plan.method == ApplyMethod.LINKEDIN_MESSAGE:
        from jobbot.adapters.ats.apply import open_ats_in_browser

        if not apply_changes:
            console.print(
                "Dry-run only. Re-run with [bold]--apply[/bold] to open the LinkedIn post "
                "(you write the message; JobBot never sends)."
            )
            return
        if not yes and not typer.confirm(
            "¿Abrir la publicación de LinkedIn para que le escribas vos? "
            "JobBot no envía el mensaje.",
            default=False,
        ):
            console.print("Aborted.")
            raise typer.Exit(SUCCESS)
        job_dir = config.output_dir / "jobs" / job.id
        app_dir = prepare_application_package(
            job, config.output_dir, job_dir=job_dir, candidate=candidate
        )
        console.print(open_ats_in_browser(plan.ats_url))
        console.print(
            "[green]Opened the post.[/green] Write the message yourself. JobBot never sends InMail."
        )
        _note_no_receipt(session, job.id, str(app_dir), plan.ats_url)
        return

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
        from jobbot.browser.sessions import (
            AccountExpectation,
            inspect_sessions,
            refuse_to_open,
            session_for,
        )

        expected = AccountExpectation(
            email=str(candidate.personal.email) if candidate.personal.email else None,
            linkedin=candidate.personal.linkedin,
        )
        gmail = session_for(
            inspect_sessions(config.root, sites=["gmail"], account=expected),
            "gmail",
        )
        if gmail is not None:
            blocked = refuse_to_open(gmail.status, gmail.evidence)
            if blocked:
                err_console.print(f"[red]{blocked}[/red]")
                raise typer.Exit(GENERIC_FAILURE)
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
            console.print(background_notice(f"Gmail compose ({len(url)} chars URL)"))
            console.print(
                f"Adjuntá el CV ({cv_pdf or 'output/base/cv.pdf'}) "
                "y pulsá [bold]Enviar[/bold] en Gmail. JobBot no envía por vos."
            )
        job_dir = config.output_dir / "jobs" / job.id
        app_dir = prepare_application_package(
            job, config.output_dir, job_dir=job_dir, candidate=candidate
        )
        _note_no_receipt(session, job.id, str(app_dir), plan.ats_url or draft.to)
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
    job_dir = config.output_dir / "jobs" / job.id
    filled_in_cdp = False
    if cdp:
        _fill_ats_over_cdp(
            str(cdp),
            _ats_target_url(adapter, job, plan.ats_url),
            candidate,
            config,
            job.id,
            foreground=foreground,
            attach_timeout_s=cdp_timeout,
        )
        filled_in_cdp = True
    app_dir = prepare_application_package(
        job, config.output_dir, job_dir=job_dir, candidate=candidate
    )
    if not filled_in_cdp:
        if adapter is not None and hasattr(adapter, "open"):
            opened = adapter.open(job)
            if opened:
                console.print(background_notice(opened))
        else:
            from jobbot.adapters.ats.apply import open_ats_in_browser

            console.print(open_ats_in_browser(plan.ats_url))
    # Write prefill cheat-sheet next to package. Contact stays in profile.yaml.
    cheat = app_dir / "ats_prefill.yaml"
    import yaml

    cheat.write_text(
        yaml.safe_dump(
            {
                "ats_url": plan.ats_url,
                "ats_kind": plan.ats_kind.value,
                "fields": prefill_sheet_fields(candidate),
                "omitted_contact": ["email", "phone"],
                "needs_review": prefill_review,
                "note": (
                    "Fill only known fields; leave blank rather than inventing. "
                    "Email and phone are not copied here — read them from profile.yaml."
                ),
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    where = "in your Chrome (CDP tab left open)" if filled_in_cdp else ""
    console.print(f"[green]Opened ATS[/green] {plan.ats_url} {where}".rstrip())
    console.print(f"Prefill sheet: {cheat}")
    console.print("Submit manually after reviewing HITL fields.")
    _learn_form_from_apply(config, plan.ats_url, job.company)
    _note_no_receipt(session, job.id, str(app_dir), plan.ats_url)


@application_app.command("check-answer")
def application_check_answer(
    job_id: Annotated[str, typer.Argument()],
    question: Annotated[str, typer.Option("--question", "-q", help="The form's question")],
    text: Annotated[str | None, typer.Option("--text", help="The answer to check")] = None,
    file: Annotated[
        Path | None, typer.Option("--file", help="Read the answer from this file")
    ] = None,
) -> None:
    """Check a free-text answer against profile.yaml and the stored posting (pastes nothing).

    Exit 0 when every claim is backed, 2 when a claim is unbacked or misattributed,
    4 when the question asks for motivation, including a cover letter whose claims
    are all backed: the output says so, and only you can confirm the motivation.
    """
    from jobbot.applications.answer_check import Verdict, check_answer, render_answer_check

    if text is not None and file is None:
        answer = text
    elif file is not None and text is None:
        answer = file.read_text(encoding="utf-8")
    else:
        err_console.print("[red]Give the answer with --text or --file (one of them).[/red]")
        raise _QuietExit(VALIDATION_FAILURE)
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

    check = check_answer(question, answer, candidate, job)
    for line in render_answer_check(check, job):
        console.print(line, markup=False, highlight=False)
    if check.verdict is Verdict.REJECTED:
        raise _QuietExit(VALIDATION_FAILURE)
    if check.verdict is Verdict.NEEDS_CANDIDATE:
        raise _QuietExit(MANUAL_CHALLENGE)


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
        for event in ApplicationRepository(session).events_for(app.id):
            console.print(f"  event {event.event_type}: {event.detail or '—'}")
    else:
        console.print("No application record yet. Run: jobbot application prepare " + job_id)


@application_app.command("status")
def application_status(
    job_id: Annotated[str, typer.Argument()],
    set_status: Annotated[
        str | None,
        typer.Option("--set", help="Move the pipeline. applied asks first."),
    ] = None,
    yes: Annotated[bool, typer.Option("--yes", help="Skip the applied confirmation")] = False,
) -> None:
    """Show or set one job's pipeline status. A new job is saved."""
    from jobbot.applications.tracker import TrackerError, parse_status, status_label

    session, _config = _session()
    job = JobRepository(session).get(job_id)
    if job is None:
        err_console.print(f"[red]Job not found: {job_id}[/red]")
        raise typer.Exit(GENERIC_FAILURE)
    repo = ApplicationRepository(session)
    if set_status is not None:
        try:
            target = parse_status(set_status)
        except TrackerError as exc:
            err_console.print(f"[red]{exc}[/red]")
            raise _QuietExit(VALIDATION_FAILURE) from exc
        if (
            target is ApplicationStatus.APPLIED
            and not yes
            and not typer.confirm(f"Set {job.id} to applied?", default=False)
        ):
            console.print("Aborted.")
            raise _QuietExit(USER_CANCEL)
        repo.upsert_for_job(job.id, status=target)
    current = repo.get_for_job(job.id)
    label = status_label(current)
    when = current.updated_at.isoformat() if current is not None else job.discovered_at.isoformat()
    console.print(f"{job.id}  {label}  {when}")
    if job.note:
        console.print(f"note: {job.note}")


@application_app.command("tracker")
def application_tracker(
    status: Annotated[
        str | None,
        typer.Option("--status", help="Only this pipeline label, including saved"),
    ] = None,
) -> None:
    """List stored jobs by pipeline status. Order is the job id."""
    from jobbot.applications.tracker import known_status, status_label

    if status is not None and not known_status(status):
        err_console.print(f"[red]unknown status {status!r}[/red]")
        raise _QuietExit(VALIDATION_FAILURE)
    session, _config = _session()
    apps = {app.job_id: app for app in ApplicationRepository(session).list_all()}
    wanted = status.casefold() if status else None
    for job in sorted(JobRepository(session).list_all(), key=lambda item: item.id):
        label = status_label(apps.get(job.id))
        if wanted is not None and label != wanted:
            continue
        note = f"  {job.note}" if job.note else ""
        console.print(f"{job.id}  {label}  {job.company}  {job.title}{note}")


@application_app.command("cover-letter")
def application_cover_letter(
    job_id: Annotated[str, typer.Argument()],
    apply_changes: Annotated[
        bool,
        typer.Option("--apply", help="Record the path on the package manifest, if one exists"),
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Skip the manifest confirmation")] = False,
) -> None:
    """Write a cover letter that only restates profile facts. Nothing is sent."""
    from jobbot.applications.cover_letter import draft_cover_letter, record_manifest

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
    letter = config.output_dir / "jobs" / job.id / "cover-letter.txt"
    letter.parent.mkdir(parents=True, exist_ok=True)
    letter.write_text(draft_cover_letter(candidate, job), encoding="utf-8")
    console.print(str(letter))
    manifest = config.output_dir / "jobs" / job.id / "application" / "manifest.json"
    if not apply_changes:
        return
    if not manifest.is_file():
        console.print("No application package. Manifest unchanged.")
        return
    if (
        not yes
        and not typer.confirm(f"Record {letter.name} on the package manifest?", default=False)
    ):
        console.print("Aborted.")
        raise _QuietExit(USER_CANCEL)
    record_manifest(manifest, letter)
    console.print(f"Recorded {letter}")


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


@applications_app.command("feedback")
def applications_feedback(
    file: Annotated[
        str | None,
        typer.Option("--file", help="Pasted employer message. Otherwise stdin."),
    ] = None,
    job: Annotated[
        str | None,
        typer.Option("--job", help="Force the posting id when the message names it."),
    ] = None,
    apply: Annotated[
        bool,
        typer.Option("--apply", help="Write the event. Default is dry-run."),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option("--yes", help="Confirm a rejection that would replace an offer."),
    ] = False,
) -> None:
    """Classify a pasted employer message and record it on the application."""
    from jobbot.applications.feedback import FeedbackError, read_feedback, store_feedback

    body = _pasted_message(file)
    session, config = _session()
    try:
        reading = read_feedback(
            body,
            JobRepository(session).list_all(),
            ApplicationRepository(session).list_all(),
            job_id=job,
        )
    except FeedbackError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise _QuietExit(VALIDATION_FAILURE) from exc
    for line in reading.lines():
        console.print(line)
    if not apply:
        console.print("[dim]dry-run: nothing written[/dim]")
        return
    if reading.needs_confirm and not yes:
        err_console.print("[yellow]Sin --yes el estado offer no cambia.[/yellow]")
        raise _QuietExit(VALIDATION_FAILURE)
    store_feedback(session, config.root, reading, body)


@applications_app.command("report")
def applications_report() -> None:
    """Funnel per stored posting: responses, interviews and rejections."""
    from jobbot.applications.feedback import funnel, report_lines

    session, _ = _session()
    for line in report_lines(funnel(session)):
        console.print(line)


def _pasted_message(file: str | None) -> str:
    if file:
        path = Path(file)
        if not path.is_file():
            err_console.print(f"[red]File not found: {file}[/red]")
            raise _QuietExit(VALIDATION_FAILURE)
        return path.read_text(encoding="utf-8")
    if sys.stdin.isatty():
        err_console.print("[red]Paste a message via --file or stdin.[/red]")
        raise _QuietExit(VALIDATION_FAILURE)
    return sys.stdin.read()


# ── indeed / linkedin (Vertical B) ───────────────────────────────────────────


@indeed_app.command("login")
def indeed_login(
    cdp: Annotated[
        str | None,
        typer.Option("--cdp", help="Attach to Chrome CDP (e.g. http://127.0.0.1:9222)"),
    ] = None,
    continue_url: Annotated[
        str | None,
        typer.Option(
            "--continue-url",
            help=(
                "Magic / verify link from Indeed's email (paste from phone). "
                "JobBot opens it in the persistent Chrome profile; never types a password."
            ),
        ),
    ] = None,
) -> None:
    """Open Indeed login (HITL). Prefer email/magic link; optional --continue-url."""
    from jobbot.adapters.indeed.client import IndeedAdapter, normalize_indeed_continue_url
    from jobbot.browser.cdp import resolve_cdp_url

    if continue_url is not None:
        try:
            continue_url = normalize_indeed_continue_url(continue_url)
        except ValueError as exc:
            err_console.print(f"[red]{exc}[/red]")
            raise typer.Exit(VALIDATION_FAILURE) from exc

    IndeedAdapter.from_config(load_config(), cdp_url=resolve_cdp_url(cdp)).login(
        continue_url=continue_url
    )


@indeed_app.command("status")
def indeed_status(
    cdp: Annotated[str | None, typer.Option("--cdp")] = None,
) -> None:
    """Check whether an Indeed session appears valid."""
    from jobbot.adapters.indeed.client import IndeedAdapter
    from jobbot.browser.cdp import resolve_cdp_url

    ok = IndeedAdapter.from_config(load_config(), cdp_url=resolve_cdp_url(cdp)).session_valid()
    if ok:
        console.print("Indeed session: valid")
        return
    console.print("Indeed session: not authenticated")
    raise typer.Exit(AUTH_REQUIRED)


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
    """Pull Indeed profile snapshot (read). Refuses when the structured editor is gone."""
    from jobbot.adapters.indeed.client import IndeedAdapter
    from jobbot.adapters.indeed.resume_edit import IndeedUiChanged
    from jobbot.browser.cdp import resolve_cdp_url

    try:
        path = IndeedAdapter.from_config(
            load_config(), cdp_url=resolve_cdp_url(cdp)
        ).pull_and_save()
    except IndeedUiChanged as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(UI_CHANGED) from exc
    console.print(f"[green]Wrote[/green] {path}")


@indeed_app.command("diff")
def indeed_diff(
    section: Annotated[str | None, typer.Option("--section")] = None,
) -> None:
    """Diff local profile vs Indeed snapshot."""
    from jobbot.adapters.diff_engine import render_profile_diff
    from jobbot.adapters.indeed.resume_edit import DOCUMENT_ONLY_MESSAGE, load_editor_state

    config = load_config()
    if load_editor_state(config.output_dir) == "document_only":
        console.print(DOCUMENT_ONLY_MESSAGE)
        raise typer.Exit(UI_CHANGED)
    candidate = load_profile(config.profile_path)
    console.print(render_profile_diff(candidate, config.output_dir, "indeed", section=section))


def _sync_indeed_preferences(
    adapter: IndeedAdapter, *, apply_changes: bool, yes: bool
) -> None:
    from jobbot.adapters.indeed.preferences import plan_preferences, save_preferences
    from jobbot.jobs.eligibility import (
        ApplicationAnswers,
        default_answers_path,
        read_answers_mapping,
    )
    from jobbot.profile.loader import load_profile

    candidate = load_profile(adapter.config.profile_path)
    answers_path = default_answers_path(adapter.config.root)
    answers = (
        ApplicationAnswers.model_validate(read_answers_mapping(answers_path))
        if answers_path.is_file()
        else ApplicationAnswers()
    )
    for line in plan_preferences(candidate, answers).lines:
        console.print(line)
    if not apply_changes:
        return
    with adapter._session() as browser:
        confirmed = yes or typer.confirm("¿Guardar preferencias en Indeed?", default=False)
        if not confirmed:
            raise typer.Exit(USER_CANCEL)
        save_preferences(browser.page, confirmed=True)


@indeed_app.command("upload-cv")
def indeed_upload_cv(
    apply_changes: Annotated[
        bool,
        typer.Option("--apply", help="Upload when the hash differs (default: check only)"),
    ] = False,
    variant: Annotated[
        str,
        typer.Option("--variant", help="base_es or base_en when --cv is omitted"),
    ] = "base_es",
    cv: Annotated[
        Path | None,
        typer.Option("--cv", help="PDF to upload (default: output/base/cv.pdf)"),
    ] = None,
    cdp: Annotated[str | None, typer.Option("--cdp")] = None,
) -> None:
    """Replace the Indeed PDF when its hash differs from the last receipt."""
    from jobbot.adapters.indeed.cv_upload import (
        ALREADY_CURRENT,
        KNOWN_VARIANTS,
        file_sha256,
        icon_glyph_message,
        load_receipt_sha,
    )

    config = load_config()
    if variant not in KNOWN_VARIANTS:
        err_console.print(f"variante desconocida: {variant}")
        raise typer.Exit(VALIDATION_FAILURE)
    path = cv if cv is not None else config.output_dir / "base" / "cv.pdf"
    if not path.is_file():
        err_console.print(f"no está el PDF: {path}")
        raise typer.Exit(VALIDATION_FAILURE)
    reason = icon_glyph_message(path)
    if reason:
        err_console.print(reason)
        raise typer.Exit(VALIDATION_FAILURE)
    digest = file_sha256(path)
    if load_receipt_sha(config.output_dir) == digest:
        console.print(ALREADY_CURRENT)
        return
    if not apply_changes:
        console.print(f"subiría {path.name}")
        return
    from jobbot.adapters.indeed.client import IndeedAdapter
    from jobbot.browser.cdp import resolve_cdp_url

    adapter = IndeedAdapter.from_config(config, cdp_url=resolve_cdp_url(cdp))
    with adapter._session() as browser:
        browser.page.set_input_files('input[type="file"]', str(path))


@indeed_app.command("sync")
def indeed_sync(
    section: Annotated[
        str,
        typer.Option(
            "--section",
            help="headline|summary|skills|experience|preferences|all (default: all)",
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
    """Dry-run or apply Indeed sync; --section preferences plans titles and salary."""
    from jobbot.adapters.indeed.client import IndeedAdapter
    from jobbot.adapters.indeed.owner import IndeedOwnerMismatch
    from jobbot.adapters.indeed.resume_edit import IndeedUiChanged
    from jobbot.browser.cdp import resolve_cdp_url

    adapter = IndeedAdapter.from_config(load_config(), cdp_url=resolve_cdp_url(cdp))
    if section == "preferences":
        _sync_indeed_preferences(adapter, apply_changes=apply_changes, yes=yes)
        return
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
        try:
            result = adapter.apply_reconcile()
        except IndeedUiChanged as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(UI_CHANGED) from exc
        except IndeedOwnerMismatch as exc:
            err_console.print(str(exc))
            raise typer.Exit(VALIDATION_FAILURE) from exc
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
    try:
        result = adapter.apply_sync_plan(plan, section=section)
    except IndeedUiChanged as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(UI_CHANGED) from exc
    except IndeedOwnerMismatch as exc:
        err_console.print(str(exc))
        raise typer.Exit(VALIDATION_FAILURE) from exc
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
    from jobbot.browser.cdp import CdpAttachInterrupted, CdpAttachTimeout, resolve_cdp_url

    try:
        adapter = LinkedInAdapter.from_config(load_config(), cdp_url=resolve_cdp_url(cdp))
        ok = adapter.session_valid()
    except (CdpAttachTimeout, CdpAttachInterrupted) as exc:
        err_console.print(f"LinkedIn session: unreachable ({exc})")
        raise typer.Exit(GENERIC_FAILURE) from exc
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
    """Diff local profile vs LinkedIn snapshot. Mismatches are warnings; exit 0."""
    from jobbot.adapters.diff_engine import render_profile_diff

    config = load_config()
    candidate = load_profile(config.profile_path)
    console.print(render_profile_diff(candidate, config.output_dir, "linkedin", section=section))


@linkedin_app.command("import")
def linkedin_import(
    section: Annotated[
        str | None,
        typer.Option("--section", help="headline, experience, education, or skills"),
    ] = None,
    apply_changes: Annotated[
        bool,
        typer.Option("--apply", help="Write confirmed sections into profile.yaml"),
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Confirm every section")] = False,
) -> None:
    """Merge a stored LinkedIn snapshot into profile.yaml. Dry-run writes nothing."""
    from jobbot.adapters.diff_engine import load_snapshot
    from jobbot.adapters.linkedin.importer import (
        LinkedInImportError,
        apply_import,
        import_plan,
        render_change,
    )
    from jobbot.cv.tune import backup_profile

    config = load_config()
    if not config.profile_path.is_file():
        err_console.print(
            "[red]No profile.yaml. The snapshot has no name, so import cannot create one.[/red]"
        )
        raise _QuietExit(VALIDATION_FAILURE)
    external = load_snapshot(config.output_dir, "linkedin")
    if external is None:
        err_console.print("[red]No linkedin snapshot found. Run: jobbot linkedin pull[/red]")
        raise _QuietExit(VALIDATION_FAILURE)
    try:
        candidate = load_profile(config.profile_path)
    except ProfileLoadError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(VALIDATION_FAILURE) from exc
    try:
        plan = import_plan(candidate, external, section=section)
    except LinkedInImportError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise _QuietExit(VALIDATION_FAILURE) from exc
    for warning in plan.warnings:
        err_console.print(f"[yellow]{warning}[/yellow]")
    for change in plan.changes:
        console.print(render_change(change))
    if not plan.changes:
        console.print("Nothing to write.")
        return
    if not apply_changes:
        console.print("Dry-run only. Nothing written.")
        return
    raw = yaml.safe_load(config.profile_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        err_console.print("[red]profile.yaml is not a mapping[/red]")
        raise _QuietExit(VALIDATION_FAILURE)
    chosen: set[str] = set()
    for name in ("headline", "experience", "education", "skills"):
        if not any(change.section == name for change in plan.changes):
            continue
        if yes or typer.confirm(f"Write LinkedIn {name} into profile.yaml?", default=False):
            chosen.add(name)
    if not chosen:
        console.print("Nothing written.")
        return
    backup = backup_profile(config.profile_path)
    merged = apply_import(raw, plan, sections=chosen)
    config.profile_path.write_text(
        yaml.safe_dump(merged, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    console.print(f"Wrote profile.yaml. Backup: {backup.name}")


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
        typer.Argument(help="Content search keywords (default: 'hiring' + your profile searches)"),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", help="Max posts to keep")] = 20,
    max_queries: Annotated[
        int,
        typer.Option("--max-queries", help="Profile searches to run when no query is given"),
    ] = _DEFAULT_MAX_QUERIES,
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
        queries = [f"hiring {text}" for text in _search_queries(config, None, max_queries)]
    else:
        queries = [query]
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

    def search_one(text: str) -> list[JobPosting]:
        if fixture is not None:
            return source.search_from_fixture(
                fixture.expanduser().resolve(),
                query=text,
                countries=countries,
                allow_remote=config.search.allow_remote,
                max_age_days=max_age,
            )
        console.print(f"Sweeping LinkedIn content for [bold]{text}[/bold]…")
        return source.search_jobs(
            JobSearchQuery(
                query=text,
                limit=limit,
                countries=countries,
                allow_remote=config.search.allow_remote,
                copy_permalinks=copy_links,
                max_age_days=max_age,
            )
        )

    found = _unique_postings(_run_portal_queries(queries, search_one, portal="LinkedIn"))
    if fixture is not None:
        for reason in source.fixture_skip_reasons(
            fixture.expanduser().resolve(),
            countries=countries,
            allow_remote=config.search.allow_remote,
            max_age_days=max_age,
        ):
            console.print(f"descartada por {reason}")

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
    scores: list[float] = []
    for raw in found[:limit]:
        job = repo.upsert_external(raw)
        if candidate is not None:
            match = analyzer.analyze(candidate, job)
            repo.update_match_score(job.id, match.score)
            job.match_score = match.score
            scores.append(match.score)
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
    if candidate is not None:
        _warn_if_matcher_blind(scores)


@linkedin_app.command("jobs")
def linkedin_jobs(
    query: Annotated[
        str | None,
        typer.Argument(help="Job search keywords (default: the profile's search queries)"),
    ] = None,
    fixture: Annotated[
        Path | None,
        typer.Option("--fixture", help="Parse a saved search-results page (no browser)"),
    ] = None,
    country: Annotated[
        list[str] | None,
        typer.Option("--country", help="Keep cards in these countries (default: CL)"),
    ] = None,
    any_country: Annotated[
        bool,
        typer.Option("--any-country", help="Keep cards from every country"),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Print the table and write nothing"),
    ] = False,
    cdp: Annotated[
        str | None,
        typer.Option("--cdp", help="Attach to Chrome CDP; without this or --fixture, stop"),
    ] = None,
) -> None:
    """Save LinkedIn job cards from a search page; --dry-run writes nothing."""
    from jobbot.adapters.linkedin.job_search import jobs_from_search_html
    from jobbot.jobs.geo import detect_country, resolve_countries

    config = load_config()
    countries = resolve_countries(config.search.countries, country, any_country=any_country)
    if fixture is not None:
        html = fixture.expanduser().resolve().read_text(encoding="utf-8")
    elif cdp:
        err_console.print("linkedin jobs --cdp aún no abre la búsqueda; pasa --fixture")
        raise typer.Exit(VALIDATION_FAILURE)
    else:
        err_console.print("pasa --fixture o --cdp; no abro un navegador solo")
        raise typer.Exit(VALIDATION_FAILURE)
    cards = jobs_from_search_html(html)
    if countries:
        cards = [
            card
            for card in cards
            if (detected := detect_country(f"{card.location or ''}\n{card.title}")) is None
            or detected in countries
        ]
    label = query or "perfil"
    table = Table(title=f"LinkedIn jobs: {label}" + (" (dry-run)" if dry_run else ""))
    table.add_column("Title")
    table.add_column("Company")
    table.add_column("Where")
    table.add_column("URL")
    for card in cards:
        table.add_row(
            card.title[:40],
            card.company[:28],
            card.location or "?",
            card.url or "",
        )
    console.print(table)
    if dry_run:
        console.print("Dry-run: nothing written.")
        return
    _session_pair, config = _session()
    repo = JobRepository(_session_pair)
    for card in cards:
        stored = repo.upsert_external(card)
        write_job_json(stored, config.output_dir)
    console.print("Next: jobbot jobs shortlist")


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
    from jobbot.adapters.getonboard.draft import omission_line

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
    notice = omission_line(result.fields)
    if notice:
        console.print(notice)
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
    console.print(background_notice(url))
    console.print("Reemplaza textos viejos con output/getonboard/profile_permanent.md")


@getonboard_app.command("upload-cv")
def getonboard_upload_cv(
    apply_changes: Annotated[
        bool,
        typer.Option("--apply", help="Upload after validation (default: validate only)"),
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
    make_default: Annotated[
        bool,
        typer.Option("--default/--no-default", help="Mark the uploaded CV as default"),
    ] = True,
    label: Annotated[
        str,
        typer.Option("--label", help="Name shown under Tus CVs"),
    ] = "CV base",
    cdp: Annotated[
        str | None,
        typer.Option("--cdp", help="Attach to your logged-in Chrome (browser chrome-debug)"),
    ] = None,
    cv: Annotated[
        Path | None,
        typer.Option("--cv", help="PDF to upload (default: output/base/cv.pdf)"),
    ] = None,
) -> None:
    """Validate the local CV PDF, upload it, and report whether the portal rewrote the profile."""
    from jobbot.adapters.getonboard.cv_upload import (
        PROFILE_REWRITE_WARNING,
        GobCvUploadError,
        profile_rewrite_guard,
        resolve_base_cv,
        upload_cv,
        validate_cv_for_upload,
        wait_for_cv_parse,
        write_upload_receipt,
    )
    from jobbot.adapters.getonboard.profile_edit import GOB_EDIT_URL, read_current

    config = load_config()
    path = cv.expanduser().resolve() if cv else resolve_base_cv(config.output_dir)
    check = validate_cv_for_upload(path)
    console.print("[bold]Local CV check[/bold] (before any upload)")
    for line in check.summary_lines():
        # Paths must stay one token: soft-wrap mid-filename breaks copy/paste and tests.
        console.print(f"  {line}", soft_wrap=False, overflow="ignore", crop=False)
    if not check.ok:
        err_console.print("[red]Validation failed — nothing was uploaded.[/red]")
        raise typer.Exit(VALIDATION_FAILURE)
    if not apply_changes:
        console.print(
            "Dry-run. Re-run with [bold]--apply --cdp URL[/bold] to upload "
            "(you confirm after seeing the hash)."
        )
        return
    if not yes and not typer.confirm(
        f"Upload {path.name} as {label!r}" + (" and mark default?" if make_default else "?"),
        default=False,
    ):
        console.print("Aborted.")
        raise typer.Exit(SUCCESS)
    try:
        with _getonboard_session(config, cdp) as browser:
            page = browser.page
            page.goto(GOB_EDIT_URL, wait_until="domcontentloaded")
            before = read_current(page)
            result = upload_cv(
                page,
                path,
                label=label,
                make_default=make_default,
                check=check,
            )
            if not wait_for_cv_parse(page):
                err_console.print("la lectura del CV no terminó")
                console.print(PROFILE_REWRITE_WARNING)
                raise typer.Exit(GENERIC_FAILURE)
            page.goto(GOB_EDIT_URL, wait_until="domcontentloaded")
            after = read_current(page)
    except GobCvUploadError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(GENERIC_FAILURE) from exc
    guard = profile_rewrite_guard(before, after)
    write_upload_receipt(config.output_dir, check, result, overwrite=guard.receipt)
    console.print(
        f"[green]Uploaded[/green] {result.path.name} as {result.label!r} "
        f"(default={result.is_default}) → {result.resumes_url}"
    )
    if guard.overwritten:
        for line in guard.lines:
            console.print(line, markup=False)
    else:
        console.print(guard.receipt, markup=False)


@getonboard_app.command("open-cvs")
def getonboard_open_cvs() -> None:
    """Open Get on Board 'Tus CVs' (HITL fallback if upload-cv is not enough)."""
    from jobbot.adapters.getonboard.client import GetOnBoardProfileClient
    from jobbot.adapters.getonboard.cv_upload import resolve_base_cv, validate_cv_for_upload

    config = load_config()
    path = resolve_base_cv(config.output_dir)
    check = validate_cv_for_upload(path)
    url = GetOnBoardProfileClient.from_config(config).open_resumes()
    console.print(background_notice(url))
    console.print("[bold]Local CV check[/bold]")
    for line in check.summary_lines():
        console.print(f"  {line}", soft_wrap=False, overflow="ignore", crop=False)
    if check.ok:
        console.print(
            "Prefer: [bold]jobbot getonboard upload-cv --apply --cdp URL[/bold] "
            "(validates, then uploads)."
        )
    else:
        console.print("Fix the PDF first: [bold]jobbot cv build[/bold]")


@getonboard_app.command("sync")
def getonboard_sync(
    apply_changes: Annotated[
        bool,
        typer.Option(
            "--apply",
            help="Open profile + CV editors (default: dry-run checklist only)",
        ),
    ] = False,
    section: Annotated[
        str | None,
        typer.Option("--section", help="skills, seniority, english (comma-separated)"),
    ] = None,
) -> None:
    """Maintain permanent GoB profile; --section plans skills, seniority and English."""
    from jobbot.adapters.getonboard.client import GetOnBoardProfileClient
    from jobbot.adapters.getonboard.profile_fields import parse_sections, render_section_plan
    from jobbot.jobs.eligibility import default_answers_path, load_application_answers

    config = load_config()
    if section:
        try:
            sections = parse_sections(section)
            candidate = load_profile(config.profile_path)
            answers = load_application_answers(default_answers_path(config.root))
        except (ProfileLoadError, ValueError) as exc:
            err_console.print(str(exc))
            raise typer.Exit(VALIDATION_FAILURE) from exc
        for line in render_section_plan(candidate, answers, sections):
            console.print(line, markup=False)
        return

    client = GetOnBoardProfileClient.from_config(config)
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
    console.print(background_notice(client.open_profile_edit()))
    console.print("Abriendo zona profesional (navega a Tus CVs)…")
    console.print(background_notice(client.open_resumes()))
    console.print("HITL: reemplaza textos viejos, sube CV default, guarda. Luego postula.")


@getonboard_app.command("search")
def getonboard_search(
    query: Annotated[
        str | None,
        typer.Argument(help="Search query (default: the searches in your own profile)"),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", help="Max results per query (1-50)")] = 20,
    max_queries: Annotated[
        int,
        typer.Option("--max-queries", help="Profile searches to run when no query is given"),
    ] = _DEFAULT_MAX_QUERIES,
) -> None:
    """Search Get on Board (Spanish/LATAM) and store jobs locally."""
    from jobbot.adapters.getonboard.jobs import GetOnBoardJobSource
    from jobbot.jobs.sources import JobSearchQuery

    if limit < 1 or limit > 50:
        err_console.print("--limit must be between 1 and 50")
        raise typer.Exit(GENERIC_FAILURE)

    session, config = _session()
    queries = _search_queries(config, query, max_queries)
    source = GetOnBoardJobSource(config)

    def search_one(text: str) -> list[JobPosting]:
        console.print(f"Searching Get on Board for [bold]{text}[/bold]…")
        return source.search_jobs(JobSearchQuery(query=text, limit=limit))

    found = _unique_postings(_run_portal_queries(queries, search_one, portal="Get on Board"))

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
    scores: list[float] = []
    for raw in found:
        job = repo.upsert_external(raw)
        if candidate is not None:
            match = analyzer.analyze(candidate, job)
            repo.update_match_score(job.id, match.score)
            job.match_score = match.score
            scores.append(match.score)
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
    if candidate is not None:
        _warn_if_matcher_blind(scores)


@torre_app.command("search")
def torre_search(
    query: Annotated[
        str | None,
        typer.Argument(help="Search query (default: the searches in your own profile)"),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", help="Max results per query (1-50)")] = 20,
    remote: Annotated[bool, typer.Option("--remote", help="Only remote opportunities")] = False,
    max_queries: Annotated[
        int,
        typer.Option("--max-queries", help="Profile searches to run when no query is given"),
    ] = _DEFAULT_MAX_QUERIES,
) -> None:
    """Search Torre (LATAM / remote) and store jobs locally."""
    from jobbot.adapters.torre.jobs import TorreJobSource
    from jobbot.jobs.sources import JobSearchQuery

    if limit < 1 or limit > 50:
        err_console.print("--limit must be between 1 and 50")
        raise typer.Exit(GENERIC_FAILURE)

    session, config = _session()
    queries = _search_queries(config, query, max_queries)

    narrator = _narrator()
    source = TorreJobSource(config)

    def search_one(text: str) -> list[JobPosting]:
        narrator.phase(Phase.RECEIVING_WORLD, f"Torre: {text}")
        return source.search_jobs(JobSearchQuery(query=text, limit=limit, remote=remote))

    found = _unique_postings(_run_portal_queries(queries, search_one, portal="Torre"))

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
    scores: list[float] = []
    for raw in found:
        job = repo.upsert_external(raw)
        if candidate is not None:
            match = analyzer.analyze(candidate, job)
            repo.update_match_score(job.id, match.score)
            job.match_score = match.score
            scores.append(match.score)
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
    if candidate is not None:
        _warn_if_matcher_blind(scores)


@empleospublicos_app.command("search")
def empleospublicos_search(
    query: Annotated[
        str | None,
        typer.Argument(help="Filter text (default: profile searches)"),
    ] = None,
    fixture: Annotated[
        Path | None,
        typer.Option(
            "--fixture",
            exists=True,
            dir_okay=False,
            readable=True,
            help="Offline: saved open-data CSV or search JSON dump (default: live open data)",
        ),
    ] = None,
    region: Annotated[
        str | None,
        typer.Option(
            "--region", "--location", help="Only this region (e.g. 'Biobío', 'Metropolitana')"
        ),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", help="Max results per query (1-50)")] = 20,
    max_queries: Annotated[
        int,
        typer.Option("--max-queries", help="Profile searches when no query is given"),
    ] = _DEFAULT_MAX_QUERIES,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Preview only: no database, job JSON, portals or companies are written",
        ),
    ] = False,
) -> None:
    """Search open Empleos Públicos concursos (Servicio Civil open data) and store leads."""
    from jobbot.adapters.empleospublicos.jobs import (
        EmpleosPublicosJobSource,
        EmpleosPublicosParseError,
    )
    from jobbot.adapters.empleospublicos.open_data import (
        OpenDataError,
        format_salary,
        staleness_warning,
    )
    from jobbot.jobs.sources import JobSearchQuery

    if limit < 1 or limit > 50:
        err_console.print("--limit must be between 1 and 50")
        raise typer.Exit(GENERIC_FAILURE)

    config = load_config()
    queries = _search_queries(config, query, max_queries)
    source = EmpleosPublicosJobSource(
        config, fixture=fixture.expanduser().resolve() if fixture is not None else None
    )
    if fixture is None:
        console.print("Reading Servicio Civil open data (one download, ~11 MB)…")
    found: list[JobPosting] = []
    failed: list[str] = []
    for text in queries:
        try:
            found.extend(
                source.search_jobs(JobSearchQuery(query=text, location=region, limit=limit))
            )
        except (EmpleosPublicosParseError, OpenDataError) as exc:
            failed.append(text)
            err_console.print(f"[red]Empleos Públicos search failed for {text!r}: {exc}[/red]")
    if failed and len(failed) == len(queries):
        raise typer.Exit(GENERIC_FAILURE)
    stale = staleness_warning(source.as_of)
    if stale:
        console.print(f"[yellow]{stale}[/yellow]")
    found = _unique_postings(found)
    if not found:
        console.print("No open concursos matched.")
        raise typer.Exit(SUCCESS)
    if fixture is None and not dry_run:
        source.remember_portal()

    try:
        candidate = load_profile(config.profile_path)
    except ProfileLoadError:
        candidate = None
    analyzer = RuleBasedJobAnalyzer()
    repo = None if dry_run else JobRepository(_session()[0])
    table = Table(
        title="Empleos Públicos (preview, nothing stored)"
        if dry_run
        else "Empleos Públicos (leads)"
    )
    for column in (
        "ID",
        "Institución",
        "Cargo",
        "Región",
        "Cierre",
        "Renta bruta",
        "Grado",
        "Match",
    ):
        table.add_column(column)
    stored: list[str] = []
    scores: list[float] = []
    for raw in found:
        facts = source.seen.get(raw.source_job_id or "")
        closes = f"{facts.closes_at:%Y-%m-%d %H:%M}" if facts and facts.closes_at else "-"
        salary = format_salary(facts.gross_salary) if facts and facts.gross_salary else "-"
        grade = facts.grade if facts and facts.grade else "-"
        job = raw if repo is None else repo.upsert_external(raw)
        if candidate is not None:
            match = analyzer.analyze(candidate, job)
            if repo is not None:
                repo.update_match_score(job.id, match.score)
            job.match_score = match.score
            scores.append(match.score)
        if repo is not None:
            write_job_json(job, config.output_dir)
            _learn_company_knowledge(config, job)
            stored.append(job.id)
        score = f"{job.match_score:.0f}%" if job.match_score is not None else "-"
        table.add_row(
            (raw.source_job_id or "-") if repo is None else job.id,
            job.company[:28],
            job.title[:36],
            (job.location or "-")[:20],
            closes,
            salary,
            grade,
            score,
        )
    console.print(table)
    if dry_run:
        console.print(
            f"Dry run: {len(found)} open concursos would be stored; nothing was written. "
            "Run again without [bold]--dry-run[/bold] to store them."
        )
    else:
        console.print(
            f"Stored {len(stored)} leads. Detail: "
            f"[bold]jobbot get URL --fixture ficha.html[/bold]. "
            f"Next: [bold]jobbot jobs match {stored[0]}[/bold]"
        )
    if candidate is not None:
        _warn_if_matcher_blind(scores)


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
    if save and (form.readable or form.sso_providers):
        stored = _store_form_knowledge(config, form)
        console.print(f"Learned (candidate knowledge): {stored}")
    elif save:
        console.print("[yellow]Nothing stored: the form could not be read.[/yellow]")


def _profile_states_or_exit(path: Path) -> list[Any]:
    from jobbot.portals.profile_state import ProfileStateError, load_states

    try:
        return load_states(path)
    except ProfileStateError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(VALIDATION_FAILURE) from exc


def _candidate_or_none(config: JobbotConfig) -> Any:
    from jobbot.profile.loader import ProfileLoadError, load_profile

    if not config.profile_path.is_file():
        return None
    try:
        return load_profile(config.profile_path)
    except ProfileLoadError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(VALIDATION_FAILURE) from exc


def _resolve_portal_state(config: JobbotConfig, portal_id: str) -> Any:
    from jobbot.portals.fill_catalog import catalog_state, fill_portal
    from jobbot.portals.profile_state import default_state_path

    states = _profile_states_or_exit(default_state_path(config.root))
    for state in states:
        if state.portal == portal_id:
            return state
    known = fill_portal(portal_id)
    if known is None:
        err_console.print(f"[red]Unknown portal: {portal_id}[/red]")
        raise typer.Exit(VALIDATION_FAILURE)
    return catalog_state(known)


@portals_profile_app.command("status")
def portals_profile_status(
    portal: Annotated[str | None, typer.Argument(help="One portal id")] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Machine-readable rows")] = False,
) -> None:
    """Coverage of tracked portals. Numbers and labels only; nothing is opened."""
    from datetime import UTC, datetime

    from jobbot.portals.profile_state import (
        coverage_report,
        cv_hashes_from_output,
        default_state_path,
    )

    config = load_config()
    path = default_state_path(config.root)
    if path.is_file():
        states = _profile_states_or_exit(path)
    else:
        from jobbot.portals.profile_state import AccountState, PortalProfileState, Priority
        from jobbot.portals.registry import default_portals_path, load_registry

        registry = load_registry(default_portals_path(config.root))
        states = [
            PortalProfileState(
                portal=entry.domain,
                adapter=entry.ats_kind.value,
                priority=Priority.medium,
                account=AccountState.unknown,
            )
            for entry in registry.portals
        ]
    if portal is not None:
        states = [item for item in states if item.portal == portal]
        if not states:
            err_console.print(f"[red]Unknown portal: {portal}[/red]")
            raise typer.Exit(VALIDATION_FAILURE)
    report = coverage_report(
        states,
        _candidate_or_none(config) if path.is_file() else None,
        now=datetime.now(UTC),
        cv_hashes=cv_hashes_from_output(config.root),
    )
    if as_json:
        console.print_json(data=report.to_public_dict())
        return
    console.print(
        f"KPI {report.kpi_num}/{report.kpi_den}  "
        f"automation {report.automation:.0%}  "
        f"SST gap {report.sst_gap}  due {report.due}"
    )
    table = Table(title="Portal profile coverage")
    table.add_column("Portal")
    table.add_column("Status")
    table.add_column("Level")
    table.add_column("c_p")
    table.add_column("CV")
    for row in report.portals:
        table.add_row(
            row.portal,
            row.status.value,
            str(row.level),
            f"{row.covered}/{row.applicable}",
            "yes" if row.cv_current else "no",
        )
    console.print(table)


@portals_profile_app.command("sheet")
def portals_profile_sheet(
    portal: Annotated[str, typer.Argument(help="Portal id from the fill catalog or the tracker")],
    lang: Annotated[str, typer.Option("--lang", help="es or en")] = "es",
    out: Annotated[Path | None, typer.Option("--out", help="Write the sheet here")] = None,
) -> None:
    """Fill sheet from the source of truth. Does not open a browser."""
    from jobbot.portals.fill_catalog import fill_portal
    from jobbot.portals.profile_sheet import render_fill_sheet
    from jobbot.portals.profile_state import default_alias_path, load_aliases

    config = load_config()
    candidate = _candidate_or_none(config)
    if candidate is None:
        err_console.print("[red]Profile not found. The sheet needs data/profile.yaml.[/red]")
        raise typer.Exit(VALIDATION_FAILURE)
    state = _resolve_portal_state(config, portal)
    if portal == "chiletrabajos":
        from jobbot.jobs.eligibility import default_answers_path, load_application_answers
        from jobbot.portals.chiletrabajos import render_chiletrabajos_sheet

        try:
            answers = load_application_answers(default_answers_path(config.root))
        except ValueError as exc:
            err_console.print(f"[red]{exc}[/red]")
            raise typer.Exit(VALIDATION_FAILURE) from exc
        text = render_chiletrabajos_sheet(candidate, answers)
        if out is not None:
            destination = out.expanduser()
            if not destination.is_absolute():
                destination = config.root / destination
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(text, encoding="utf-8")
            console.print(f"Wrote {destination}")
            return
        console.print(text, markup=False)
        return
    try:
        text = render_fill_sheet(
            state,
            candidate,
            load_aliases(default_alias_path(config.root)),
            lang=lang,
            catalog=fill_portal(portal),
        )
    except ValueError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(VALIDATION_FAILURE) from exc
    if out is not None:
        destination = out.expanduser()
        if not destination.is_absolute():
            destination = config.root / destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8")
        console.print(f"Wrote {destination}")
        return
    console.print(text, markup=False)


@portals_profile_app.command("mark-updated")
def portals_profile_mark_updated(
    portal: Annotated[str, typer.Argument()],
    sections: Annotated[str, typer.Option("--sections", help="Comma-separated canonical sections")],
    evidence: Annotated[str, typer.Option("--evidence", help="diff, receipt, or none")],
    note: Annotated[str | None, typer.Option("--note")] = None,
) -> None:
    """Record a manual fill. evidence=none does not raise coverage."""
    from datetime import UTC, datetime

    from jobbot.portals.profile_state import (
        EvidenceKind,
        ProfileStateError,
        cv_hashes_from_output,
        default_state_path,
        mark_updated,
        save_states,
    )

    config = load_config()
    path = default_state_path(config.root)
    states = _profile_states_or_exit(path)
    index = next((i for i, item in enumerate(states) if item.portal == portal), None)
    if index is None:
        err_console.print(f"[red]Unknown portal: {portal}[/red]")
        raise typer.Exit(VALIDATION_FAILURE)
    try:
        kind = EvidenceKind(evidence)
    except ValueError as exc:
        err_console.print("[red]evidence must be diff, receipt, or none[/red]")
        raise typer.Exit(VALIDATION_FAILURE) from exc
    evidence_dir = config.root / "output" / "portals" / portal
    if kind is not EvidenceKind.none and not any(evidence_dir.glob("*")):
        err_console.print(
            f"[red]Missing evidence file in {evidence_dir}. "
            "A declaration without a file does not count.[/red]"
        )
        raise typer.Exit(VALIDATION_FAILURE)
    names = [item.strip() for item in sections.split(",") if item.strip()]
    try:
        states[index] = mark_updated(
            states[index],
            sections=names,
            evidence=kind,
            by="manual",
            now=datetime.now(UTC),
            candidate=_candidate_or_none(config),
            current_cv_sha256=cv_hashes_from_output(config.root).get(states[index].cv_variant),
            note=note,
        )
    except ProfileStateError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(VALIDATION_FAILURE) from exc
    save_states(states, path)
    console.print(f"Recorded {portal} evidence={kind.value} sections={','.join(names)}")


@portals_profile_app.command("import")
def portals_profile_import(
    csv_path: Annotated[Path, typer.Option("--csv", help="Tracker export")],
    apply: Annotated[bool, typer.Option("--apply", help="Write the tracker")] = False,
) -> None:
    """Seed portal state from a CSV. Without --apply, nothing is written."""
    from jobbot.portals.profile_state import (
        ProfileStateError,
        default_state_path,
        preview_import,
        save_states,
    )

    config = load_config()
    source = csv_path.expanduser()
    if not source.is_absolute():
        source = config.root / source
    if not source.is_file():
        err_console.print(f"[red]CSV not found: {source}[/red]")
        raise typer.Exit(VALIDATION_FAILURE)
    try:
        preview = preview_import(source)
    except ProfileStateError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(VALIDATION_FAILURE) from exc
    for column in preview.ignored_columns:
        console.print(f"ignorada: {column}")
    console.print(f"{len(preview.rows)} portal(s): {', '.join(preview.portals)}")
    if not apply:
        console.print("Dry run. Pass --apply to write data/portal_profiles.yaml.")
        return
    save_states(preview.rows, default_state_path(config.root))
    console.print(f"Wrote {default_state_path(config.root)}")


@portals_profile_app.command("seed")
def portals_profile_seed(
    apply: Annotated[
        bool,
        typer.Option("--apply", help="Write catalog portals that are missing"),
    ] = False,
) -> None:
    """Register the known career portals (UN, UNICEF, FAO, ADP, Devex, Impactpool, and the rest)."""
    from jobbot.portals.fill_catalog import FILL_PORTALS, catalog_state
    from jobbot.portals.profile_state import default_state_path, save_states

    config = load_config()
    path = default_state_path(config.root)
    states = _profile_states_or_exit(path)
    have = {item.portal for item in states}
    missing = [catalog_state(item) for item in FILL_PORTALS if item.portal not in have]
    for item in missing:
        console.print(f"{item.portal}  adapter={item.adapter}  account={item.account.value}")
    if not apply:
        console.print(f"Dry run. {len(missing)} portal(s). Pass --apply to write.")
        return
    save_states([*states, *missing], path)
    console.print(f"Wrote {len(missing)} portal(s) to {path}")


@portals_profile_app.command("push")
def portals_profile_push(
    portal: Annotated[str, typer.Argument()],
    apply: Annotated[
        bool,
        typer.Option("--apply", help="Refused: no browser writer types into these portals"),
    ] = False,
) -> None:
    """Refuse to type into a portal. Identity-bound sites never attach; the sheet is the fill."""
    config = load_config()
    state = _resolve_portal_state(config, portal)
    if state.account.value == "identity_bound" or state.adapter == "identity_bound":
        err_console.print(
            "[red]identity_bound: jobbot does not attach to this portal. "
            "Use `jobbot portals profile sheet`.[/red]"
        )
        raise typer.Exit(VALIDATION_FAILURE)
    err_console.print(
        f"[red]adapter {state.adapter} has no browser writer. "
        "Nothing was typed. The fill is `jobbot portals profile sheet`.[/red]"
    )
    del apply
    raise typer.Exit(VALIDATION_FAILURE)


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
    if form.sso_providers:
        names = ", ".join(form.sso_providers)
        console.print(f"Sign in with: {names}  [dim](you click; JobBot never starts OAuth)[/dim]")
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


def _run_portal_queries(
    queries: list[str],
    search: Callable[[str], list[JobPosting]],
    *,
    portal: str,
) -> list[JobPosting]:
    """Run every query. One portal error is reported; the other queries still run."""
    found: list[JobPosting] = []
    failed: list[str] = []
    for text in queries:
        try:
            found.extend(search(text))
        except Exception as exc:
            failed.append(text)
            err_console.print(f"[red]{portal} search failed for {text}: {exc}[/red]")
    if failed and len(failed) == len(queries):
        err_console.print(f"[red]{portal}: every search failed.[/red]")
        raise typer.Exit(GENERIC_FAILURE)
    if failed:
        err_console.print(
            f"[yellow]{portal}: {len(failed)} search(es) failed; the rest finished.[/yellow]"
        )
    return found


def _search_queries(config: JobbotConfig, query: str | None, max_queries: int) -> list[str]:
    """An explicit query runs alone; otherwise the profile's own searches.

    A default query hardcodes one career into the tool, and a headline can be a
    degree. The saved ``search_queries`` win; without them the set is derived from
    the experience, and only a profile with no experience falls back to its headline.
    """
    from jobbot.profile.search_queries import search_queries_for

    if query is not None:
        return [query]
    try:
        candidate = load_profile(config.profile_path)
    except Exception:  # noqa: BLE001 — no profile yet is a normal first run
        candidate = None
    queries: list[str] = []
    where = ""
    if candidate is not None:
        chosen = search_queries_for(candidate)
        queries = chosen.queries
        where = "saved in profile.yaml" if chosen.saved else "derived from your experience"
        if not queries:
            role = _headline_role(candidate)
            queries = [role] if role else []
            where = "from your headline"
    if not queries:
        err_console.print(
            "No query given and nothing in the profile to search for: pass the search terms, "
            "or add experience (or search_queries) to profile.yaml."
        )
        raise typer.Exit(GENERIC_FAILURE)
    picked = queries[: max(1, max_queries)]
    console.print(f"[dim]Queries {where}: {', '.join(picked)}[/dim]")
    if len(queries) > len(picked):
        console.print(f"[dim]{len(queries) - len(picked)} more left out (--max-queries).[/dim]")
    if where == "derived from your experience":
        console.print("[dim]Review and save them: jobbot profile queries --apply[/dim]")
    return picked


def _headline_role(candidate: Candidate) -> str | None:
    headline = (candidate.personal.headline or "").strip()
    if headline:
        return re.split(r"\s*[|/·–—]\s*", headline)[0].strip() or None
    return None


def _unique_postings(found: Sequence[JobPosting]) -> list[JobPosting]:
    """Several queries return the same vacancy; keep the first sighting."""
    seen: set[tuple[str, ...]] = set()
    unique: list[JobPosting] = []
    for job in found:
        if job.source_job_id:
            key: tuple[str, ...] = (job.source, job.source_job_id)
        elif job.url:
            key = (job.url,)
        else:
            key = (job.source, job.title.casefold(), job.company.casefold())
        if key not in seen:
            seen.add(key)
            unique.append(job)
    return unique


def _warn_if_matcher_blind(scores: Sequence[float]) -> None:
    from jobbot.matching.scoring import blind_matcher_warning

    warning = blind_matcher_warning(scores)
    if warning:
        console.print(f"[yellow]{warning}[/yellow]")


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
    fixture: Annotated[
        Path | None,
        typer.Option("--fixture", help="Saved HTML used to recognise an embedded ATS"),
    ] = None,
) -> None:
    """Register a company/portal relation you found yourself (candidate by default)."""
    from jobbot.companies.learn import learn_from_url
    from jobbot.companies.models import DiscoverySource, KnowledgeStatus
    from jobbot.companies.registry import save_companies
    from jobbot.companies.urls import PrivateRouteRejected, company_hint_from_url

    config = load_config()
    registry, path = _companies_registry(config)
    narrator = _narrator()
    narrator.phase(Phase.UPDATING_WORLD, "company career platforms")
    try:
        page = fixture.read_text(encoding="utf-8") if fixture is not None else None
        outcome = learn_from_url(
            registry,
            company=company or company_hint_from_url(url),
            url=url,
            source=DiscoverySource.USER_OBSERVATION,
            country=country,
            resolve=resolve,
            html=page,
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
        if outcome.site.status == KnowledgeStatus.CANDIDATE:
            console.print(
                f"Candidate stored. Confirm with: [bold]jobbot companies promote "
                f"{outcome.company.id} --site {outcome.site.url}[/bold]"
            )
        else:
            console.print(f"Recorded. Status stays {outcome.site.status.value}.")


@companies_app.command("recheck")
def companies_recheck(
    company: Annotated[
        str | None,
        typer.Argument(help="One company id or name; omit to recheck every saved site"),
    ] = None,
    apply_changes: Annotated[
        bool,
        typer.Option("--apply", help="Confirm each detector change before writing"),
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Apply every proposed change")] = False,
) -> None:
    """Re-run offline detectors on saved sites. Dry-run writes nothing."""
    from jobbot.companies.recheck import apply_recheck, plan_recheck
    from jobbot.companies.registry import save_companies

    config = load_config()
    registry, path = _companies_registry(config)
    if company is not None and registry.find_company(company) is None:
        err_console.print(f"[red]No company {company!r} in the registry.[/red]")
        raise typer.Exit(VALIDATION_FAILURE)
    changes = plan_recheck(registry, company=company)
    if not changes:
        console.print("No detector changes.")
        return
    for change in changes:
        console.print(f"{change.company_id}  {change.action}  {change.detail}")
    if not apply_changes:
        console.print("Dry-run only. Re-run with [bold]--apply[/bold] to confirm each change.")
        return
    confirmed = []
    for change in changes:
        if yes or typer.confirm(f"Apply {change.action} on {change.url}?", default=False):
            confirmed.append(change)
    if not confirmed:
        console.print("Nothing applied.")
        return
    apply_recheck(registry, confirmed)
    save_companies(registry, path)
    console.print(f"Applied {len(confirmed)} change(s).")


@companies_app.command("list")
def companies_list(
    status: Annotated[
        str,
        typer.Option("--status", help="candidate | active | stale | rejected | all"),
    ] = "all",
) -> None:
    """List known companies and their career platforms."""
    from jobbot.companies.models import KnowledgeStatus
    from jobbot.companies.urls import display_url
    from jobbot.portals.detect import job_board_host_review

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
    table.add_column("Company", overflow="fold")
    table.add_column("Country")
    table.add_column("Career site", overflow="fold", min_width=24, ratio=3)
    table.add_column("Type", overflow="fold")
    table.add_column("ATS")
    table.add_column("Status")
    table.add_column("Conf.")
    rows = 0
    review_ids: list[str] = []
    for record in registry.companies:
        for site in record.career_sites:
            if wanted is not None and site.status.value not in wanted:
                continue
            review = job_board_host_review(site.url)
            site_type = site.site_type.value if not review else f"{site.site_type.value} · {review}"
            table.add_row(
                record.id,
                record.country or "—",
                display_url(site.url),
                site_type,
                site.ats.value,
                site.status.value,
                str(site.confidence),
            )
            if review and record.id not in review_ids:
                review_ids.append(record.id)
            rows += 1
    if rows == 0:
        console.print(f"No career sites with status {status!r}.")
        return
    console.print(table)
    for company_id in review_ids:
        console.print(f"jobbot companies reject {company_id}")


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


@companies_app.command("recon")
def companies_recon(
    company: Annotated[str, typer.Argument(help="Company id or name already in the registry")],
    apply_changes: Annotated[
        bool,
        typer.Option(
            "--apply",
            help="Write ATS observation + form questions (default: dry-run report)",
        ),
    ] = False,
    fixture: Annotated[
        Path | None,
        typer.Option(
            "--fixture",
            help="Local HTML captured after entering (tests / offline)",
            exists=True,
            dir_okay=False,
            readable=True,
        ),
    ] = None,
    cdp: Annotated[
        str | None,
        typer.Option("--cdp", help="Attach to Chrome; read the open page (HITL login first)"),
    ] = None,
    site_url: Annotated[
        str | None,
        typer.Option("--site", help="Which career site, when the company has several"),
    ] = None,
    navigate: Annotated[
        bool,
        typer.Option(
            "--navigate/--no-navigate",
            help="With --cdp, open the career URL before capturing HTML",
        ),
    ] = True,
) -> None:
    """Learn ATS markers and form questions from a page you entered (issue #45)."""
    from jobbot.companies.recon import ReconError, plan_recon

    config = load_config()
    html: str | None = None
    if fixture is not None:
        html = fixture.read_text(encoding="utf-8")
    elif cdp is not None:
        html = _capture_recon_html(config, company, cdp=cdp, site_url=site_url, navigate=navigate)
    elif apply_changes:
        err_console.print(
            "[red]--apply needs HTML: pass --fixture PATH or --cdp URL "
            "(after you are signed in).[/red]"
        )
        raise typer.Exit(VALIDATION_FAILURE)

    try:
        report = plan_recon(
            config,
            company,
            html=html,
            site_url=site_url,
            apply=apply_changes,
        )
    except ReconError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(VALIDATION_FAILURE) from exc

    table = Table(title=f"Portal recon — {report.company_name}")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("url", report.url)
    table.add_row("ats before", report.previous_ats.value)
    table.add_row("ats detected", report.detected_ats.value)
    table.add_row("evidence", report.evidence or "(none)")
    table.add_row("account", report.account_need.value)
    table.add_row(
        "form",
        (
            f"{report.form_field_count} field(s)"
            if report.form.readable
            else f"unreadable: {report.form.evidence}"
        ),
    )
    table.add_row(
        "wrote",
        f"companies={report.wrote_companies} forms={report.wrote_forms}",
    )
    console.print(table)
    if report.field_labels:
        console.print("Fields: " + ", ".join(report.field_labels[:12]))
        if len(report.field_labels) > 12:
            console.print(f"  … +{len(report.field_labels) - 12} more")
    if report.conflict:
        err_console.print(f"[yellow]Contradiction:[/yellow] {report.conflict}")
    if report.refused:
        err_console.print(f"[yellow]Not stored:[/yellow] {report.refused}")
    console.print(report.hint)
    if not apply_changes:
        console.print(
            "Dry-run. Re-run with [bold]--apply[/bold] plus [bold]--fixture[/bold] or "
            "[bold]--cdp[/bold] to store evidence (#45)."
        )


def _capture_recon_html(
    config: JobbotConfig,
    company: str,
    *,
    cdp: str,
    site_url: str | None,
    navigate: bool,
) -> str:
    """Attach to the user's Chrome and read page HTML (no login automation)."""
    from jobbot.browser.cdp import resolve_cdp_url
    from jobbot.browser.session import BrowserSession
    from jobbot.companies.recon import resolve_recon_site
    from jobbot.companies.registry import default_companies_path, load_companies

    registry = load_companies(default_companies_path(config.root))
    _record, site = resolve_recon_site(registry, company, site_url=site_url)
    cdp_url = resolve_cdp_url(cdp)
    if not cdp_url:
        err_console.print("[red]No CDP URL — pass --cdp or set JOBBOT_CDP_URL[/red]")
        raise typer.Exit(GENERIC_FAILURE)
    with BrowserSession(
        profile_dir=config.root / "browser-data" / "companies-recon-cdp",
        headless=False,
        cdp_url=cdp_url,
        debug_root=config.output_dir / "debug",
    ) as browser:
        page = browser.page
        if navigate:
            page.goto(site.url, wait_until="domcontentloaded")
            console.print(f"Opened {site.url} — sign in / enter if needed, then recon reads HTML.")
        return str(page.content())


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
            help="Fill known fields / open login (stops before password/terms/submit)",
        ),
    ] = False,
    cdp: Annotated[
        str | None,
        typer.Option("--cdp", help="Attach to Chrome via CDP (e.g. http://127.0.0.1:9222)"),
    ] = None,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip the fill confirmation (with --apply)"),
    ] = False,
    job_id: Annotated[
        str | None,
        typer.Option(
            "--job",
            help="Attach job-adapted CV (output/jobs/Jxxxx/cv.pdf); chat-first build, no API key",
        ),
    ] = None,
    issue_gaps: Annotated[
        bool,
        typer.Option(
            "--issue-gaps/--no-issue-gaps",
            help="With --apply, open a GitHub issue for unanswered/new fields (HITL)",
        ),
    ] = False,
) -> None:
    """Sheet of what registering asks; --apply fills or opens login (HITL create).

    Account evidence (page receipt) → login only. Otherwise signup fill from
    profile.yaml + optional job-adapted CV. Unanswered fields are learned gaps
    (issue HITL). Never invents a password or clicks create/submit.
    """
    from jobbot.adapters.getonboard.cv_upload import resolve_base_cv
    from jobbot.companies.models import KnowledgeStatus
    from jobbot.companies.signup import (
        AccountNeed,
        screening_to_prepare,
        signup_sheet,
        signup_target,
    )
    from jobbot.cv.company_apply import (
        company_apply_intent,
        has_receipt_for,
        resolve_job_adapted_cv,
    )
    from jobbot.cv.sync import CompanySyncRow
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
    evidenced = has_receipt_for(config.output_dir, site.url)

    console.print(
        Panel(
            f"[bold]{record.name}[/bold] ({record.id})\n"
            f"{target.url}\n"
            f"ats: {site.ats.value}   account: {target.need.value}\n"
            f"local account evidence: {'yes' if evidenced else 'no'}\n\n{target.note}",
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
        if not apply_fill:
            if open_page:
                from jobbot.adapters.ats.apply import open_ats_in_browser

                open_ats_in_browser(target.url)
                console.print(f"Opened {target.url}")
            return

    if evidenced and not apply_fill:
        console.print(
            "[green]Local account evidence found[/green] — use "
            "[bold]jobbot browser login --apply[/bold] or "
            "[bold]companies signup … --apply[/bold] to open login only."
        )

    if apply_fill:
        cv_path = resolve_base_cv(config.output_dir)
        if job_id:
            adapted = resolve_job_adapted_cv(config.output_dir, job_id)
            if adapted is not None:
                cv_path = adapted
            else:
                console.print(
                    f"[yellow]No adapted CV at output/jobs/{job_id}/cv.pdf[/yellow] — "
                    "adapt in Cursor chat, then "
                    f"[bold]jobbot cv build --job {job_id}[/bold] (chat-first, no API key)."
                )
        row = CompanySyncRow(
            company_id=record.id,
            company_name=record.name,
            url=site.url,
            ats=site.ats,
            need=target.need,
            action="needs_account",
            hint="signup",
            status=KnowledgeStatus.ACTIVE,
            session_evidenced=evidenced,
        )
        intent = company_apply_intent(
            row,
            candidate,
            cv_path=cv_path,
            form=form,
            has_account_evidence=evidenced,
            job_id=job_id,
        )
        console.print(f"\n[bold]Next action:[/bold] {intent.mode} — {intent.note}")
        if intent.mode == "login":
            prompt = "Open login now? (you type the password)"
        else:
            prompt = (
                "Fill known profile fields now? (password, terms, CAPTCHA/2FA and create "
                "stay with you — JobBot does not submit)"
            )
        if not yes and not typer.confirm(prompt, default=False):
            console.print("Skipped. Sheet above still stands.")
            raise typer.Exit(SUCCESS)
        _run_company_fill(
            intent,
            config=config,
            candidate=candidate,
            cdp=cdp,
            ats=site.ats.value,
            open_gap_issue=issue_gaps,
            yes=yes,
        )
        return

    if open_page:
        from jobbot.adapters.ats.apply import open_ats_in_browser

        console.print(open_ats_in_browser(target.url))


@companies_app.command("promote")
def companies_promote(
    company: Annotated[str, typer.Argument(help="Company id or name")],
    site: Annotated[
        str | None,
        typer.Option("--site", help="Promote only this career URL"),
    ] = None,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
) -> None:
    """Promote one company's candidate sites to active."""
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


@companies_app.command("auto-promote")
def companies_auto_promote(
    apply_changes: Annotated[
        bool,
        typer.Option("--apply", help="Mark eligible candidate sites active"),
    ] = False,
) -> None:
    """List candidate sites technical evidence can promote. Dry-run writes nothing."""
    from jobbot.companies.auto_promote import auto_promote_plan
    from jobbot.companies.registry import save_companies

    config = load_config()
    registry, path = _companies_registry(config)
    plan = auto_promote_plan(registry)
    if not plan:
        console.print("Nothing to auto-promote.")
        return
    for record, site in plan:
        console.print(f"{record.id}  {site.url}  {site.ats.value}")
    if not apply_changes:
        console.print("Dry-run only. Re-run with --apply to mark these active.")
        return
    for record, site in plan:
        registry.promote(record.id, url=site.url)
    save_companies(registry, path)
    console.print(f"Promoted {len(plan)} career site(s).")


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
    target = out.expanduser().resolve() if out else generated_candidates_path(config.output_dir)
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
            "No public portal found for: " + ", ".join(report.companies_without_portal[:10])
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
    """Open a Chromium browser (Chrome/Edge/Brave) with CDP for manual challenges.

    Automatically detects and launches any available Chromium-based browser:
    Chrome, Microsoft Edge, Brave, or Chromium.
    """
    from jobbot.browser.background import launch_detached
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
    launch_detached(argv)
    console.print(f"[green]Launched[/green] Chrome with CDP at {url}")
    console.print(background_notice(start_url, where="una ventana nueva de Chrome"))


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
            SessionStatus.WRONG_ACCOUNT: "red",
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


@browser_app.command("login")
def browser_login(
    apply: Annotated[
        bool,
        typer.Option("--apply", help="Open the next portal that still needs you (you sign in)"),
    ] = False,
    port: Annotated[
        int | None,
        typer.Option("--port", help="Debugging port when opening the next portal"),
    ] = None,
) -> None:
    """List permanent, active and candidate portals that still need you to sign in."""
    from jobbot.browser.background import launch_detached
    from jobbot.browser.cdp import chrome_debug_argv
    from jobbot.browser.login_plan import plan_logins
    from jobbot.browser.sessions import ProfileBusyError, SessionStatus, ensure_profile_free

    config = load_config()
    plan = plan_logins(config.root)
    table = Table(title="Login tour")
    table.add_column("Bucket")
    table.add_column("Portal")
    table.add_column("Status")
    table.add_column("Account")
    for row in plan.rows:
        colour = {
            SessionStatus.READY: "green",
            SessionStatus.NEEDS_LOGIN: "yellow",
            SessionStatus.PROFILE_BUSY: "red",
            SessionStatus.WRONG_ACCOUNT: "red",
        }.get(row.status, "white")
        table.add_row(
            row.bucket.value,
            row.name,
            f"[{colour}]{row.status.value}[/{colour}]",
            row.need.value,
        )
    console.print(table)
    for row in plan.rows:
        if row.status is not SessionStatus.READY and row.hint:
            console.print(f"  {row.name}: {row.hint}")

    gap = plan.next_to_open()
    if not apply:
        if gap is None:
            console.print(
                "Nothing left to open. A company host is still unknown until you are signed in."
            )
        else:
            console.print(
                "Dry-run. Re-run with [bold]--apply[/bold] to open the next portal. "
                "You type the password; JobBot never does."
            )
        return
    if gap is None:
        console.print("Nothing left to open.")
        return
    from jobbot.browser.sessions import refuse_to_open

    reason = refuse_to_open(gap.status, gap.evidence)
    if reason:
        err_console.print(f"[red]{reason}[/red]")
        if gap.hint and gap.status is not SessionStatus.WRONG_ACCOUNT:
            err_console.print(gap.hint)
        raise typer.Exit(GENERIC_FAILURE)

    profile_dir = config.root / "browser-data" / gap.profile_name
    profile_dir.mkdir(parents=True, exist_ok=True)
    chosen = port if port is not None else plan.port
    try:
        argv = chrome_debug_argv(profile_dir=profile_dir, port=chosen, start_url=gap.url)
    except FileNotFoundError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(GENERIC_FAILURE) from exc
    try:
        ensure_profile_free(profile_dir)
    except ProfileBusyError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(GENERIC_FAILURE) from exc
    launch_detached(argv)
    console.print(background_notice(gap.url, where="una ventana nueva de Chrome"))
    console.print(
        f"[green]Opened[/green] {gap.name}. Sign in yourself (password, CAPTCHA, 2FA). "
        "Then re-run [bold]jobbot browser login[/bold]."
    )


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


@ops_failure_app.command("work")
def ops_failure_work(
    failure_id: Annotated[str, typer.Argument(help="Failure id, e.g. F0001")],
    apply_changes: Annotated[
        bool,
        typer.Option(
            "--apply",
            help="HITL: create issue if needed, git fetch + checkout -b; never commit/push/PR",
        ),
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
    open_issue: Annotated[
        bool,
        typer.Option(
            "--issue/--no-issue",
            help="With --apply, also run ops failure issue when none is linked",
        ),
    ] = True,
) -> None:
    """Print (or open) the bash maintainer lane: issue → branch → PR → retry (#46)."""
    import subprocess

    from jobbot.ops.failure_work import branch_name, work_script
    from jobbot.ops.failures import get_failure

    session, _ = _session()
    record = get_failure(session, failure_id)
    if record is None:
        err_console.print(f"[red]Unknown failure {failure_id}[/red]")
        raise typer.Exit(GENERIC_FAILURE)

    script = work_script(record)
    console.print(Panel(script, title=f"bash lane · {record.id} → {branch_name(record)}"))

    if not apply_changes:
        console.print(
            "Dry-run (script only). Re-run with [bold]--apply[/bold] to open the lane: "
            "issue (HITL) + [bold]git fetch --all[/bold] + [bold]checkout -b[/bold]. "
            "Commit / push / PR stay bash you run yourself."
        )
        raise typer.Exit(SUCCESS)

    if not yes and not typer.confirm(
        f"Open lane for {record.id} (issue if needed + branch {branch_name(record)})?",
        default=False,
    ):
        console.print("Aborted.")
        raise typer.Exit(SUCCESS)

    if open_issue and not record.issue_url:
        # Reuse the same HITL path as `ops failure issue` (reviews body).
        ops_failure_issue(failure_id, yes=yes)
        record = get_failure(session, failure_id) or record

    def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
        console.print(f"$ {' '.join(argv)}")
        return subprocess.run(argv, check=False, capture_output=True, text=True)  # noqa: S603

    fetch = _run(["git", "fetch", "--all"])
    if fetch.returncode != 0:
        err_console.print(f"[red]git fetch failed:[/red] {fetch.stderr or fetch.stdout}")
        raise typer.Exit(GENERIC_FAILURE)

    base = _run(["git", "checkout", "develop"])
    if base.returncode != 0:
        console.print("[yellow]develop missing — trying main[/yellow]")
        base = _run(["git", "checkout", "main"])
    if base.returncode != 0:
        err_console.print(f"[red]git checkout base failed:[/red] {base.stderr or base.stdout}")
        raise typer.Exit(GENERIC_FAILURE)

    pull = _run(["git", "pull", "--ff-only"])
    if pull.returncode != 0:
        err_console.print(f"[yellow]git pull:[/yellow] {pull.stderr or pull.stdout}")

    name = branch_name(record)
    created = _run(["git", "checkout", "-b", name])
    if created.returncode != 0:
        switched = _run(["git", "checkout", name])
        if switched.returncode != 0:
            err_console.print(f"[red]branch failed:[/red] {created.stderr or created.stdout}")
            raise typer.Exit(GENERIC_FAILURE)
        console.print(f"[dim]branch {name} already existed — checked out[/dim]")

    from jobbot.ops.failure_work import original_command

    console.print(
        f"[green]Lane open[/green] on {name}. Next (bash):\n"
        "  # regression test that fails first, then fix\n"
        "  uv run ruff check . && uv run mypy src && uv run pytest\n"
        '  git add -A && git commit -m "fix: …" && git push -u origin HEAD\n'
        "  gh pr create --fill\n"
        f"  uv run jobbot ops failure triage {record.id} --status fixed\n"
        "  git fetch --all\n"
        f"  {original_command(record)}"
    )


@ops_symptom_app.command("note")
def ops_symptom_note(
    intent: Annotated[
        str,
        typer.Argument(help="What keeps returning in vibecode (will be redacted)"),
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
        typer.Option("--rule", help="Falsifiable rule hypothesis (redacted)"),
    ] = "",
) -> None:
    """Capture a latent requirement. Same fingerprint increments sightings."""
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
    """List latent requirements (symptoms), newest first."""
    from jobbot.ops.symptoms import list_symptoms

    session, _ = _session()
    rows = list_symptoms(session, status=status, area=area, limit=limit)
    if not rows:
        console.print("No symptoms stored.")
        raise typer.Exit(SUCCESS)
    table = Table(title="ops symptoms (latent requirements)")
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
            f"title: {record.title}\n\nintent:\n{record.intent}\n\n"
            f"rule:\n{record.rule_hypothesis or '(none yet)'}\n\n"
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
    """Print the System 2 → System 1 compression plan (does not write code)."""
    from jobbot.ops.symptoms import get_symptom, promote_plan

    session, _ = _session()
    record = get_symptom(session, symptom_id)
    if record is None:
        err_console.print(f"[red]Unknown symptom {symptom_id}[/red]")
        raise typer.Exit(GENERIC_FAILURE)
    console.print(Panel(promote_plan(record), title="compress to System 1"))


@ops_symptom_app.command("triage")
def ops_symptom_triage(
    symptom_id: Annotated[str, typer.Argument(help="Symptom id, e.g. S0001")],
    status: Annotated[
        str,
        typer.Option("--status", help="latent|acknowledged|compressing|resolved|wontfix"),
    ],
    feature: Annotated[
        str | None,
        typer.Option("--feature", help="Path of the compressed feature module"),
    ] = None,
) -> None:
    """Update symptom status after review / compression."""
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
    """Create a GitHub issue from a redacted symptom (HITL; uses gh). Never auto."""
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
        [
            "gh",
            "issue",
            "create",
            "--title",
            title,
            "--body",
            body,
            "--assignee",
            "cursoragent",
        ],
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
    target = (
        out.expanduser().resolve()
        if out
        else (config.output_dir / "recruiters" / "hiring_practice.yaml")
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    listed = payload.get("sources")
    count = len(listed) if isinstance(listed, list) else 0
    console.print(f"[green]Exported[/green] {count} active source(s) → {target}")
