# JobBot SDK Documentation

The JobBot SDK provides programmatic access to JobBot functionality without depending on CLI internals. Use it to integrate job search, matching, and CV building into your own applications.

## Installation

The SDK is part of the `jobbot` package:

```bash
pip install -e .  # From source
```

## Quick Start

```python
from jobbot.sdk import JobBotClient

# Initialize client (auto-discovers workspace)
client = JobBotClient()

# Search for jobs
jobs = client.jobs.search("python developer", source="torre", remote=True, limit=5)

# Match against profile
matches = client.jobs.match(jobs)

# Build tailored CV
for job, match in zip(jobs, matches):
    if match.score >= 70:
        cv_path = client.cv.build(
            job=job,
            style="modern",
            output_path=f"cv_{job.company.replace(' ', '_')}.pdf"
        )
        print(f"Built CV: {cv_path} (match: {match.score}%)")

# Clean up
client.close()
```

## JobBotClient

The main entry point for all SDK operations.

### Initialization

```python
from pathlib import Path
from jobbot.sdk import JobBotClient

# Auto-discover workspace from current directory
client = JobBotClient()

# Specify workspace explicitly
client = JobBotClient(workspace_root="/path/to/workspace")

# Use custom config file
client = JobBotClient(config_path="/path/to/jobbot.toml")
```

### Context Manager

The client supports the context manager protocol for automatic cleanup:

```python
with JobBotClient() as client:
    jobs = client.jobs.search("data scientist", remote=True)
    # ... work with jobs
# Automatically closes connections
```

## Jobs API

Access job search, retrieval, and matching functionality.

### Search Jobs

```python
# Search Torre (LATAM/remote jobs)
jobs = client.jobs.search(
    "backend developer",
    source="torre",
    remote=True,
    limit=20
)

# Filter and explore
for job in jobs:
    print(f"{job.id}: {job.company} - {job.title}")
    print(f"  Location: {job.location}")
    print(f"  Remote: {job.remote_type}")
```

### Retrieve Jobs

```python
# Get job by ID
job = client.jobs.get("J0001")

if job:
    print(f"Company: {job.company}")
    print(f"Title: {job.title}")
    print(f"Skills: {', '.join(job.skills or [])}")

# List all stored jobs
all_jobs = client.jobs.list_all(limit=50)
```

### Match Jobs

```python
# Match single job
job = client.jobs.get("J0001")
match = client.jobs.match(job)

print(f"Match score: {match.score}%")
print(f"Highlights: {match.highlights}")
print(f"Gaps: {match.gaps}")

# Match multiple jobs
jobs = client.jobs.search("python", remote=True)
matches = client.jobs.match(jobs)

# Sort by score
sorted_matches = sorted(zip(jobs, matches), key=lambda x: x[1].score, reverse=True)

for job, match in sorted_matches[:5]:
    print(f"{job.company} - {job.title}: {match.score}%")

# Match by ID
match = client.jobs.match_by_id("J0001")
```

## CV API

Build tailored CVs for job applications.

### Build CV

```python
# Build generic CV
cv_path = client.cv.build(style="modern")

# Build tailored CV for specific job
job = client.jobs.get("J0001")
cv_path = client.cv.build(
    job=job,
    style="ats-optimized",
    output_path="cv_acme_corp.pdf"
)

# Build from job ID
cv_path = client.cv.build_for_job_id(
    "J0001",
    style="classic",
    output_path="cv_custom.pdf"
)
```

### Available Styles

```python
# List available styles
styles = client.cv.list_styles()
print(f"Available styles: {', '.join(styles)}")

# Typical styles:
# - "modern": Clean, contemporary design
# - "classic": Traditional, formal layout
# - "ats-optimized": Optimized for applicant tracking systems
```

## Complete Example: Automated Job Application Flow

```python
from jobbot.sdk import JobBotClient

def main():
    with JobBotClient() as client:
        # 1. Search for relevant jobs
        print("Searching for jobs...")
        jobs = client.jobs.search(
            "senior python developer",
            source="torre",
            remote=True,
            limit=20
        )
        print(f"Found {len(jobs)} jobs")

        # 2. Match against profile
        print("Matching jobs against profile...")
        matches = client.jobs.match(jobs)

        # 3. Filter high-quality matches
        strong_matches = [
            (job, match)
            for job, match in zip(jobs, matches)
            if match.score >= 70  # At least 70% match
        ]
        print(f"Found {len(strong_matches)} strong matches")

        # 4. Build tailored CVs
        for job, match in strong_matches[:5]:  # Top 5 matches
            print(f"\nBuilding CV for {job.company} - {job.title}")
            print(f"  Match score: {match.score}%")
            
            cv_path = client.cv.build(
                job=job,
                style="ats-optimized",
                output_path=f"cvs/cv_{job.company.replace(' ', '_')}.pdf"
            )
            print(f"  CV saved: {cv_path}")

if __name__ == "__main__":
    main()
```

## Error Handling

```python
from jobbot.sdk import JobBotClient

try:
    client = JobBotClient(workspace_root="/nonexistent")
except FileNotFoundError as e:
    print(f"Workspace not found: {e}")

try:
    jobs = client.jobs.search("python", source="unsupported")
except ValueError as e:
    print(f"Invalid source: {e}")

try:
    cv_path = client.cv.build(style="invalid-style")
except ValueError as e:
    print(f"Invalid style: {e}")
```

## Configuration

The SDK respects JobBot configuration from `jobbot.toml`:

```toml
[profile]
path = "data/profile.yaml"

[paths]
templates = "templates/"
output = "output/"

[database]
path = "data/jobbot.db"
```

Access configuration programmatically:

```python
client = JobBotClient()
print(f"Profile path: {client.config.profile_path}")
print(f"Database path: {client.config.database_path}")
print(f"Templates: {client.config.paths.templates}")
```

## Advanced Usage

### Custom Session Management

```python
from jobbot.sdk import JobBotClient

client = JobBotClient()

# Access database session factory
session = client.jobs._session_factory()

try:
    # Custom database operations
    from jobbot.jobs.repository import JobRepository
    repo = JobRepository(session)
    jobs = repo.list_all()
finally:
    session.close()
```

### Direct API Access

```python
from jobbot.sdk.jobs_api import JobsApi
from jobbot.sdk.cv_api import CvApi
from jobbot.config import JobbotConfig
from jobbot.profile.loader import load_profile
from jobbot.db.engine import make_engine, make_session_factory

# Manual setup
config = JobbotConfig()
engine = make_engine(config.database_path)
session_factory = make_session_factory(engine)
candidate = load_profile(config.profile_path)

# Create APIs directly
jobs_api = JobsApi(config, session_factory, candidate)
cv_api = CvApi(config, candidate)

# Use APIs
jobs = jobs_api.search("python", source="torre")
cv_path = cv_api.build(job=jobs[0])
```

## Best Practices

1. **Use context manager** for automatic resource cleanup:
   ```python
   with JobBotClient() as client:
       # work with client
   ```

2. **Filter matches** before building CVs:
   ```python
   matches = client.jobs.match(jobs)
   good_matches = [j for j, m in zip(jobs, matches) if m.score >= 70]
   ```

3. **Handle errors gracefully**:
   ```python
   job = client.jobs.get("J0001")
   if job is None:
       print("Job not found")
   ```

4. **Batch operations** when possible:
   ```python
   # Match multiple jobs at once
   matches = client.jobs.match(jobs)
   # Instead of:
   # matches = [client.jobs.match(job) for job in jobs]
   ```

## API Reference Summary

### JobBotClient

- `__init__(config_path=None, workspace_root=None)`: Initialize client
- `jobs`: Jobs API namespace
- `cv`: CV API namespace  
- `close()`: Close connections
- `__enter__()/__exit__()`: Context manager support

### JobsApi

- `search(query, source="torre", remote=False, limit=10)`: Search jobs
- `get(job_id)`: Get job by ID
- `list_all(limit=None)`: List all stored jobs
- `match(jobs)`: Match job(s) against profile
- `match_by_id(job_id)`: Match stored job by ID

### CvApi

- `build(job=None, style="modern", output_path=None, target=LOCAL_REVIEW)`: Build CV
- `build_for_job_id(job_id, style="modern", output_path=None)`: Build CV for stored job
- `list_styles()`: List available CV styles

## Support

For issues or questions:
- Check the [main documentation](README.md)
- Review [CLI documentation](AGENTS.md) for feature details
- Examine the [architecture docs](architecture-di.md) for design patterns
