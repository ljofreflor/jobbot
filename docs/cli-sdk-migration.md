# CLI to SDK Migration Guide

This document outlines how JobBot CLI commands can be refactored to use the SDK as a thin wrapper, separating presentation logic from business logic.

## Architecture

### Current Pattern (Direct Implementation)

```python
@app.command()
def search(query: str, remote: bool = False):
    """Search jobs command - direct implementation."""
    # CLI mixes config, session, business logic, and presentation
    config = load_config()
    engine = make_engine(config.database_path)
    session = make_session_factory(engine)()
    
    # Business logic embedded in CLI
    from jobbot.adapters.torre.jobs import TorreJobSource
    source = TorreJobSource(config)
    jobs = source.search_jobs(...)
    
    # Presentation
    console.print(table)
```

### New Pattern (SDK Wrapper)

```python
@app.command()
def search(query: str, remote: bool = False):
    """Search jobs command - SDK wrapper."""
    with JobBotClient() as client:
        # Business logic in SDK
        jobs = client.jobs.search(query, remote=remote)
        
        # CLI handles only presentation
        _display_jobs_table(jobs)
```

## Benefits

1. **Separation of Concerns**: Business logic in SDK, presentation in CLI
2. **Testability**: SDK can be tested independently of CLI
3. **Reusability**: Same logic available for scripts, integrations, notebooks
4. **Maintainability**: Changes to business logic don't require CLI changes
5. **Consistency**: Same configuration/session management everywhere

## Migration Strategy

### Phase 1: New Commands (Completed)

New commands can use SDK immediately:

```python
# src/jobbot/cli.py

@app.command("sdk-search")
def sdk_search_command(
    query: str,
    remote: bool = False,
    limit: int = 10,
) -> int:
    """Search jobs using SDK (demonstration)."""
    try:
        with JobBotClient() as client:
            jobs = client.jobs.search(query, remote=remote, limit=limit)
            matches = client.jobs.match(jobs)
            
            _display_job_matches(jobs, matches)
            return SUCCESS
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        return GENERIC_FAILURE
```

### Phase 2: Gradual Refactoring

Refactor existing commands one at a time:

#### Example: Torre Search

**Before:**
```python
@torre_app.command("search")
def torre_search(query: str, remote: bool = False, limit: int = 10) -> int:
    config = load_config()
    engine = make_engine(config.database_path)
    session_factory = make_session_factory(engine)
    session = session_factory()
    
    from jobbot.adapters.torre.jobs import TorreJobSource
    source = TorreJobSource(config)
    from jobbot.jobs.sources import JobSearchQuery
    search_query = JobSearchQuery(query=query, remote=remote, limit=limit)
    jobs = source.search_jobs(search_query)
    
    # ... 50 lines of presentation logic
    
    return SUCCESS
```

**After:**
```python
@torre_app.command("search")
def torre_search(query: str, remote: bool = False, limit: int = 10) -> int:
    with JobBotClient() as client:
        jobs = client.jobs.search(query, source="torre", remote=remote, limit=limit)
        matches = client.jobs.match(jobs)
        _display_torre_results(jobs, matches)
        return SUCCESS
```

#### Example: CV Build

**Before:**
```python
@cv_app.command("build")
def build_cv(job_id: str | None = None, style: str = "modern") -> int:
    config = load_config()
    candidate = load_profile(config.profile_path)
    
    job = None
    if job_id:
        engine = make_engine(config.database_path)
        session = make_session_factory(engine)()
        repo = JobRepository(session)
        job = repo.get(job_id)
    
    cv_style = CvStyle[style.upper()]
    result = build_cv(candidate, job, config, cv_style, ...)
    console.print(f"CV built: {result.pdf_path}")
    return SUCCESS
```

**After:**
```python
@cv_app.command("build")
def build_cv_command(job_id: str | None = None, style: str = "modern") -> int:
    with JobBotClient() as client:
        if job_id:
            cv_path = client.cv.build_for_job_id(job_id, style=style)
        else:
            cv_path = client.cv.build(style=style)
        
        console.print(f"CV built: {cv_path}")
        return SUCCESS
```

## Demonstration Command

A proof-of-concept command has been added to demonstrate the pattern:

```bash
# Use SDK-based command
jobbot sdk-demo search "python developer" --remote --limit 5

# Build CV using SDK
jobbot sdk-demo cv J0001 --style modern
```

See implementation in `src/jobbot/cli_sdk_demo.py`.

## Presentation Helpers

Extract common presentation logic to helpers:

```python
# src/jobbot/cli_helpers.py

def display_job_table(jobs: list[JobPosting], matches: list[JobMatch] | None = None):
    """Display jobs in a formatted table."""
    table = Table(title="Jobs")
    table.add_column("ID")
    table.add_column("Company")
    table.add_column("Title")
    table.add_column("Location")
    if matches:
        table.add_column("Match %")
    
    for i, job in enumerate(jobs):
        row = [job.id, job.company, job.title, job.location or "-"]
        if matches:
            row.append(f"{matches[i].score}%")
        table.add_row(*row)
    
    console.print(table)

def display_match_details(job: JobPosting, match: JobMatch):
    """Display detailed match analysis."""
    console.print(Panel(
        f"[bold]{job.company} - {job.title}[/bold]\n"
        f"Match Score: {match.score}%\n"
        f"Highlights: {', '.join(match.highlights)}\n"
        f"Gaps: {', '.join(match.gaps)}",
        title="Match Analysis"
    ))
```

## Migration Checklist

For each command:

- [ ] Identify business logic (data operations)
- [ ] Identify presentation logic (console output, tables, etc.)
- [ ] Check if SDK API exists for business logic
  - If not, extend SDK first
- [ ] Refactor command to use SDK
- [ ] Extract presentation logic to helper
- [ ] Test command works identically
- [ ] Update command tests to use SDK

## Commands by Priority

### High Priority (Frequently Used)
1. `jobbot jobs search` → `client.jobs.search()`
2. `jobbot cv build` → `client.cv.build()`
3. `jobbot jobs match` → `client.jobs.match()`
4. `jobbot torre search` → `client.jobs.search(source="torre")`

### Medium Priority
5. `jobbot jobs get` → `client.jobs.get()`
6. `jobbot jobs list` → `client.jobs.list_all()`
7. Profile sync commands (extend SDK first)

### Low Priority
8. Browser/manual flow commands (may not need SDK)
9. Admin/maintenance commands

## Testing Strategy

1. **SDK Tests**: Test business logic via SDK directly
2. **CLI Tests**: Test presentation and argument parsing only
3. **Integration Tests**: Full end-to-end with CLI + SDK

Example:

```python
# Test SDK (business logic)
def test_search_jobs_sdk():
    client = JobBotClient()
    jobs = client.jobs.search("python", remote=True)
    assert len(jobs) > 0

# Test CLI (presentation)
def test_search_command_output(capsys):
    result = runner.invoke(app, ["search", "python", "--remote"])
    assert result.exit_code == 0
    output = capsys.readouterr().out
    assert "Jobs" in output  # Table title
```

## Backward Compatibility

During migration:

1. Keep old command implementations
2. Add new SDK-based commands with different names
3. Mark old commands as deprecated
4. After testing period, replace implementations
5. Maintain same CLI interface (arguments, output format)

## Next Steps

1. ✅ Create SDK package
2. ✅ Implement core APIs (Jobs, CV)
3. ✅ Add demonstration command
4. ⏳ Refactor high-priority commands
5. ⏳ Extract presentation helpers
6. ⏳ Update tests
7. ⏳ Extend SDK for remaining commands

## Example: Complete Command Migration

See `src/jobbot/cli_sdk_demo.py` for a complete working example of an SDK-based CLI command.
