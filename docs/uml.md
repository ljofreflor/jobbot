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

## Indeed Apply — avance clasificado, nunca Submit {#indeed-apply-advance}

Patrones: **Strategy** (`IndeedApplyAdapter`), **Specification** (`button_role` / `pressable_advance` — #188), stop-before-submit. Issue: #412 (#188 clasifica; #402 adjunto PDF).

```mermaid
classDiagram
  direction TB
  class IndeedApplyAdapter {
    <<ApplicationPortalAdapter>>
    +prefill()
    +open()
    +advance_step()
  }
  class button_role {
    <<Specification>>
    +classify(label) advance|submit|other
  }
  class pressable_advance {
    +pick(labels) str|None
  }
  IndeedApplyAdapter --> pressable_advance : before click
  pressable_advance --> button_role
  note for pressable_advance "Next/Siguiente/Continue → advance\nEnviar/Submit/Apply → submit\nboth → submit; only submit → None"
```

```mermaid
sequenceDiagram
  participant CLI as application apply --apply
  participant Ad as IndeedApplyAdapter
  participant Page as Indeed Apply page
  participant Human
  CLI->>Ad: open applystart / ATS
  Ad->>Page: list button labels
  Ad->>Ad: pressable_advance(labels)
  alt label advance
    Ad->>Page: click advance only
  else None (submit-only or empty)
    Ad-->>CLI: name submit button; no click
  end
  Note over Ad,Human: CAPTCHA / 2FA / terms / final Submit = HITL
```

Reglas: ningún botón con rol `submit` se pulsa; CAPTCHA/2FA/términos y el envío final quedan fuera (#412). Depende del clasificador #188; el adjunto de CV es #402.

## Postulate — clasificar, abrir opcional, promote aparte {#postulate-route}

Patrones: **Result** (`PostulateRoute`), **Command** plan-then-apply (`--apply`), **promote** explícito al registry. Issues: #410 (#41 clasifica con `--fixture`).

```mermaid
classDiagram
  direction TB
  class PostulateRoute {
    <<Result>>
    +email|portal|unknown kind
    +list~Contribution~ contributions
  }
  class Contribution {
    <<Value Object>>
    +str domain
    +str|None ats_hint
    +str url
  }
  class PortalRegistry {
    +promote(Contribution)
  }
  PostulateRoute *-- Contribution
  Contribution --> PortalRegistry : only via promote
  note for PostulateRoute "no email/phone stored\n--fixture only reads text\nportals.yaml untouched until promote"
```

```mermaid
sequenceDiagram
  participant CLI as postulate --fixture
  participant Class as classify route
  participant Browser
  participant Reg as portals.yaml
  CLI->>Class: fixture text (no download)
  Class-->>CLI: email | portal | unknown
  alt --apply + portal URL
    CLI->>Browser: open classified URL
    Note over Browser: no Submit / CAPTCHA / 2FA
  else default
    CLI-->>CLI: no browser
  end
  opt portals promote (HITL, aparte)
    CLI->>Reg: upsert domain once
  end
```

Reglas: sin `--apply` no se abre nada; `--apply` no marca `applied`; promote es otro comando y es idempotente por dominio. Fuera de alcance: LinkedIn en vivo, CAPTCHA, 2FA, envío.

## CV derived translation — build lee lo ya validado {#cv-derived-translation}

Patrones: **Projection** (`DerivedCvTexts`), **Validator** (`cv translate` #34), build como presentación. Issue: #408 (fuera: auto-traducir, escribir el YAML, overlay `#400`).

```mermaid
classDiagram
  direction TB
  class Candidate {
    <<Fact aggregate>>
    +achievements by id
  }
  class DerivedCvTexts {
    <<Projection>>
    +str lang
    +dict id_to_phrase
  }
  class translate_gate {
    <<Validator>>
    +accept(id, base, phrase) bool
  }
  class cv_build {
    <<Command>>
    +build(--lang) artifact
  }
  Candidate --> DerivedCvTexts : texts only
  translate_gate ..> Candidate : figures + company + skills
  translate_gate ..> DerivedCvTexts : accept | reject
  cv_build --> DerivedCvTexts : use if accepted
  cv_build --> Candidate : fallback base text
  note for cv_build "never writes profile.yaml\nmissing file → base + message"
```

```mermaid
flowchart TD
  B[cv build --lang en] --> F{output/cv/en.yaml?}
  F -->|missing| Base[use profile text by id]
  F -->|has id| G{cv translate would accept?}
  G -->|yes| Use[emit derived phrase]
  G -->|no| Base
  F --> Msg[print per id: used | no translation; the source text stays]
  Use --> Art[TeX/PDF]
  Base --> Art
  Art --> P[(profile.yaml unchanged)]
```

Reglas: misma invariante que #34 (cifra, empresa del texto, no skills nuevas); distinto de `ProfileOverlay` / `profile.en.yaml` (#400).

## Public queue — share → PR → `-U` {#public-queue-sync}

Patrones: **Guard** (`share_refusal` #106), **durable Queue**, **idempotent PR batch**, sync via `jobbot -U`. Issue: #418 (#189 `-U` reinstall; #52 promote sigue HITL).

```mermaid
classDiagram
  direction TB
  class share_refusal {
    <<Guard>>
    +reason|None check(line)
  }
  class ShareQueue {
    +Path local
    +enqueue(Contribution)
    +pending() list
  }
  class ShareBatch {
    +str batch_id
    +list lines
  }
  class CommonsSnapshot {
    <<Port>>
    +open_pr(ShareBatch)
    +pull_main()
  }
  share_refusal --> ShareQueue : only if empty reason
  ShareQueue --> ShareBatch : group
  ShareBatch --> CommonsSnapshot : one PR per batch_id
  CommonsSnapshot --> CompanyRegistry : foreign → candidate
```

```mermaid
sequenceDiagram
  participant Obs as observation / export line
  participant Guard as share_refusal
  participant Q as ShareQueue
  participant GH as GitHub PR
  participant U as jobbot -U
  participant Reg as local companies.yaml
  Obs->>Guard: line text
  alt contact or home path
    Guard-->>Obs: refuse (no enqueue)
  else clean
    Guard->>Q: enqueue
    alt offline
      Q-->>Q: keep on disk; search continues
    else online
      Q->>GH: open PR for batch (no duplicate)
    end
  end
  U->>Reg: pull main snapshot
  Note over Reg: new rows = candidate; promote stays HITL
```

Reglas: nada corre si la línea fue rechazada; no inventar cuenta GitHub; no compartir `profile.yaml`. `jobbot -U` actualiza programa **y** copia local del mapa desde `main` según el PR de implementación.

## Capability gaps — inventario → contrato {#capability-gap-map}

Patrones: **inventory** de puertos faltantes (ai-job-search / homónimos). Issue: #424 (mapa; no implementa). Fuera: autopilot, OAuth bandeja, inventar, followup #422.

```mermaid
flowchart LR
  Gap[stolen use-case row] --> C{falsifiable contract?}
  C -->|no| Open[child issue + SDD patch]
  C -->|yes| Port[ports / Command / Spec]
  Port --> Test[unit fixture offline]
  Test --> Done[row closed]
  Gap -.->|forbidden| No[autopilot / invent / inbox OAuth]
```

```mermaid
classDiagram
  direction TB
  class GapRow {
    +str name
    +str pattern
    +str test_contract
    +str|None child_issue
  }
  class CapabilityGapMap {
    +list~GapRow~ rows
  }
  CapabilityGapMap *-- GapRow
  note for GapRow "structured interview gaps\nexpand+provenance\nportal health\nreviewer ≠ advise\ntemplate registry\nstudy question from market"
```

Reglas: #424 se cumple documentando contratos, no shippeando las seis features en un solo PR.

## Indeed Apply — adjuntar PDF del aviso, nunca Enviar {#indeed-apply-attach}

Patrones: **Strategy** (`attach_cv`), **Command** (solo `set_input_files`). Issue: #402. Complementa [#412](uml.md#indeed-apply-advance) (avance). Fuera: Siguiente, CAPTCHA, 2FA, términos, Submit.

```mermaid
classDiagram
  direction TB
  class IndeedApplyAdapter {
    <<ApplicationPortalAdapter>>
    +page_asks_for_cv() bool
    +tailored_cv_path() Path|None
    +attach_cv(page)
  }
  class TailoredCv {
    <<Artifact>>
    +Path job_package_pdf
  }
  IndeedApplyAdapter --> TailoredCv : set_input_files if asks
  note for IndeedApplyAdapter "null path → missing_tailored_cv\ncover-letter input ignored\nno Submit click"
```

```mermaid
sequenceDiagram
  participant Ad as IndeedApplyAdapter
  participant Page
  Ad->>Ad: page_asks_for_cv?
  alt false
    Ad-->>Ad: no set_input_files
  else true + tailored path
    Ad->>Page: set_input_files(cv.pdf)
  else true + missing path
    Ad-->>Ad: print missing_tailored_cv
  end
  Note over Ad,Page: never click Enviar / Postular / Submit
```

Reglas: solo el PDF del paquete del aviso; input de carta no recibe CV; envío final = HITL (#402).

## Search filters — preferencia antes de upsert {#search-filters}

Patrones: **Preference** (`SearchFilters`), **Specification** (`apply_search_filters`), **Command** dry-run / confirm / `--store`. Issue: #374. Relacionado: [`search-outcome`](uml.md#search-outcome), [`fact-preference`](uml.md#fact-preference).

```mermaid
classDiagram
  direction TB
  class SearchFilters {
    <<Preference VO>>
    +list~str~ exclude_title_terms
    +list locations
    +Relocation|None relocation
    +Money|None min_salary
  }
  class FilterDecision {
    <<Result>>
    +keep|drop verdict
    +str reason
  }
  class apply_search_filters {
    <<Specification>>
    +decide(JobPosting, SearchFilters) FilterDecision
  }
  SearchFilters --> apply_search_filters
  apply_search_filters --> FilterDecision
  note for SearchFilters "not a Fact; profile validate\nunknown currency → reject"
```

```mermaid
flowchart TD
  S[search / torre / getonboard] --> D{--dry-run?}
  D -->|yes| T[table: keep/drop + reason]
  T --> Z[no DB / companies write]
  D -->|no + TTY| C{confirm?}
  C -->|no| X[exit 130]
  C -->|yes| F[apply_search_filters]
  D -->|--store| F
  F --> U[upsert keep rows only]
```

Reglas: sin filtros = comportamiento actual; `--dry-run --store` = exit 2; motivos estables («título excluido», «renta no publicada», …). Fuera: label Torre Remote (#181), check-open (#207).

## CV tune-for — mejora acotada desde un aviso {#cv-tune-for}

Patrones: **Command** (`cv tune-for`), budget, HITL `--apply`. Issue: #54. Reusa gates de `cv advise` (never invent / no-drop).

```mermaid
sequenceDiagram
  participant CLI as cv tune-for
  participant Get as hard-link ingest
  participant Adv as cv advise --job
  participant Hum as Human
  participant SoT as profile.yaml
  alt URL
    CLI->>Get: store JobPosting
  else Jxxxx
    CLI->>CLI: load stored
  end
  CLI->>Adv: scope=that job; budget 3..5
  Adv-->>CLI: suggestions (invention dropped)
  alt --apply
    loop each suggestion
      CLI->>Hum: y / N / skip-all
      Hum-->>CLI: yes
      CLI->>SoT: backup then write
    end
  else dry-run
    CLI-->>CLI: print only
  end
```

```mermaid
classDiagram
  direction TB
  class TuneForCommand {
    <<Command>>
    +url_or_job_id
    +budget int
    +apply bool
  }
  class AdviceBudget {
    <<Value Object>>
    +int max_suggestions
  }
  TuneForCommand --> AdviceBudget
  TuneForCommand --> JobPosting : scopes
  note for TuneForCommand "~5% product metaphor\nnot a percentage calc\ncv build --job stays derived"
```

Reglas: no reescribe el baseline entero; tailored CV sigue en `cv build --job`; LLM opcional queda en advise.

## Trabajando.cl — perfil por sección + límites {#trabajando-profile-push}

Patrones: **WritableProfileAdapter**, **Validator** de límites (SST + legacy), **ACL** CEFR→nivel, plan-then-apply. Issues: #285 (#150 fila 7).

```mermaid
classDiagram
  direction TB
  class TrabajandoProfileAdapter {
    <<WritableProfileAdapter>>
    +diff()
    +sync_plan(section)
    +apply(section)
  }
  class FieldLimit {
    <<Value Object>>
    +str field
    +int max_len
  }
  class LegacyViolation {
    <<Result>>
    +str entry_id
    +str field
    +int length
  }
  class SectionPlan {
    <<Command plan>>
    +full section payload
    +list~LegacyViolation~ blockers
    +list needs_human
  }
  TrabajandoProfileAdapter --> FieldLimit
  TrabajandoProfileAdapter --> SectionPlan
  SectionPlan *-- LegacyViolation
  note for SectionPlan "portal re-POSTs whole section\nlegacy over-limit → refuse push\nno RUN / DOB / invented jornada"
```

```mermaid
flowchart TD
  Diff[portals profile diff trabajando] --> L{legacy over limit?}
  L -->|yes| Warn[mark blocker on entry]
  Push[push --section --apply] --> V{SST or legacy invalid?}
  V -->|yes| E2[exit 2; no HTTP]
  V -->|no| HITL[confirm section]
  HITL -->|no| E130[exit 130]
  HITL -->|yes| POST[save section]
  POST -->|400| E1[exit 1; state unchanged]
  POST -->|ok| Reread[re-read; mark updated]
```

Reglas: `--fix-legacy` propone recorte con confirm por entrada; `needs_human` para renta/jornada sin hecho; fixtures sin PII.

## LinkedIn Easy Apply — Solicitud sencilla HITL {#linkedin-easy-apply}

Patrones: **Strategy** (`ApplicationPortalAdapter`), **Command** plan-then-apply, evidencia de UI para `submitted`. Issue: #296. Paridad con Indeed [#402](uml.md#indeed-apply-attach) / [#412](uml.md#indeed-apply-advance).

```mermaid
classDiagram
  direction TB
  class LinkedInEasyApplyAdapter {
    <<ApplicationPortalAdapter>>
    +prefill_contact_e164()
    +attach_cv_and_select_card()
    +pause_employer_questions()
    +record_submitted_if_evidence()
  }
  class EasyApplyEvidence {
    <<Result>>
    +str|None ui_success_text
    +prepared|submitted status
  }
  class TailoredCv {
    <<Artifact>>
    +Path job_package_pdf
  }
  LinkedInEasyApplyAdapter --> Candidate : reads SST
  LinkedInEasyApplyAdapter --> TailoredCv : set_input_files + card
  LinkedInEasyApplyAdapter --> EasyApplyEvidence
  note for LinkedInEasyApplyAdapter "no InMail / no publish\nneeds_human on unknown Qs\nsubmitted only with UI text"
```

```mermaid
sequenceDiagram
  participant CLI as application apply
  participant Ad as EasyApplyAdapter
  participant Page
  participant Hum as Human
  CLI->>Ad: open Easy Apply (CDP)
  Ad->>Page: country +56 + tel from SST
  Ad->>Page: set_input_files(cv.pdf) + select card
  Ad->>Ad: employer Qs projected?
  alt unknown
    Ad->>Hum: HITL pause
  end
  Ad->>Page: look for «Solicitud enviada»
  alt evidence
    Ad-->>CLI: submitted
  else none
    Ad-->>CLI: prepared (unknown)
  end
  Note over Ad,Page: never auto-click final Submit
```

Reglas: móvil del SST (nunca inventado); PDF del paquete del aviso; `submitted` exige texto observable (#296).

## Workday CXS — detalle público sin login {#workday-cxs-detail}

Patrones: **ACL** (URL → CXS), **Adapter** puro, **VO** cierre con zona. Issue: #215. Compartido con #225 / #207.

```mermaid
classDiagram
  direction TB
  class WorkdayRef {
    <<Value Object>>
    +str host
    +str tenant
    +str site
    +str external_path
    +str req_id
  }
  class CxsClient {
    <<Adapter>>
    +parse_workday_url(url) WorkdayRef|None
    +fetch_job(ref, fetch) WorkdayJob|Closed
    +to_job_posting(job) JobPosting
  }
  class ClosingInstant {
    <<Value Object>>
    +date endDate
    +tz|time_unknown
  }
  CxsClient --> WorkdayRef
  CxsClient --> ClosingInstant
  CxsClient --> JobPosting
  note for CxsClient "no SPA HTML scrape\n404/S22 → ClosedPostingError\n406 → one retry wider Accept"
```

```mermaid
flowchart TD
  U[jobbot get / jobs add --url] --> P{parse_workday_url}
  P -->|None| Other[other portals]
  P -->|WorkdayRef| CXS[GET wday/cxs/.../job/...]
  CXS -->|200 + jobPostingInfo| Map[to_job_posting]
  CXS -->|404 / 403 S22| Closed[ClosedPostingError]
  CXS -->|406| Retry[retry Accept+Content-Type]
  Map --> Closes{endDate + tz rule}
  Closes -->|text or site tz| Z[closes_at zoned]
  Closes -->|missing| TU[time_unknown]
```

Reglas: rate limit + UA identificable; robots.txt; nunca login; `includeResumeParsing` / `questionnaireId` como señales (#215).

## Browser login tour — un hueco, HITL humano {#browser-login-tour}

Patrones: **Command** dry-run / `--apply`, **Specification** de buckets, **Guard** de evidencia de sesión. Issue: #56.

```mermaid
classDiagram
  direction TB
  class LoginTourPlan {
    <<Command plan>>
    +list~LoginGap~ gaps
    +dry_run|apply mode
  }
  class LoginGap {
    <<Value Object>>
    +str site_id
    +permanent|active|candidate bucket
    +needs_login|unknown|profile_busy state
  }
  class SessionEvidence {
    <<Specification>>
    +ready only if signed-in page
  }
  LoginTourPlan *-- LoginGap
  SessionEvidence --> LoginGap
  note for SessionEvidence "CDP port ≠ ready\ncompany tab ≠ ready\nnever password/CAPTCHA"
```

```mermaid
flowchart TD
  Start[browser login] --> B1[permanent]
  B1 --> B2[company active]
  B2 --> B3[company candidate]
  B3 --> List[print gaps]
  List --> D{--apply?}
  D -->|no| Stop[dry-run; no Chrome]
  D -->|yes| Open[open first gap only]
  Open --> HITL[human: password / CAPTCHA / 2FA]
  HITL --> Done[stop; no promote candidate]
```

Reglas: skip ATS sin cuenta (Greenhouse/Lever/Ashby/Teamtailor); `rejected`/`stale`/job boards fuera; planner no escribe `companies.yaml` (#56).

## Experience-first search — sin proxy de profesión {#experience-first-search}

Patrones: **Preference** `search_queries`, **Strategy** matcher (evidencia del perfil), **Registry** de fuentes. Issue: #118. Relacionado: [#180](https://github.com/ljofreflor/jobbot/issues/180) / [#224](https://github.com/ljofreflor/jobbot/issues/224), [`search-filters`](uml.md#search-filters).

```mermaid
classDiagram
  direction TB
  class SearchQueries {
    <<Preference>>
    +list~str~ phrases
    +derived_from experience
  }
  class ProfileEvidenceMatcher {
    <<Strategy>>
    +score(Candidate, JobPosting) JobMatch
  }
  class PageChromeFilter {
    <<Specification>>
    +drop_metadata_as_skill()
  }
  Candidate --> SearchQueries : derive / edit
  ProfileEvidenceMatcher --> Candidate : skills / titles / achievements
  ProfileEvidenceMatcher --> PageChromeFilter : ignore deadlines/salaries
  JobSourceAdapter ..> SearchQueries : uses when no QUERY
  note for SearchQueries "not Fact; editable\nnever default occupation\nin code"
```

```mermaid
flowchart TD
  P[profile.yaml experience] --> Q[derive search_queries]
  Q --> S[JobSourceAdapter.search]
  S --> M[matcher + profile evidence]
  M --> C{all scores 0%?}
  C -->|yes| A[matcher alert]
  C -->|no| SL[shortlist]
```

Reglas: titular no es la única query; chrome de página no es requisito faltante; lado perfil solo añade; domain-agnostic (#118).

## Workday session — un tenant, un host {#workday-session-tenant}

Patrones: **Value Object** (site = career host), **Port** `inspect_sessions` con puertos extensibles. Issue: #394 (#216 aviso de login; #56 tour).

```mermaid
classDiagram
  direction TB
  class SessionState {
    +str site
    +ready|needs_login|unknown|profile_busy status
    +int|None port
  }
  class inspect_sessions {
    <<Port>>
    +run(ports) list~SessionState~
  }
  class WorkdayTenant {
    <<Value Object>>
    +str host
  }
  inspect_sessions --> SessionState
  SessionState --> WorkdayTenant : site == host
  note for WorkdayTenant "acme.wd5… ≠ other.wd5…\nno generic workday id\nextra ports e.g. 9225"
```

```mermaid
sequenceDiagram
  participant CLI as browser sessions
  participant Insp as inspect_sessions
  participant CDP as Chrome CDP ports
  CLI->>Insp: ports = DEFAULT ∪ extras
  Insp->>CDP: probe each port
  CDP-->>Insp: tab URL host
  alt host is Workday tenant + signed-in evidence
    Insp-->>CLI: ready site=that host
  else other tenant
    Insp-->>CLI: no ready for that other host
  end
```

Reglas: no login ni fill aquí; company tab sigue sin ser `ready` genérico salvo evidencia de ese host.

## Laborum — términos primero, luego sitemap {#laborum-sitemap-terms}

Patrones: **Guard** (terms decision #227), **JobSourceAdapter** (sitemap → postings). Issue: #396. Fuera: decidir términos; descarga en vivo de laborum.cl.

```mermaid
classDiagram
  direction TB
  class TermsGate {
    <<Guard>>
    +bool allowed
    +str reason_dated
  }
  class LaborumDiscover {
    <<JobSourceAdapter>>
    +discover_site() SiteOutcome
  }
  class SitemapReader {
    +parse(fixture) list~JobPosting~
  }
  LaborumDiscover --> TermsGate : before any read
  LaborumDiscover --> SitemapReader : only if allowed
  note for TermsGate "false → exit 2, no network\ntrue → fixture/sitemap path"
```

```mermaid
flowchart TD
  D[jobs discover --source laborum] --> G{terms allowed?}
  G -->|no| R[exit 2; TERMS_REASON; 0 jobs]
  G -->|yes| F[--fixture sitemap]
  F --> P[parse URL + title]
  P --> Robots{robots allows URL?}
  Robots -->|no filter page| Drop[do not upsert]
  Robots -->|yes job URL| Save[upsert JobPosting]
```

Reglas: la marca la cambia un mantenedor (HITL de política); tests mockean/paran la red; listados prohibidos por robots nunca entran al repositorio.

## HiringRoom discover — listado + detalle, página 2 por fixture {#hiringroom-discover}

Patrones: **JobSourceAdapter**, **Iterator** (stop at total / `--limit`), multi-site isolation. Issue: #377 (#243 ficha guardada; no adivinar endpoint JS).

```mermaid
classDiagram
  direction TB
  class HiringRoomDiscover {
    <<JobSourceAdapter>>
    +discover_site() SiteOutcome
  }
  class ListingPage {
    +list rows
    +int|None total
    +str|None next_fixture_key
  }
  class VacancyDetail {
    +str id
    +JobPosting posting
  }
  HiringRoomDiscover --> ListingPage : /jobs (+ page2 fixture)
  HiringRoomDiscover --> VacancyDetail : /jobs/get_vacancy/id
  note for ListingPage "?page= / ?offset= do not work\npage 2 only via known fixture"
```

```mermaid
sequenceDiagram
  participant CLI as jobs discover --source hiringroom
  participant Ad as HiringRoomDiscover
  participant Fetch as fetcher (fixture)
  participant Store as JobRepository
  CLI->>Ad: site *.hiringroom.com/jobs
  Ad->>Fetch: listing page 1
  opt page2 fixture present
    Ad->>Fetch: listing page 2
  end
  loop new vacancy ids until total or --limit
    Ad->>Fetch: get_vacancy id
    Fetch-->>Ad: detail HTML
    Ad->>Store: upsert (skip if known)
  end
  Note over Ad: peer site 503 → continue; bad --site → exit 2
```

Reglas: `--dry-run` no escribe; postular/cuenta fuera de alcance; host inválido exit 2.

## ReliefWeb discover — API v2 + appname local {#reliefweb-discover}

Patrones: **JobSourceAdapter**, **Config Port** (appname never logged), **Guard** AUTH_REQUIRED. Issue: #247 (#180 épica; no RSS/web).

```mermaid
classDiagram
  direction TB
  class ReliefWebConfig {
    <<Config>>
    +str|None appname
    +resolve() env over toml
  }
  class ReliefWebDiscover {
    <<JobSourceAdapter>>
    +discover() list~JobPosting~
  }
  class JobPosting {
    +source reliefweb
    +closes_at
    +remote_type
  }
  ReliefWebDiscover --> ReliefWebConfig : before POST
  ReliefWebDiscover --> JobPosting : map fields
  note for ReliefWebConfig "never print value\nmissing → exit 3 no network"
```

```mermaid
flowchart TD
  D[jobs discover --source reliefweb] --> C{appname configured?}
  C -->|no| A3[exit 3 + apidoc link]
  C -->|yes| P[POST /v2/jobs?appname=…]
  P -->|403/400 appname| A3b[exit 3; redact value]
  P -->|200 + data| M[map title/source/closes_at/url]
  M --> Off{offset < total and limit?}
  Off -->|yes| P
  Off -->|no| Out[dry-run preview or upsert]
```

Reglas: ≤1 req/s; UA identificable; appname nunca en el repo; aplicar en el ATS del organismo, no en ReliefWeb.

## Taleo careersection — searchjobs + columnas por sitio {#taleo-careersection-discover}

Patrones: **JobSourceAdapter**, **ACL** (column map per site), multi-site isolation. Issue: #245 (#151 AtsKind.TALEO; ≠ ORC).

```mermaid
classDiagram
  direction TB
  class TaleoDiscover {
    <<JobSourceAdapter>>
    +discover_site() SiteOutcome
  }
  class CareerSectionSite {
    +str host
    +str section
    +str|None portal
    +list column_roles
  }
  class ColumnACL {
    <<ACL>>
    +map(columns) title|locations|posted|closes
  }
  TaleoDiscover --> CareerSectionSite
  TaleoDiscover --> ColumnACL : per site
  note for ColumnACL "FAO closes_at col ≠ WHO posted_at col\ninfer from jobsearch.ftl labels"
```

```mermaid
sequenceDiagram
  participant CLI as jobs discover --source taleo
  participant Ad as TaleoDiscover
  participant FTL as jobsearch.ftl
  participant API as POST searchjobs
  CLI->>Ad: site host/section or registry
  alt portal missing
    Ad->>FTL: GET extract portal=
  end
  loop pageNo until total or --limit
    Ad->>API: KEYWORD + portal
    API-->>Ad: requisitionList + pagingData
  end
  Note over Ad: peer unavailable → continue; bad --site → exit 2
```

Reglas: sin sesión/cookies de candidato; URL pública `jobdetail.ftl?job={contestNo}`; postular fuera de alcance.

## SuccessFactors CSB — clásica vs Unify (sitemap) {#successfactors-csb-discover}

Patrones: **JobSourceAdapter**, **Strategy** (template variant), robots Guard. Issue: #230 (#224 BID; no OData; no JS).

```mermaid
classDiagram
  direction TB
  class SuccessFactorsDiscover {
    <<JobSourceAdapter>>
    +discover_site() SiteOutcome
  }
  class CsbVariant {
    <<Enumeration>>
    classic
    unify
  }
  class ClassicSearch {
    +GET /search/?q=&startrow=
  }
  class UnifySitemap {
    +GET /sitemap.xml
    +GET /job/slug/id/
  }
  SuccessFactorsDiscover --> CsbVariant : detect from /search/ HTML
  CsbVariant --> ClassicSearch : job-tile present
  CsbVariant --> UnifySitemap : rmk-jobs-search, no tiles
  note for UnifySitemap "never /services/\nfilter locs by query slug"
```

```mermaid
flowchart TD
  D[jobs discover --source successfactors] --> S[GET /search/?q=]
  S --> V{job-tile?}
  V -->|yes classic| P[paginate startrow]
  V -->|Unify widget| M[GET sitemap.xml]
  M --> J[filter /job/ URLs]
  J --> Det[GET detail HTML]
  P --> Det
  Det --> C{filled / closed?}
  C -->|yes| Skip[omit]
  C -->|no| Save[upsert or dry-run]
```

Reglas: respetar robots; sin browser/JS; sin cuenta; categorías `/go/` no se adivinan.

## LATAM master table — seed → discover → promote → shared {#latam-master-table}

Patrones: **Pipeline** oneshot + HITL promote, commons snapshot. Issue: #298 (#265 CL; #269 one model; #183 job board ≠ employer portal).

```mermaid
flowchart LR
  Seed[companies-latam.seed.yaml] --> Disc[companies discover]
  Disc --> Out[output/discovery/]
  Out --> Imp[companies import]
  Imp --> Cand[candidate rows]
  Cand --> Rec[recon / promote HITL]
  Rec --> Act[active]
  Act --> Exp[companies export]
  Exp --> Shared[companies.shared.yaml]
  Shared --> Site[make site / plataformas]
```

```mermaid
classDiagram
  direction TB
  class CompanySeed {
    +str company_id
    +str name
    +str|None domain
    +list career_url_hints
  }
  class CareerSite {
    +str url
    +AtsKind|unknown ats
    +candidate|active|stale|rejected status
  }
  class CompanyRegistry {
    +promote HITL
    +export active only
  }
  CompanySeed --> CareerSite : discover candidates
  CareerSite --> CompanyRegistry
  note for CareerSite "unknown without technical evidence\njob boards not employer portals\n403 = refused not absence"
```

Reglas: batches regionales (MX, AR, …) sin duplicar CL; Tempo sin Laborum como portal; sin PII de candidato.

## WhatsApp question queue — preguntar, no inventar {#whatsapp-question-queue}

Patrones: **Aggregate** `Question`, **Command** send/apply HITL, **Port** channel (deeplink / Cloud API). Issue: #251. Fuera: auto-send, WA Web scrape, inferir respuestas.

```mermaid
classDiagram
  direction TB
  class Question {
    +str id
    +origin kind+ref
    +str destination
    +pending|sent|answered|applied|dismissed status
    +datetime|None closes_at
  }
  class QuestionQueue {
    +enqueue()
    +plan_send() MessageBatch
    +ingest(text)
    +plan_apply() Diff
  }
  class WhatsAppChannel {
    <<Port>>
    +deeplink(batch)
    +cloud_api_opt_in(batch)
  }
  QuestionQueue *-- Question
  QuestionQueue --> WhatsAppChannel : send HITL only
  note for Question "never invent answer\nid = hash origin+destination+prompt"
```

```mermaid
sequenceDiagram
  participant Src as conditions/answers/portal
  participant Q as QuestionQueue
  participant Op as operator
  participant WA as WhatsAppChannel
  participant SST as profile / answers
  Src->>Q: enqueue ask gaps
  Op->>Q: plan_send (dry-run)
  alt --apply + confirm
    Op->>WA: deeplink or Cloud API
    WA-->>Q: status sent
  end
  Op->>Q: ingest numbered replies
  Op->>Q: plan_apply diff
  alt confirm
    Q->>SST: write destination only
  end
```

Reglas: cola en SQLite local (no git); sensitive flags; no OTP/docs por WA; otros canales no en este issue.

## Aira — discover por slug de catálogo {#aira-slug-discover}

Patrones: **JobSourceAdapter**, **Registry** (slugs observados), **SearchOutcome**. Issue: #267 (#265 coverage; #241/#243 peers).

```mermaid
classDiagram
  direction TB
  class AiraChannel {
    <<Registry row>>
    +str slug
    +str employer_name
  }
  class AiraDiscover {
    <<JobSourceAdapter>>
    +discover(slugs) SiteOutcome
  }
  class JobPosting {
    +source aira
    +company employer_of_channel
  }
  AiraDiscover --> AiraChannel : only catalog slugs
  AiraDiscover --> JobPosting : title + canonical URL
  note for AiraChannel "never invent slug from brand\nhost jobs.airavirtual.com shared"
```

```mermaid
flowchart TD
  D[jobs discover --source aira] --> R[slugs from companies/catalog]
  R --> F[fixture or fetch listing]
  F --> O{ok / refused / empty?}
  O -->|403 or robots| Ref[refused ≠ zero jobs]
  O -->|rows| M[map; company ≠ Aira]
  M --> Cap[mark job_listing proven per channel]
```

Reglas: plataforma nunca es el empleador; sin autopilot de envío; suite offline.

## Trabajando marca blanca — idDominio + searchjob {#trabajando-white-label-discover}

Patrones: **JobSourceAdapter**, **ACL** JSON→posting, **Strategy** Nuxt vs legado. Issue: #241 (#183 bolsa ≠ portal; #285 profile push aparte).

```mermaid
classDiagram
  direction TB
  class TrabajandoDiscover {
    <<JobSourceAdapter>>
    +resolve_idDominio(host)
    +searchjob(pagina)
  }
  class WhiteLabelSite {
    +str subdomain
    +int|None idDominio
    +ats trabajando
  }
  class OfferDetail {
    +closes_at America/Santiago
    +salary_text|None
  }
  TrabajandoDiscover --> WhiteLabelSite
  TrabajandoDiscover --> OfferDetail : /api/ofertas/id
  note for WhiteLabelSite "www.trabajando.cl is board\nnot employer portal"
```

```mermaid
sequenceDiagram
  participant CLI as jobs discover --source trabajando
  participant Ad as TrabajandoDiscover
  participant Host as empresa.trabajando.cl
  CLI->>Ad: site from registry or --site
  Ad->>Host: GET / → __NUXT_DATA__ idDominio
  loop pagina 1..N until limit
    Ad->>Host: GET /api/searchjob
    Ad->>Host: GET /api/ofertas/id (new only)
  end
  Note over Ad: companies discover also probes slug.trabajando.cl
```

Reglas: filtro query/location local; confidencial → nombre del sitio; detalle login → listado + nota; dry-run no escribe.

## Empleos Públicos — feeds vivos + CDP HITL {#empleos-publicos-live}

Patrones: **JobSourceAdapter**, **Strategy** HTTP→CDP, **SearchOutcome** / challenge. Issue: #240 (#180; fixture-first legacy).

```mermaid
classDiagram
  direction TB
  class EmpleosPublicosDiscover {
    <<JobSourceAdapter>>
    +read_feeds() FeedUnion
  }
  class FeedChannel {
    <<Strategy>>
    +http_identifiable()
    +cdp_same_origin()
  }
  class SalaryText {
    <<Value Object>>
    +normalize(raw) str|None
  }
  EmpleosPublicosDiscover --> FeedChannel
  EmpleosPublicosDiscover --> SalaryText : 1,00 / 0 → None
  note for FeedChannel "403 without --browser → exit 4\nnever spoof UA / CAPTCHA"
```

```mermaid
flowchart TD
  D[jobs discover --source empleos_publicos] --> H[HTTP both feeds]
  H -->|200| U[union dedupe]
  H -->|403| B{--browser / CDP?}
  B -->|no| E4[exit 4 + hint feed-file]
  B -->|yes| C[same-origin fetch in Chrome]
  C --> U
  U --> F[filter query/location local]
  F --> S[skip expired closes_at]
```

Reglas: `--fixture` alias de `--feed-file`; un feed caído no tumba al otro; URL externa conserva `ats_kind` detectado; ClaveÚnica/postular fuera.

## Companies promote policy — evidencia, opt-in, un modelo {#companies-promote-policy}

Patrones: **Policy/Guard** auto-promote, **Opt-in** share, **Aggregate** único. Issue: #269 (alinea #52 #106 #265; cola #418).

```mermaid
classDiagram
  direction TB
  class TechnicalEvidence {
    <<Specification>>
    +host_rule|redirect|html_marker
  }
  class AutoPromote {
    <<Policy>>
    +eligible(CareerSite) bool
  }
  class ShareOptIn {
    <<Preference>>
    +bool enabled
    +queue_reviewable
  }
  class CompanyRegistry {
    <<Aggregate>>
    +CareerSite sites
    +CapabilityMap caps
  }
  AutoPromote --> TechnicalEvidence
  AutoPromote --> CompanyRegistry : candidate→active
  ShareOptIn --> CompanyRegistry : enqueue public facts
  note for AutoPromote "unknown → HITL promote\nrejected/board never auto"
```

```mermaid
flowchart TD
  Learn[companies learn / recon] --> Ev{technical ATS evidence?}
  Ev -->|yes| Auto[auto-promote + log evidence]
  Ev -->|unknown| Cand[stay candidate]
  Cand --> Hitl[companies promote HITL]
  Auto --> Opt{share opt-in?}
  Opt -->|no| Local[local only]
  Opt -->|yes| Q[revisable outbound queue]
```

Reglas: uso local solo no promueve; contradicción → `stale`; catálogo #265 se fusiona en `companies` (canal = CareerSite); sin telemetría.

## Catalog unknown recon — evidencia, no inventar ATS {#catalog-unknown-recon}

Patrones: **Command** recon por impacto, **Specification** evidencia técnica, **Observation** stale-safe. Issue: #268 (cobertura #265; recon #45; promote #269).

```mermaid
classDiagram
  direction TB
  class UnknownChannel {
    <<Registry row>>
    +ats_family unknown
    +employer_count
  }
  class TechnicalAtsEvidence {
    <<Specification>>
    +host_rule|redirect|html_marker
  }
  class CatalogUnknownRecon {
    <<Command>>
    +list_by_impact()
    +observe(html|cdp)
  }
  class AtsObservation {
    +family
    +evidence_url
    +observed_at
  }
  CatalogUnknownRecon --> UnknownChannel : prioritizes
  CatalogUnknownRecon --> TechnicalAtsEvidence : requires
  CatalogUnknownRecon --> AtsObservation : writes
  note for CatalogUnknownRecon "403/robots = unread\nidentify ≠ enable"
```

```mermaid
flowchart TD
  List[list unknown by employer impact] --> Recon[recon fixture|CDP]
  Recon --> Ev{technical evidence?}
  Ev -->|yes| Obs[write family + observation]
  Ev -->|no| Keep[stay unknown]
  Recon --> Refused[403 / timeout / robots]
  Refused --> Keep
  Obs --> Cov[coverage reorder unlock ranking]
  Obs --> Pend[pending adapter — not auto-active]
```

Reglas: hostname solo no basta; contradicción → `stale`; denominador de canales no cambia; sin cuentas ni postulación.

## BCI Cornerstone — seed + evidencia CSOD {#bci-cornerstone-recon}

Patrones: **Seed hint**, **ACL/detect** CSOD, **Guard** no inventar Workday. Issue: #249 (#151 Cornerstone; #45 recon).

```mermaid
classDiagram
  direction LR
  class CareerUrlHint {
    +url trabajaenbci.cl/
  }
  class CsodEvidence {
    <<ACL>>
    +host *.csod.com
    +csp frame-src|form-action
  }
  class AtsKind {
    <<enumeration>>
    cornerstone
    unknown
  }
  CareerUrlHint --> CompanyRegistry : seed
  CsodEvidence --> AtsKind : observe
  note for AtsKind "never workday without\nWorkday marker on own portal"
```

```mermaid
flowchart TD
  Seed[career_url_hints BCI] --> Learn[companies learn]
  Learn --> Recon[recon fixture HTML/CSP]
  Recon --> CSOD{csod.com evidence?}
  CSOD -->|yes| CS[cornerstone or unknown+cited]
  CSOD -->|no| U[unknown]
  Recon --> WD{workday marker on portal?}
  WD -->|no| Skip[do not invent workday ATS]
```

Reglas: SPA listado fuera de alcance live; reCAPTCHA HITL; promote → recon → sync humanos.

## Non-tech sources epic — registry + blocked {#nontech-source-epic}

Patrones: **Epic Facade**, **JobSourceAdapter** registry, **Guard** blocked. Issue: #224 (hijos #233–#239; hermana #180; bolsas #191).

```mermaid
classDiagram
  direction TB
  class NonTechSourceEpic {
    <<Facade>>
  }
  class JobSourceAdapter {
    <<Protocol>>
  }
  class DiscoveryBlocked {
    <<Value Object>>
    +reason
    +reviewed_at
  }
  class SourceId {
    <<enumeration>>
    un_careers
    pageup
    impactpool
    avature
    cornerstone
    lumesse
    pdf_index
  }
  NonTechSourceEpic --> SourceId : registers
  SourceId --> JobSourceAdapter : enabled
  SourceId --> DiscoveryBlocked : refused
  JobSourceAdapter ..> JobPosting : ACL map
```

```mermaid
flowchart TD
  Discover[jobs discover --source X] --> Gate{robots / terms / token?}
  Gate -->|blocked| Exit2[exit 2 — zero sockets]
  Gate -->|ok| Adapt[JobSourceAdapter + fake fetch]
  Adapt --> Map[ACL → JobPosting]
  Adapt --> Outcome{empty | refused | rows}
  Map --> Dedupe[source + source_job_id]
  Map --> Close[closure — no expired as open]
```

Reglas: queries del perfil; UA + ≤1 req/s; sin login/CAPTCHA bypass; OCR fuera; hijos implementan o declaran blocked.

## Workday E2E epic — discover → profile → apply HITL {#workday-e2e-epic}

Patrones: **Epic Facade**, puertos Workday, **Command** plan-apply, **Guard** no Submit. Issue: #214 (hijos #215–#220 #225; sesión #216/#394; vigencia #207).

```mermaid
classDiagram
  direction TB
  class WorkdayE2E {
    <<Facade>>
  }
  class WorkdayCxsSource {
    <<JobSourceAdapter>>
  }
  class WorkdayProfilePort {
    <<ProfileAdapter>>
  }
  class WorkdayApplyPort {
    <<ApplicationPortalAdapter>>
  }
  class TenantSession {
    <<Guard>>
    +host keyed evidence
  }
  WorkdayE2E --> WorkdayCxsSource : discover/get
  WorkdayE2E --> WorkdayProfilePort : diff/push
  WorkdayE2E --> WorkdayApplyPort : prefill HITL
  WorkdayE2E --> TenantSession : one account/tenant
```

```mermaid
flowchart TD
  Learn[companies learn tenant] --> Disc[jobs discover CXS]
  Disc --> Get[get / add --url CXS]
  Get --> Open[check-open signals]
  Learn --> Signup[signup HITL — no password]
  Signup --> Sess[browser sessions per host]
  Sess --> Diff[profile diff]
  Diff --> Push[profile push --apply]
  Push --> Apply[application apply --apply]
  Apply --> Stop[stop before Submit]
```

Reglas: CXS público sin login para discover/detalle; perfil = proyección SST; nunca password/términos/autoidentificación/Submit; UI_CHANGED=5.

## Legal/admin portals epic — learned boards + ATS {#legal-admin-portals}

Patrones: **Epic Facade**, **JobSourceAdapter** registry, **Guard** robots/términos, bolsas. Issue: #191 (hijos #226–#232; hermana #180; no-tech #224).

```mermaid
classDiagram
  direction TB
  class LegalAdminPortals {
    <<Facade>>
  }
  class JobSourceAdapter {
    <<Protocol>>
  }
  class DiscoveryBlocked {
    <<Value Object>>
    +reason
    +reviewed_at
  }
  class SourceId {
    <<enumeration>>
    chiletrabajos
    laborum
    adp
    bne
    successfactors
    smartrecruiters
    pjud
  }
  class JobBoardKind {
    <<enumeration>>
    bolsa
    employer_ats
  }
  LegalAdminPortals --> SourceId : registers
  SourceId --> JobSourceAdapter : enabled
  SourceId --> DiscoveryBlocked : refused / import-only
  SourceId --> JobBoardKind : classify
  JobSourceAdapter ..> JobPosting : ACL map
```

```mermaid
flowchart TD
  Discover[jobs discover --source X] --> Gate{robots / terms?}
  Gate -->|ADP Disallow| Import[import saved fichas only]
  Gate -->|Laborum terms open| Decide[record decision #227]
  Gate -->|ok| Adapt[JobSourceAdapter + fake fetch]
  Adapt --> Board{bolsa?}
  Board -->|yes| NoLearn[companies learn skips employer]
  Board -->|no| Learn[optional companies candidate]
  Adapt --> Map[ACL → JobPosting]
  Map --> Close[closure — no expired as open]
```

Reglas: queries del perfil; UA + ≤1 req/s; sin login/CAPTCHA bypass; Laborum misma decisión que #180; export sin PII.

## Jobs discover epic — public APIs + greedy coverage {#jobs-discover-epic}

Patrones: **Epic Facade**, **Factory** de fuentes, **Command** dry-run, **Greedy Coverage**, **SearchOutcome**. Issue: #180 (hijos #225 #240–#248; hermanas #191 #224; Workday #214; cola #106/#418).

```mermaid
classDiagram
  direction TB
  class JobsDiscover {
    <<Facade>>
  }
  class JobSourceAdapter {
    <<Protocol>>
  }
  class CoverageReport {
    <<Value Object>>
    +origin repo|perfil
    +status
    +share_state
  }
  class ClosingInstant {
    <<Value Object>>
    +closes_at
    +tz
  }
  JobsDiscover --> JobSourceAdapter : --source / --greedy
  JobsDiscover --> CoverageReport : one row per portal
  JobSourceAdapter ..> JobPosting : ACL
  JobPosting --> ClosingInstant : optional
```

```mermaid
flowchart TD
  Cmd[jobs discover] --> Mode{--source | --greedy}
  Mode -->|source| One[Factory → adapter]
  Mode -->|greedy| Uni[repo ∪ perfil hosts]
  Uni --> Row[CoverageReport row each]
  One --> Dry{--dry-run?}
  Dry -->|yes| Preview[no DB / no companies.yaml]
  Dry -->|no| Upsert[dedupe source+id]
  Row --> Share[perfil → public queue #106]
  One --> Out{empty | refused | rows}
```

Reglas: sitios desde `companies sites` / catálogo; sin query fija de oficio; robots/términos tipados; `salary_text` tal cual; nunca bypass anti-bot.

## Advisor mode — multi-candidate checkout {#advisor-mode}

Patrones: **Aggregate** sandbox, **Projection** advisor, **Consent** VO, **Guard** wrong_account. Issue: #129 (tracker #35; tune-for #54; login tour #56).

```mermaid
classDiagram
  direction TB
  class AdvisorMode {
    <<Facade>>
  }
  class Workspace {
    <<Aggregate>>
    +name
    +OwnerStamp
  }
  class Consent {
    <<Value Object>>
    +granted_at
    +scope
    +retain_until
  }
  class AdvisorStatus {
    <<Projection>>
    +fingerprint
    +job_count
    +prepared
    +proposal_today
  }
  class SessionGuard {
    <<Guard>>
    ready
    wrong_account
    unknown
    profile_busy
  }
  AdvisorMode --> Workspace : list/status
  Workspace --> Consent : local gitignored
  AdvisorMode --> AdvisorStatus : no PII names
  Workspace --> SessionGuard : preflight
```

```mermaid
flowchart TD
  List[advisor status] --> Rows[one row per sandbox]
  Rows --> Redact[fingerprint only]
  Report[advisor report --workspace] --> Scope[that sandbox only]
  Scope --> PII[pii_guard.redact]
  CDP[browser sessions / --cdp] --> Match{page identity = owner?}
  Match -->|no| Wrong[wrong_account — block]
  Match -->|yes| Ready[ready]
  Match -->|no evidence| Unknown[unknown]
  Delete[workspace delete] --> Confirm{HITL confirm?}
  Confirm -->|no| Stop[no write]
  Confirm -->|yes| Rm[only that sandbox]
```

Reglas: nunca imprimir nombre del dueño ni identidad ajena; delete no toca `data/` raíz; HITL de envío intacto; datacenter browser fuera de alcance.

## Isolated client VM — before identity mailbox {#isolated-client-vm}

Patrones: **Isolation Boundary**, **Decision Record**. Issue: #274 (bloquea #272; mapa #162; advisor #129; posicionamiento #266).

```mermaid
classDiagram
  direction TB
  class IsolatedClientVm {
    <<Boundary>>
    +one machine per paying client
  }
  class LocalCliSegment {
    <<Context>>
    +workspace sandboxes
    +gift use
  }
  class HostedSegment {
    <<Context>>
    +pays for VM
  }
  class ProfileYaml {
    <<SoT>>
    +on that machine only
  }
  IsolatedClientVm --> HostedSegment : hosts
  LocalCliSegment --> Workspace : already shipped
  IsolatedClientVm --> ProfileYaml : never shared store
  IsolatedClientVm ..> IdentityMailbox : blocks design #272
```

```mermaid
flowchart TD
  Pay[paying client] --> VM[EC2 or GCE — provider undecided]
  VM --> PII[profile.yaml + vault on VM]
  VM --> Limit[datacenter IP — measured 403s]
  Limit --> NoProxy[no proxies / stealth]
  OpenQ[open questions] --> Close[written answers]
  Close --> Mail[#272 mailbox design may start]
```

Reglas: issue = registro de decisión, no Terraform; PII por máquina; OTP/CAPTCHA humanos; no JobBot Cloud multi-tenant ni telemetría.

## Identity mailbox + thin mobile client {#identity-mailbox-client}

Patrones: **Decision Record**, **Identity Mailbox**, **Thin Client**. Issue: #272 (bloqueado por #274; feedback #154; WhatsApp hacia persona #251; posicionamiento #266).

```mermaid
classDiagram
  direction TB
  class IdentityMailbox {
    <<Decision>>
    +owner workspace|person|discarded
    +form_address VM|profile.yaml
  }
  class ThinFlutterClient {
    <<Client>>
    +capture URL
    +status
    +confirm HITL
  }
  class IsolatedClientVm {
    <<Boundary>>
  }
  class PastedFeedback {
    <<Command>>
    +#154 funnel
  }
  IsolatedClientVm ..> IdentityMailbox : blocks design until answered
  IdentityMailbox --> PastedFeedback : paste still valid if no mailbox
  ThinFlutterClient --> LocalCli : same loop, not second product
  note for IdentityMailbox "JobBot never reads OTP\nno OAuth personal Gmail\nno auto-send"
```

```mermaid
flowchart TD
  Q1[mailbox owner?] --> A1[written answer]
  Q2[form address?] --> A2[written answer]
  Q3[Flutter in or out?] --> A3[written answer]
  A1 --> Close[issue closed]
  A2 --> Close
  A3 --> Close
  Close -->|mailbox kept| Design[design after #274]
  Close -->|Flutter thin| Proto[prototype later]
  Close -.->|forbidden| No[OAuth inbox / OTP bot / dashboard twin]
```

Reglas: correo = domicilio de postulación, no agente que lea bandeja; Flutter no reemplaza la terminal; CAPTCHA/2FA/OTP humanos.

## Stolen AI Apply outcomes — HITL map {#stolen-ai-apply-outcomes}

Patrones: **Stolen-Outcome Map**, **Anti-pattern table**, **HITL Command**. Issue: #155 (ciclo #154; cola #75; asesoria #130; presencia #150; no clonar #266).

```mermaid
classDiagram
  direction TB
  class StolenOutcome {
    <<Row>>
    +str outcome
    +str jobbot_form
    +str|None issue
  }
  class AiApplyOutcomeMap {
    <<Inventory>>
  }
  class AntiPattern {
    <<Forbidden>>
    autopilot
    spray_cv
    gmail_oauth_inbox
    cloud_agent_while_asleep
  }
  AiApplyOutcomeMap *-- StolenOutcome
  AiApplyOutcomeMap ..> AntiPattern : never ship
  StolenOutcome --> PlanApply : prefill / queue HITL
  StolenOutcome --> CapabilityGapMap : when contract missing
```

```mermaid
flowchart LR
  Reel[AI Apply reel claim] --> Filter{HITL + local?}
  Filter -->|no| Drop[anti-pattern #105]
  Filter -->|yes| Row[outcome → JobBot form → issue]
  Row --> Close154[#154 feedback + report]
  Row --> Msg130[#130 hard-way message]
  Row --> Erg75[#75 HITL queue ≠ volume KPI]
```

Reglas: robar resultados medibles, no el medio de créditos-por-envío; Review mode de ellos ≈ único modo nuestro.

## Commons vs traveller — GCP if ever {#commons-vs-traveller}

Patrones: **Bounded Context**, **Anti-corruption** del nombre, **Decision Record**. Issue: #162 (federación #106; advisor #129; vault #157; VM #274).

```mermaid
classDiagram
  direction TB
  class Traveller {
    <<Bounded Context>>
    +profile.yaml
    +vault
    +browser
    +apply
  }
  class Commons {
    <<Bounded Context>>
    +companies export
    +portals
    +zero candidate PII
  }
  class JobBotName {
    <<Brand>>
  }
  class OptionalGcpBucket {
    <<Later>>
    +public snapshots
  }
  JobBotName --> Traveller : this name only
  Commons --> GitMerge : #106 first
  Commons ..> OptionalGcpBucket : after merge hurts
  Traveller ..> OptionalGcpBucket : never hosts apply
  note for OptionalGcpBucket "no Cloud Run Playwright\nno Cloud SQL profiles\nno Secret Manager vault"
```

```mermaid
flowchart TD
  Ask[GCP under JobBot?] --> No[keep name on local CLI]
  No --> Map[commons / el mapa]
  Map --> File[#106 file merge HITL]
  File -->|enough| Stay[git is commons]
  File -->|not enough| Bucket[public export bucket]
  Bucket --> Guard[pii_guard at edge]
```

Reglas: colaboración = el mapa, no el viajero; datacenter IP descalifica JobBot en GCE/Cloud Run contra portales.

## Namesake JobBot use-cases {#namesake-usecase-map}

Patrones: **Stolen-Outcome Map**, **Anti-pattern table**, **Never invent**. Issue: #164 (filtro #155 / #105; marca dual #261; gaps #32 #34 #84 #154).

```mermaid
classDiagram
  direction TB
  class NamesakeRow {
    <<Row>>
    +str source
    +str outcome
    +str jobbot_form
    +str|None issue
  }
  class NamesakeUsecaseMap {
    <<Inventory>>
  }
  class NamesakeForbidden {
    <<Anti-pattern>>
    auto_submit
    hosted_cv
    datacenter_cron
    cold_email
    sheets_tracker
    llm_vision_extension
    esco_as_gate
    invent_bullets
  }
  NamesakeUsecaseMap *-- NamesakeRow
  NamesakeUsecaseMap ..> NamesakeForbidden : never ship
  NamesakeRow --> ExistingIssues : #33 #34 #84 #154 …
  NamesakeUsecaseMap --> CapabilityGapMap : falsifiable contracts
```

```mermaid
flowchart LR
  Hom[jobbot.io / Devpost / …] --> F{same filter as #155?}
  F -->|throughput medium| Out[drop]
  F -->|honest outcome| Map[row → shipped or open issue]
  Map --> Prior[prior-art.md one-liner]
  Map --> NoParallel[no parallel tracker]
```

Reglas: no pelear la marca; huecos en issues ya abiertos; ESCO no decide el oficio; detector de invención intacto.

## Cómo citar desde un issue

```markdown
## SDD / patrones
- SDD: docs/software-design.md §3 / §8
- Patrón(es): Value Object, Aggregate
- UML: docs/uml.md#fact-preference
- El PR actualiza el diagrama si introduce o renombra un tipo
```
