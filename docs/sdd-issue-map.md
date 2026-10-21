---
title: SDD ← issues map
description: Which open issues advance which design patterns and UML anchors. Loop updates status.
---

# SDD ← issues map

Cada issue de dominio debe mejorar el [SDD](software-design.md) y quedar
reflejado en [UML](uml.md). Esta tabla es el backlog del loop: `pending` =
falta sección `## SDD / patrones` en el issue (o el diagrama target aún no
existe); `body_ready` = texto listo en `docs/sdd-issue-patches/`; `done` =
issue ya cita UML y el diagrama está al día.

| Issue | Patrón(es) | UML | Status | Patch |
| --- | --- | --- | --- | --- |
| #141 | Value Object | [fact-preference](uml.md#fact-preference) | done | [141](sdd-issue-patches/141.md) |
| #144 | Value Object, Aggregate | [fact-preference](uml.md#fact-preference) | done | [144](sdd-issue-patches/144.md) |
| #185 | Value Object | [fact-preference](uml.md#fact-preference) | done | [185](sdd-issue-patches/185.md) |
| #195 | Association, EvidenceStrength | [fact-preference](uml.md#fact-preference) | done | [195](sdd-issue-patches/195.md) |
| #206 | Aggregate (Preferences) | [fact-preference](uml.md#fact-preference) | done | [206](sdd-issue-patches/206.md) |
| #221 | Overlay / Projection | [fact-preference](uml.md#fact-preference) | done | [221](sdd-issue-patches/221.md) |
| #400 | Overlay / Projection | [fact-preference](uml.md#fact-preference) | done | [400](sdd-issue-patches/400.md) |
| #166 | Specification | [specification](uml.md#specification) | done | [166](sdd-issue-patches/166.md) |
| #186 | Specification + Command | [specification](uml.md#specification) · [plan-apply](uml.md#plan-apply) | done | [186](sdd-issue-patches/186.md) |
| #94 | ACL | [acl](uml.md#acl) | done | [94](sdd-issue-patches/94.md) |
| #203 | Specification + Command | [plan-apply](uml.md#plan-apply) | done | [203](sdd-issue-patches/203.md) |
| #178 | PostingClarity (VO) | [specification](uml.md#specification) | done | [178](sdd-issue-patches/178.md) |
| #404 | Strategy (CV variant) | [ports](uml.md#ports) | done | [404](sdd-issue-patches/404.md) |
| #303 | Preferences aggregate + ACL | [fact-preference](uml.md#fact-preference) · [acl](uml.md#acl) | done | [303](sdd-issue-patches/303.md) |
| #265 | Registry + Factory / DI | [ports](uml.md#ports) | done | [265](sdd-issue-patches/265.md) |
| #218 | ProfileAdapter + Snapshot diff | [ports](uml.md#ports) · [acl](uml.md#acl) | done | [218](sdd-issue-patches/218.md) |
| #414 | Command (import HITL) | [plan-apply](uml.md#plan-apply) | done | [414](sdd-issue-patches/414.md) |
| #382 | VO deadline + selection plan | [specification](uml.md#specification) · [plan-apply](uml.md#plan-apply) | done | [382](sdd-issue-patches/382.md) |
| #219 | WritableProfileAdapter + ACL | [ports](uml.md#ports) · [plan-apply](uml.md#plan-apply) · [acl](uml.md#acl) | done | [219](sdd-issue-patches/219.md) |
| #150 | Profile ports epic | [ports](uml.md#ports) · [plan-apply](uml.md#plan-apply) | done | [150](sdd-issue-patches/150.md) |
| #284 | WritableProfileAdapter (LinkedIn sections) | [ports](uml.md#ports) · [plan-apply](uml.md#plan-apply) | done | [284](sdd-issue-patches/284.md) |
| #207 | Strategy check-open + Verdict | [ports](uml.md#ports) · [specification](uml.md#specification) | done | [207](sdd-issue-patches/207.md) |
| #140 | presentations VO + Strategy | [ports](uml.md#ports) · [fact-preference](uml.md#fact-preference) | done | [140](sdd-issue-patches/140.md) |
| #416 | Command rejection proposal | [plan-apply](uml.md#plan-apply) | done | [416](sdd-issue-patches/416.md) |
| #406 | ACL form gap + HITL | [acl](uml.md#acl) · [plan-apply](uml.md#plan-apply) | done | [406](sdd-issue-patches/406.md) |
| #220 | Apply port step-by-step | [ports](uml.md#ports) · [plan-apply](uml.md#plan-apply) | done | [220](sdd-issue-patches/220.md) |
| #157 | Local vault (not Candidate) | [ports](uml.md#ports) | done | [157](sdd-issue-patches/157.md) |
| #392 | Guard TTY + HITL pause (Indeed challenge) | [hitl-pause](uml.md#hitl-pause) · [plan-apply](uml.md#plan-apply) | body_ready | [392](sdd-issue-patches/392.md) |
| #390 | SearchOutcome: empty ≠ failed ≠ off-topic | [search-outcome](uml.md#search-outcome) · [ports](uml.md#ports) | body_ready | [390](sdd-issue-patches/390.md) |
| #388 | Command `jobs add --url` / `jobs verify` | [posting-url-verify](uml.md#posting-url-verify) · [ports](uml.md#ports) | body_ready | [388](sdd-issue-patches/388.md) |
| #386 | ProfileAdapter LinkedIn /details/ | [linkedin-details-pull](uml.md#linkedin-details-pull) · [ports](uml.md#ports) | body_ready | [386](sdd-issue-patches/386.md) |
| #384 | LLM extract JD (never invent) | [jd-llm-extract](uml.md#jd-llm-extract) · [ports](uml.md#ports) | body_ready | [384](sdd-issue-patches/384.md) |
| #398 | Mutex `jobbot update` | [update-mutex](uml.md#update-mutex) · [plan-apply](uml.md#plan-apply) | body_ready | [398](sdd-issue-patches/398.md) |
| #412 | Indeed Apply advance, no Submit | [indeed-apply-advance](uml.md#indeed-apply-advance) · [ports](uml.md#ports) · [plan-apply](uml.md#plan-apply) | body_ready | [412](sdd-issue-patches/412.md) |
| #410 | postulate --apply + promote aparte | [postulate-route](uml.md#postulate-route) · [plan-apply](uml.md#plan-apply) · [ports](uml.md#ports) | body_ready | [410](sdd-issue-patches/410.md) |
| #408 | cv build derived translation | [cv-derived-translation](uml.md#cv-derived-translation) · [fact-preference](uml.md#fact-preference) · [ports](uml.md#ports) | body_ready | [408](sdd-issue-patches/408.md) |
| #420 | Tutorial entry door only | docs (no UML) | body_ready | [420](sdd-issue-patches/420.md) |
| #418 | Public queue sync PR + `-U` | [public-queue-sync](uml.md#public-queue-sync) · [ports](uml.md#ports) · [acl](uml.md#acl) | body_ready | [418](sdd-issue-patches/418.md) |
| #424 | ai-job-search gaps → contracts | [capability-gap-map](uml.md#capability-gap-map) · [ports](uml.md#ports) | body_ready | [424](sdd-issue-patches/424.md) |
| #402 | Strategy attach_cv + no Submit | [indeed-apply-attach](uml.md#indeed-apply-attach) · [ports](uml.md#ports) · [plan-apply](uml.md#plan-apply) | body_ready | [402](sdd-issue-patches/402.md) |
| #374 | Preference SearchFilters + dry-run | [search-filters](uml.md#search-filters) · [fact-preference](uml.md#fact-preference) · [plan-apply](uml.md#plan-apply) | body_ready | [374](sdd-issue-patches/374.md) |
| #54 | Command cv tune-for (budget + HITL) | [cv-tune-for](uml.md#cv-tune-for) · [plan-apply](uml.md#plan-apply) · [fact-preference](uml.md#fact-preference) | body_ready | [54](sdd-issue-patches/54.md) |
| #285 | WritableProfileAdapter + field limits | [trabajando-profile-push](uml.md#trabajando-profile-push) · [ports](uml.md#ports) · [acl](uml.md#acl) | body_ready | [285](sdd-issue-patches/285.md) |

## Cómo aplicar un patch (HITL, token con write)

```bash
# Una vez logueado como owner (gh auth login --web):
BODY=$(gh issue view 141 --json body -q .body)
PATCH=$(cat docs/sdd-issue-patches/141.md)
gh issue edit 141 --body "${BODY}

${PATCH}"
```

O pegar a mano la sección del patch bajo el cuerpo actual.

## Contrato del loop

1. Elegir la siguiente fila `pending`.
2. Escribir `docs/sdd-issue-patches/N.md` con `## SDD / patrones` + criterio UML.
3. Si hace falta un tipo nuevo, actualizar `docs/uml.md` y §8 del SDD.
4. Marcar la fila `body_ready`.
5. Si `gh issue edit` tiene permiso, aplicar y marcar `done`; si no, dejar patch.
