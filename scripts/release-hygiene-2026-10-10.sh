#!/usr/bin/env bash
# Friday release hygiene (10 oct 2026). Run with a token that can write issues:
#   ./scripts/release-hygiene-2026-10-10.sh
# The cloud agent token can push code but cannot close/comment issues (403).
set -euo pipefail

comment_close_dup() {
  local newer=$1
  local canonical=$2
  gh issue comment "$newer" --body "Duplicate of #${canonical} (identical body created seconds apart; keeping the older issue as canonical). Evidence and acceptance stay on #${canonical}."
  gh issue close "$newer" --reason "not planned" --comment "Duplicate of #${canonical}."
  echo "Closed #${newer} as duplicate of #${canonical}"
}

echo "== Duplicates (keep oldest) =="
comment_close_dup 250 249
comment_close_dup 223 222
comment_close_dup 200 199

echo "== Close train issues if still open (also referenced from main empty commit) =="
for n in 193 211 212 249 252 253 142; do
  state=$(gh issue view "$n" --json state -q .state)
  if [[ "$state" == "OPEN" ]]; then
    gh issue close "$n" --reason "completed" --comment "Shipped on main in the 10 oct 2026 release (develop → main)."
    echo "Closed #${n}"
  else
    echo "#${n} already ${state}"
  fi
done

echo "== Rewrite #240 (Empleos Públicos remaining work) =="
gh issue comment 240 --body "$(cat <<'EOF'
## Estado parcial (10 oct 2026)

Ya en el árbol:

- **#153** (merged): fuente `empleos_publicos` fixture-first + hard-link; sin `--fixture` la búsqueda en vivo aún no es el camino por defecto en `main`/`develop` previo a PR #198.
- **PR #198** (si/cuando mergea): ADP reconocida pero no leída (`robots.txt`); `empleospublicos search` en vivo vía CSV open-data del Servicio Civil (`eepp_convocatorias.csv`), solo abiertos, cierre/renta en el texto para `jobs conditions`.

Este issue **no** se cierra con #198: el CSV no es lo mismo que los feeds JSON del portal.
EOF
)"

gh issue edit 240 --body "$(cat <<'EOF'
## Contexto (recorte 10 oct 2026)

La búsqueda en vivo de Empleos Públicos ya tiene (o tendrá con #198) un camino por **CSV open-data** del Servicio Civil. Lo que **sigue faltando** es ingerir los **dos feeds JSON** del portal (`empleospublicos.cl`) que alimentan el listado real de convocatorias, con dedupe y HITL cuando hay 403.

## Ya cubierto (no rehacer)

- Fuente fixture-first + hard-link ([#153](https://github.com/ljofreflor/jobbot/pull/153)).
- Camino CSV open-data + reconocimiento ADP sin scrape ([#198](https://github.com/ljofreflor/jobbot/pull/198)) — cuando ese PR esté en `develop`/`main`.
- Cierre/renta embebidos en el texto del aviso para `jobs conditions` (enfoque de #198); si el modelo gana `closes_at` / `salary_text` eso vive en [#180](https://github.com/ljofreflor/jobbot/issues/180), no bloquea este issue.

## Trabajo restante

1. Leer en vivo (o vía CDP HITL si HTTP 403) los feeds:
   - `https://www.empleospublicos.cl/data/convocatorias2_nueva.txt`
   - `https://www.empleospublicos.cl/data/convocatorias2.txt`
2. Normalizar a `JobPosting`, deduplicar entre feeds y contra lo ya guardado.
3. Exponer el camino en `jobs discover --source empleos_publicos` / `empleospublicos search` **sin** `--fixture` cuando los feeds respondan; si 403, mensaje claro + sugerencia CDP (sin bypass de CAPTCHA).
4. Tests con fixtures anonimizados de ambos feeds; sin red en la suite.

## Criterios de aceptación

- [ ] Con fixtures de ambos feeds, el parser produce avisos abiertos sin duplicar el mismo concurso.
- [ ] Sin `--fixture`, si los feeds responden, se guardan avisos; si 403, mensaje accionable (no “no hay nada”).
- [ ] Suite offline verde; sin PII en fixtures.

## Relacionados

#153 · #198 · #180 · #228 (ADP)
EOF
)"

echo "== Epic #214: link children #215–#220 =="
gh issue comment 215 --body "Part of #214 (Workday epic)."
gh issue comment 216 --body "Part of #214 (Workday epic). Tenant-specific session gate; distinct from generic browser sessions."
gh issue comment 217 --body "Part of #214 (Workday epic). Related branches to check: \`cursor/field-homologation-aa4f\`, \`feature/94-field-homologation\` — not on develop until merged."
gh issue comment 218 --body "Part of #214 (Workday epic)."
gh issue comment 219 --body "Part of #214 (Workday epic)."
gh issue comment 220 --body "Part of #214 (Workday epic)."

gh issue edit 214 --body "$(cat <<'EOF'
## Contexto y problema

Una candidata no técnica (salud pública, Chile) postula a un organismo internacional de salud y a farmacéuticas/diagnóstico que usan **Workday**. El recorrido completo hoy se hace a mano: descubrir, vigilar cierre, guardar aviso, mantener un perfil por tenant y postular con HITL.

## Hijos (un issue = un criterio comprobable)

- [ ] #215 — `jobbot get` / `jobs add --url` descargan el aviso vía CXS (detalle, cierre con zona del tenant, `canApply`)
- [ ] #216 — una cuenta/sesión por tenant Workday (`browser sessions`, `login_gate`)
- [ ] #217 — `apply_fill` usa `data-automation-id` + tabla de homologación en pasos Workday
- [ ] #218 — auditoría read-only del perfil de candidato vs SST (`portals profile diff workday --tenant`)
- [ ] #219 — llenar perfil desde el SST por sección (`portals profile push workday --tenant --apply`)
- [ ] #220 — postulación asistida paso a paso; se detiene antes de Submit

## Fuera de alcance de la épica

- Descubrimiento masivo de tenants (puede vivir en discover Workday aparte).
- Auto-submit o bypass de CAPTCHA/2FA.

## Definición de terminado

Cada hijo cerrado con sus tests; la épica se cierra cuando los seis están hechos o explícitamente wontfix.
EOF
)"

echo "== Note #142 / #143 stay distinct =="
gh issue comment 143 --body "Sigue separado de #142 (validate vs render). #142 shipped on main 10 oct 2026; este issue sigue abierto hasta que el CV por cargo respete \`selection.skill_names\` / formación."

echo "Done. Verify with: gh issue list --state open --limit 30"
