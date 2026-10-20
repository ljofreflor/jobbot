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
| #141 | Value Object | [fact-preference](uml.md#fact-preference) | body_ready | [141](sdd-issue-patches/141.md) |
| #144 | Value Object, Aggregate | [fact-preference](uml.md#fact-preference) | body_ready | [144](sdd-issue-patches/144.md) |
| #185 | Value Object | [fact-preference](uml.md#fact-preference) | body_ready | [185](sdd-issue-patches/185.md) |
| #195 | Association, EvidenceStrength | [fact-preference](uml.md#fact-preference) | body_ready | [195](sdd-issue-patches/195.md) |
| #206 | Aggregate (Preferences) | [fact-preference](uml.md#fact-preference) | body_ready | [206](sdd-issue-patches/206.md) |
| #221 / #400 | Overlay / Projection | [fact-preference](uml.md#fact-preference) | body_ready | [221](sdd-issue-patches/221.md) |
| #166 | Specification | [specification](uml.md#specification) | body_ready | [166](sdd-issue-patches/166.md) |
| #186 | Specification + Command | [specification](uml.md#specification) · [plan-apply](uml.md#plan-apply) | body_ready | [186](sdd-issue-patches/186.md) |
| #94 | ACL | [acl](uml.md#acl) | body_ready | [94](sdd-issue-patches/94.md) |
| #203 | Specification + Command | [plan-apply](uml.md#plan-apply) | body_ready | [203](sdd-issue-patches/203.md) |
| #178 | PostingClarity (VO) | [specification](uml.md#specification) | body_ready | [178](sdd-issue-patches/178.md) |

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
