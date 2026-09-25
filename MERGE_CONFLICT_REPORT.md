# Merge Conflict Report: cursor/companies-recon-1023 ← develop

**Date**: 2026-09-24  
**Base**: `df8983bd1cf7dddbf951d33038ec693fa3da78a0`  
**Branch**: `cursor/companies-recon-1023` (1d231b2)  
**Target**: `origin/develop` (e117fb0)

## Summary

**6 files with conflicts**:
- ✅ **2 simple conflicts** - Fixed automatically
- ⚠️ **4 complicated conflicts** - Require human review

## ✅ Simple Conflicts (RESOLVED)

### 1. `src/jobbot/adapters/ats/registry.py`

**Type**: Dictionary addition conflict  
**Cause**: Both branches add different ATS adapters to the same registry

**Conflict**:
```python
_ADAPTERS: dict[AtsKind, ApplicationPortalAdapter] = {
    AtsKind.GREENHOUSE: GreenhouseAdapter(),
    AtsKind.LEVER: LeverAdapter(),
    AtsKind.ASHBY: AshbyAdapter(),
    AtsKind.GETONBOARD: GetOnBoardAdapter(),
    AtsKind.WORKDAY: WorkdayAdapter(),
<<<<<<< HEAD (our branch)
    AtsKind.TORRE: TorreApplicationAdapter(),
=======
    AtsKind.INDEED: IndeedApplyAdapter(),
>>>>>>> origin/develop
}
```

**Resolution**: Keep both adapters
```python
_ADAPTERS: dict[AtsKind, ApplicationPortalAdapter] = {
    AtsKind.GREENHOUSE: GreenhouseAdapter(),
    AtsKind.LEVER: LeverAdapter(),
    AtsKind.ASHBY: AshbyAdapter(),
    AtsKind.GETONBOARD: GetOnBoardAdapter(),
    AtsKind.WORKDAY: WorkdayAdapter(),
    AtsKind.INDEED: IndeedApplyAdapter(),  # From develop
    AtsKind.TORRE: TorreApplicationAdapter(),  # From our branch
}
```

**Status**: ✅ Fixed

---

### 2. `docs/capabilities.md`

**Type**: Documentation statistics update  
**Cause**: Different counts after independent feature additions

**Conflict**:
```markdown
<<<<<<< HEAD
80 commands, 110 modules, 499 public symbols.
=======
87 commands, 124 modules, 582 public symbols.
>>>>>>> origin/develop
```

**Resolution**: Take develop version (includes both feature sets)
- `87 commands` (includes Torre + other develop features)
- `124 modules` (includes SDK + develop modules)
- `582 public symbols` (comprehensive count)

Also includes corrected description:
```markdown
- `jobbot companies recon` — Learn ATS markers and form questions from a page you entered (issue #45).
```

**Status**: ✅ Fixed

---

## ⚠️ Complicated Conflicts (REQUIRE HUMAN REVIEW)

### 3. `src/jobbot/cli.py` - `companies_recon` command

**Type**: Conflicting CLI implementations  
**Impact**: User-facing command interface differs

**Our Branch** (cursor/companies-recon-1023):
```python
@companies_app.command("recon")
def companies_recon(
    company: str,  # Required argument
    fixture: Path | None = None,  # --fixture option
    cdp: str | None = None,  # --cdp option
    apply: bool = False,  # --apply flag
) -> None:
    """Learn ATS and form questions by reading a page the human is already on (HITL).
    
    Uses: recon_from_fixture() or recon_from_html()
    Returns: ReconResult
    """
```

**Develop Branch**:
```python
@companies_app.command("recon")
def companies_recon(
    url: str,  # URL argument (different!)
    apply: bool = False,  # --apply flag
    cdp: str | None = None,  # --cdp option  
) -> None:
    """Learn portal truth from a page you are already on (issue #45).
    
    Uses: plan_recon() and resolve_recon_site()
    Returns: ReconReport
    """
```

**Key Differences**:
1. **Argument**: `company` vs `url` - fundamentally different user interface
2. **Options**: Our branch has `--fixture` for offline testing
3. **Return type**: `ReconResult` vs `ReconReport`
4. **Implementation**: Different function calls and logic flow

**Why Complicated**: 
- Different user experience (how the command is invoked)
- Different underlying data models
- Cannot mechanically merge without understanding intended UX

---

### 4. `src/jobbot/companies/recon.py`

**Type**: Completely different module implementations  
**Impact**: Core business logic differs

**Our Branch** (326 lines):
```python
@dataclass(frozen=True)
class ReconResult:
    """What recon learned from the page the human is on."""
    company_id: str
    url: str
    ats: AtsKind
    ats_evidence: str
    form: FormKnowledge
    observation_written: bool = False
    form_written: bool = False

def recon_from_html(
    html: str,
    *,
    url: str,
    company: str,
    company_id: str | None = None,
) -> ReconResult:
    """Learn ATS and form questions from HTML. Pure: no network, no writes."""
    
def recon_from_fixture(
    fixture: Path,
    *,
    url: str,
    company: str,
    company_id: str | None = None,
) -> ReconResult:
    """Learn from a saved HTML fixture (offline testing)."""
    
def make_observation(
    result: ReconResult,
    status: KnowledgeStatus = KnowledgeStatus.CANDIDATE,
) -> Observation:
    """Convert ReconResult to Observation for registry."""
```

**Develop Branch** (238 lines):
```python
@dataclass(frozen=True)
class ReconReport:
    """What recon saw, and whether anything was persisted."""
    company_id: str
    company_name: str
    url: str
    previous_ats: AtsKind  # NEW: Tracks what was known before
    detected_ats: AtsKind
    evidence: str
    account_need: AccountNeed  # NEW: Integration with signup
    form: FormKnowledge
    applied: bool
    observation_updated: bool  # Different field name
    form_updated: bool  # Different field name

@dataclass(frozen=True)
class ReconError:
    """Recon failure modes."""
    company_id: str
    url: str
    reason: str

def resolve_recon_site(
    config: JobbotConfig,
    url: str,
) -> tuple[CompanyRecord, CareerSite]:
    """Find the company and site for this URL."""
    
def recon_from_html(
    config: JobbotConfig,
    url: str,
    html: str,
    *,
    apply: bool = False,
) -> ReconReport | ReconError:
    """Learn portal evidence from HTML (integrated with registry)."""
    
def plan_recon(
    registry: CompanyRegistry,
    url: str,
) -> tuple[CompanyRecord, CareerSite, AccountNeed]:
    """Plan what recon needs for this URL."""
```

**Key Differences**:

| Aspect | Our Branch | Develop |
|--------|------------|---------|
| **Data Model** | `ReconResult` (7 fields) | `ReconReport` (11 fields) + `ReconError` |
| **State Tracking** | Simple flags | Tracks previous state + changes |
| **Integration** | Separate observation creation | Integrated with registry + signup |
| **Error Handling** | Exceptions | Result type (`ReconReport \| ReconError`) |
| **Configuration** | Passed per-call | Uses `JobbotConfig` throughout |
| **Testing Support** | `recon_from_fixture()` for offline | No fixture support |
| **API Style** | Pure functions | Integrated with config/registry |

**Why Complicated**:
- Fundamentally different architectures
- Different error handling strategies
- Different integration patterns
- Cannot merge without choosing a design philosophy

---

### 5. `tests/unit/test_companies_recon.py`

**Type**: Test suite for conflicting implementations

**Our Branch**: Tests `ReconResult`-based API
- `test_recon_from_html_detects_greenhouse()`
- `test_recon_from_html_extracts_form_fields()`
- `test_recon_from_fixture_reads_saved_html()`
- `test_make_observation_creates_candidate_observation()`
- Tests pure functions with explicit parameters

**Develop Branch**: Tests `ReconReport`-based API
- `test_recon_finds_site_from_url()`
- `test_recon_updates_ats_when_evidence_found()`
- `test_recon_returns_error_when_url_unknown()`
- Tests integrated functions using `JobbotConfig`

**Why Complicated**: Tests depend on module implementation choice

---

### 6. `tests/unit/test_companies_recon_cli.py`

**Type**: CLI test suite for conflicting implementations

**Our Branch**: Tests CLI with `company` argument + `--fixture` option  
**Develop Branch**: Tests CLI with `url` argument

**Why Complicated**: CLI tests depend on CLI implementation choice

---

## Architecture Comparison

### Our Branch Philosophy
- **Pure functions**: Minimal dependencies, explicit parameters
- **Separation**: Observation creation separate from recon logic
- **Testing**: Offline fixture support for tests
- **Data model**: Simple `ReconResult` with basic tracking

### Develop Philosophy  
- **Integration**: Tight coupling with config/registry/signup
- **Result types**: Explicit success/error types (`ReconReport | ReconError`)
- **State tracking**: Tracks previous state and changes
- **Registry-first**: Resolves companies/sites before processing

---

## Recommendation

### Immediate Action
1. ✅ Merge with simple conflicts resolved
2. ⚠️ **DO NOT auto-resolve complicated conflicts**

### Required Discussion Points

**For Product Owner / Tech Lead**:

1. **CLI Interface**: Which command signature should we keep?
   - `jobbot companies recon <company>` (our branch)
   - `jobbot companies recon <url>` (develop)

2. **Architecture**: Which design philosophy?
   - Pure functions with explicit params (our branch)
   - Integrated with config/registry (develop)

3. **Testing Strategy**: 
   - Keep fixture support for offline testing? (our branch)
   - Or rely on integrated tests? (develop)

4. **Error Handling**:
   - Exceptions (our branch)
   - Result types with explicit errors (develop)

5. **Feature Merge**: Can we combine strengths?
   - Fixture testing from our branch
   - Previous state tracking from develop
   - Result types from develop
   - Pure function style from our branch

---

## Next Steps

1. **Create merge branch**: `git checkout -b merge/develop-into-recon`
2. **Apply simple fixes**: Already identified above
3. **Schedule design review**: For complicated conflicts
4. **Decide on architecture**: Choose one or hybrid approach
5. **Implement chosen design**: Whichever is selected
6. **Update tests**: Match chosen implementation
7. **Verify**: Ensure all tests pass

---

## Files to Review

### Require Human Decision
- [ ] `src/jobbot/cli.py` (CLI interface)
- [ ] `src/jobbot/companies/recon.py` (core logic)
- [ ] `tests/unit/test_companies_recon.py` (tests)
- [ ] `tests/unit/test_companies_recon_cli.py` (CLI tests)

### Auto-Resolved
- [x] `src/jobbot/adapters/ats/registry.py` ✅
- [x] `docs/capabilities.md` ✅

---

**Prepared by**: Cloud Agent  
**Merge attempt**: Aborted after analysis  
**Branch state**: Clean (no merge in progress)
