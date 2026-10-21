---
title: UML — dominio y puertos
description: Diagramas Mermaid del SDD. Cada issue de dominio debe nombrar qué diagrama toca.
---

# UML — dominio y puertos

Fuente canónica de los diagramas del [software design](software-design.md).
Los PRs que añaden un tipo de dominio o un puerto **actualizan este archivo**
(o fallan el criterio de aceptación del issue).

Convención: cada diagrama tiene un ancla (`{#id}`). Los issues citan
`docs/uml.md#id`.

## Dominio actual — aggregate `Candidate` {#candidate-now}

```mermaid
classDiagram
  direction TB
  class Candidate {
    +PersonalInfo personal
    +str|None summary
    +list~str~ specialties
    +list~str~ search_queries
    +list~Experience~ experience
    +list~Education~ education
    +SkillGroups skills
    +list~Publication~ publications
    +list~Project~ projects
    +achievement_count() int
  }
  class PersonalInfo {
    +str name
    +str headline
    +str|None city
    +str|None country
    +EmailStr|None email
  }
  class Experience {
    +str id
    +str company
    +str title
    +str start_date
    +str|None end_date
    +bool current
    +list~Achievement~ achievements
  }
  class Achievement {
    +str id
    +str text
    +list~str~ tags
    +dict metrics
  }
  class Education {
    +str id
    +str institution
    +str degree
  }
  class SkillGroups {
    +dict root
  }
  class JobPosting {
    +str id
    +str title
    +str company
    +str description
    +list~str~ requirements
    +list~str~ skills
    +str|None ats_kind
    +float|None match_score
  }
  class Application {
    +str id
    +str job_id
    +ApplicationStatus status
    +str|None package_dir
  }
  Candidate *-- PersonalInfo
  Candidate *-- Experience
  Candidate *-- Education
  Candidate *-- SkillGroups
  Experience *-- Achievement
  Application --> JobPosting : job_id
```

## Target — hechos vs preferencias + evidencia {#fact-preference}

Patrones: **Aggregate Root**, **Value Object**, asociación skills↔roles.
Issues: #141 #144 #185 #195 #206 #221.

```mermaid
classDiagram
  direction TB
  class Candidate {
    <<Fact aggregate>>
    +PersonalInfo personal
    +list~Experience~ experience
    +list~Education~ education
    +list~LanguageSkill~ languages
    +list~Certification~ certifications
    +list~SkillUse~ skill_uses
  }
  class ApplicationPreferences {
    <<Preference aggregate>>
    +work_auth
    +relocation
    +salary_expectation
    +answers
  }
  class LanguageSkill {
    <<Value Object>>
    +str name
    +CEFR|native level
    +str|None evidence
  }
  class Education {
    +EducationStatus status
    +YearMonth|None expected_end
  }
  class Experience {
    +str company
    +str|None unit
    +WorkMode|None work_mode
  }
  class SkillUse {
    +str skill
    +str experience_id
    +EvidenceStrength strength
  }
  class EvidenceStrength {
    <<Enumeration>>
    claim
    experience
    evidence
    assessed
  }
  class Requirement {
    <<Value Object>>
    +must|want kind
    +str text
    +str|None source_span
  }
  class JobPosting {
    +list~Requirement~ requirements_typed
    +PostingClarity clarity
    +datetime|None closes_at
    +str|None closes_timezone
  }
  class ProfileOverlay {
    <<Projection>>
    +str lang
    +dict by_id
    +source_hash per entry
  }
  Candidate ..> ApplicationPreferences : used with
  Candidate ..> ProfileOverlay : composed with
  Candidate *-- LanguageSkill
  Candidate *-- SkillUse
  Candidate *-- Experience
  Candidate *-- Education
  JobPosting *-- Requirement
  SkillUse --> EvidenceStrength
```

## Puertos y adapters (hexagonal) {#ports}

Patrones: **Port/Adapter**, **Factory**, **Strategy**, **Registry**.

```mermaid
classDiagram
  direction LR
  class Candidate
  class JobPosting
  class JobSourceAdapter {
    <<Protocol>>
    +search_jobs()
    +get_job()
  }
  class ApplicationPortalAdapter {
    <<Protocol>>
    +detect()
    +prefill()
    +attach_cv()
  }
  class ProfileAdapter {
    <<Protocol>>
    +pull()
    +diff()
  }
  class WritableProfileAdapter {
    <<Protocol>>
    +sync_plan()
    +apply()
  }
  class RuleBasedJobAnalyzer {
    +analyze(Candidate, JobPosting) JobMatch
  }
  class SourceChannel {
    <<Registry entry>>
    +str id
    +evidence
    +capabilities
  }
  class CvPresentationVariant {
    <<Strategy choice>>
    +str name
    +list match_terms
  }
  JobSourceAdapter ..> JobPosting : produces
  ApplicationPortalAdapter ..> Candidate : reads
  ProfileAdapter ..> Candidate : diffs
  WritableProfileAdapter --|> ProfileAdapter
  RuleBasedJobAnalyzer ..> Candidate : reads
  RuleBasedJobAnalyzer ..> JobPosting : reads
  SourceChannel ..> JobSourceAdapter : selects
  CvPresentationVariant ..> Candidate : presentation only
```

## Plan-then-apply (Command) {#plan-apply}

Patrón: **Template Method** / **Command** con dry-run default.

```mermaid
sequenceDiagram
  participant CLI
  participant Plan as SyncPlan / PrefillPlan / AdvisePlan
  participant Port as Adapter port
  participant Human
  CLI->>Plan: build (facts only)
  CLI->>CLI: print dry-run
  alt --apply + confirm
    CLI->>Human: HITL confirm
    Human-->>CLI: yes
    CLI->>Port: execute plan
  else default
    CLI-->>CLI: no write
  end
```

## Specification — condiciones / elegibilidad {#specification}

Patrones: **Specification**, **Result object**. Issues: #166 #186.

```mermaid
classDiagram
  direction TB
  class ConditionSpec {
    <<Specification>>
    +is_satisfied_by(Candidate, Preferences, JobPosting) Verdict
  }
  class Verdict {
    +ok|ask|block status
    +str evidence
    +str|None question
  }
  class PostingClarity {
    +float coverage
    +bool usable_for_pj_fit
  }
  ConditionSpec --> Verdict
  ConditionSpec ..> PostingClarity : reads
```

## Anti-corruption — homologación portal → perfil {#acl}

Patrón: **Anti-Corruption Layer**. Issue: #94.

```mermaid
flowchart LR
  Portal[Portal field label] --> ACL[Homologation table exact]
  ACL -->|alias| Path[Profile path]
  ACL -->|none| Empty[leave blank needs_human]
  Path --> Candidate
```

## HITL pause — desafío / CAPTCHA (sin bypass) {#hitl-pause}

Patrones: **Guard** (TTY), **Template Method** (`pause_for_manual`). Issue: #392.

```mermaid
sequenceDiagram
  participant Adapter as Indeed JobSource
  participant Session as BrowserSession
  participant Human
  Adapter->>Session: pause_for_manual(is_clear, 300s)
  alt stdin is TTY
    Session->>Human: Enter / poll until clear
    Human-->>Session: cleared or timeout
    Session-->>Adapter: True | False
  else no TTY (agent / pipe)
    Note over Session: no 300s wait (#392)
    Session-->>Adapter: False (fail fast)
    Adapter-->>Adapter: exit 4 + ops failure
  end
```

Reglas: nunca resolver CAPTCHA; nunca informar el desafío como lista vacía (#184); sin TTY no se bloquea el proceso 5 minutos.

## Search outcome — vacío ≠ falla ≠ off-topic {#search-outcome}

Patrones: **Result object**, **discriminated union**. Issues: #390 #176 #184.

```mermaid
classDiagram
  direction TB
  class JobSourceAdapter {
    <<Protocol>>
    +search_jobs(JobSearchQuery) list~JobPosting~
  }
  class SearchOutcome {
    <<Result>>
    +ok|source_failed|off_topic|challenge kind
    +list~JobPosting~ jobs
    +str|None detail
  }
  class TorreJobSource
  class GetOnBoardJobSource
  JobSourceAdapter <|.. TorreJobSource
  JobSourceAdapter <|.. GetOnBoardJobSource
  TorreJobSource ..> SearchOutcome : HTTP 400 → source_failed
  GetOnBoardJobSource ..> SearchOutcome : title≠query → off_topic
  note for SearchOutcome "empty ok ≠ source_failed\nnever CAPTCHA solve"
```

```mermaid
flowchart TD
  Q[search_jobs query] --> R{HTTP / page}
  R -->|200 + relevant rows| Ok[kind ok]
  R -->|200 + empty| Empty[kind ok jobs empty]
  R -->|4xx/5xx / down| Fail[kind source_failed]
  R -->|rows other trade| Off[kind off_topic]
  R -->|challenge page| Ch[kind challenge one pass]
  Fail --> Msg[print failure not No jobs found]
  Empty --> MsgOk[may print No jobs found]
```

## Posting URL verify — ficha vs SERP {#posting-url-verify}

Patrones: **Specification**, **Value Object** (evidencia de URL). Issue: #388 (#182 id-only, #215 Workday).

```mermaid
classDiagram
  direction TB
  class PostingUrlCheck {
    <<Value Object>>
    +str final_url
    +str url_status
    +datetime url_checked_at
    +str|None title
    +str|None employer
  }
  class verify_posting_url {
    <<Specification>>
    +check(html, url) PostingUrlCheck|Reject
  }
  class JobRepository {
    +upsert(JobPosting)
  }
  verify_posting_url --> PostingUrlCheck
  PostingUrlCheck --> JobRepository : only detail + open
```

```mermaid
flowchart TD
  U[jobs add --url / jobs verify] --> F{fixture or fetcher}
  F -->|no reader| Ask[ask --file; no network]
  F -->|HTML| V[verify_posting_url]
  V -->|SERP / home / closed| Reject[do not upsert]
  V -->|detail title+employer| Save[upsert + final_url + checked_at]
```

## LinkedIn details pull — sección a sección {#linkedin-details-pull}

Patrones: **ProfileAdapter** (pull), **Result** por sección. Issue: #386 (#194 snapshot vacío).

```mermaid
classDiagram
  direction TB
  class ProfileAdapter {
    <<Protocol>>
    +pull() Snapshot
  }
  class SectionRead {
    <<Result>>
    +ok|empty|unread status
    +list blocks
  }
  class LinkedInProfileAdapter {
    +pull_details(section) SectionRead
  }
  ProfileAdapter <|.. LinkedInProfileAdapter
  LinkedInProfileAdapter --> SectionRead
  note for SectionRead "empty = portal says nothing\nunread = fetch/parse failed\nnever invent facts"
```

```mermaid
flowchart LR
  P["/in/slug/"] --> H[headline block]
  P --> D["/details/experience|education|…/"]
  D -->|blocks in main| Ok[status ok]
  D -->|No hay nada…| Empty[status empty]
  D -->|missing / error| Unread[status unread]
```

## JD LLM extract — anclado al texto {#jd-llm-extract}

Patrones: **Optional LLM** (`nlp/gateway`) + **Validator** (grounding). Issue: #384 (#85 chrome).

```mermaid
sequenceDiagram
  participant CLI as jobs add --file --llm
  participant Det as Deterministic parser
  participant GW as run_optional_llm
  participant Val as Grounding validator
  CLI->>Det: parse JD text
  alt no OPENAI_API_KEY
    CLI-->>CLI: keep Det (no network)
  else key present
    CLI->>GW: redacted JD text only
    GW-->>Val: proposed fields
    alt every field substring of JD
      Val-->>CLI: accept → JobPosting
    else invents employer/skill
      Val-->>CLI: discard → keep Det
    end
  end
  Note over CLI: profile.yaml never written
```

## Update mutex — un solo `jobbot update` a la vez {#update-mutex}

Patrones: **Mutex** / exclusive lock file (pid + stale reclaim). Issue: #398 (#189 dejó el lock fuera).

```mermaid
classDiagram
  direction TB
  class UpdateLock {
    <<Value Object>>
    +Path path
    +int pid
  }
  class update_jobbot {
    <<Command>>
    +run() UpdateResult
  }
  update_jobbot --> UpdateLock : acquire before uv
  note for UpdateLock "path under workspace data/\nlive pid → refuse\ndead pid → reclaim\nfinally → release"
```

```mermaid
sequenceDiagram
  participant CLI as jobbot update / -U
  participant Lock as UpdateLock
  participant UV as uv tool install --force
  CLI->>Lock: try acquire (pid file)
  alt lock held by live pid
    Lock-->>CLI: busy → exit 1 (no uv)
  else missing or stale pid
    Lock->>Lock: write own pid
    CLI->>UV: reinstall (mockable)
    UV-->>CLI: ok | fail
    CLI->>Lock: release (finally)
  end
```

Reglas: el lock vive junto al data del workspace (no en un checkout compartido sin workspace); nunca inventar el lock en el repo; tests mockean el instalador — sin `uv` real.

## Cómo citar desde un issue

```markdown
## SDD / patrones
- SDD: docs/software-design.md §3 / §8
- Patrón(es): Value Object, Aggregate
- UML: docs/uml.md#fact-preference
- El PR actualiza el diagrama si introduce o renombra un tipo
```
