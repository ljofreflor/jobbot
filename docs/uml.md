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

## Cómo citar desde un issue

```markdown
## SDD / patrones
- SDD: docs/software-design.md §3 / §8
- Patrón(es): Value Object, Aggregate
- UML: docs/uml.md#fact-preference
- El PR actualiza el diagrama si introduce o renombra un tipo
```
