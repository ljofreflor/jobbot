"""Parse free-text job descriptions into JobPosting fields."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from jobbot.jobs.normalization import fold_text, normalize_skill
from jobbot.models.job import JobPosting

_HEADER_FIELD_RE = re.compile(
    r"(?i)^(title|role|cargo|puesto|company|empresa|organization|location|"
    r"ubicacion|ubicación|city|seniority|url|source)\s*[:\-]"
)
_SECTION_HEADING_RE = re.compile(
    r"(?i)^(?:required\s+|minimum\s+|preferred\s+|desired\s+)?"
    r"(requirements?|requisitos|qualifications|calificaciones|skills|habilidades|"
    r"competencias|conocimientos|herramientas|tecnolog[ií]as|stack|nice to have|"
    r"deseable|responsabilidades|responsibilities|beneficios|benefits|funciones|tareas|"
    r"duties|education|educaci[oó]n|descripci[oó]n|perfil|objetivo|prop[oó]sito|purpose|"
    r"sobre el cargo|el cargo|about the (?:role|job|position)|about\b.*)"
    r"(?:\s+\w+){0,2}\s*:?\s*$"
)
# Sections that describe the employer or what it offers: nothing in them is asked of
# the candidate, so no requirement is read until the next heading.
_NON_REQUIREMENT_SECTION_RE = re.compile(
    r"(?i)^(?:acerca\s+de\b.*|sobre\s+(?:nosotros|la\s+empresa|la\s+compa[nñ][ií]a)|"
    r"qui[eé]nes\s+somos|nuestra\s+empresa|"
    r"about(?!\s+(?:the\s+)?(?:role|job|position|you|this|team)\b)(?:\s+\S+){0,6}|"
    r"who\s+we\s+are|our\s+company|beneficios|benefits|what\s+we\s+offer|"
    r"(?:te\s+)?ofrecemos)\s*:?\s*$"
)
# Links, domains, file names, addresses and handles are page furniture, never a skill.
_URLISH_RE = re.compile(
    r"https?://\S+|www\.\S+|\S+@\S+\.\S+|(?<!\w)@\w+"
    r"|\b[\w-]+(?:\.[\w-]+)*\.(?:com|org|net|edu|gov|int|io|cl|ar|mx|co|pe|es)\b\S*"
    r"|\b[\w-]+\.(?:php|aspx?|html?|jsp|pdf)\b"
)
_SOCIAL_RE = re.compile(
    r"(?i)\b(?:s[ií]guenos|follow\s+us|share\s+(?:on|this)|comparte|compartir\s+en)\b"
)

# A requirement line names the skill after a lead-in: 'Experiencia en X', 'Manejo de Y'.
_LEAD_IN_RE = re.compile(
    r"(?i)^(?:"
    r"experiencia(?:\s+(?:previa|comprobable|demostrable))?(?:\s+en|\s+con|\s+in)?|"
    r"experience\s+(?:with|in)|"
    r"manejo\s+(?:de|del)|dominio\s+(?:de|del)|conocimientos?\s+(?:de|del|en)|"
    r"t[ií]tulo\s+(?:de|en)|formaci[oó]n\s+(?:en|de)|"
    r"capacidad\s+(?:de|para)|habilidad(?:es)?\s+(?:de|en|para)|"
    r"deseable|excluyente|requerido|required|strong|solid|proven|comfortable\s+with|"
    r"s[oó]lidos?|al menos|m[ií]nimo|minimum|"
    r"necesitamos|buscamos|se\s+requiere|we\s+need|need|nice\s+to\s+have|"
    r"\d+\s*\+?\s*(?:a[nñ]os|years)(?:\s+(?:de|of))?"
    r"(?:\s+(?:experiencia|experience))?(?:\s+(?:en|in|con|with))?"
    r")\b[\s:,-]*"
)
# A fragment that ends on a preposition or starts on a conjunction is a cut phrase.
_DANGLING_RE = re.compile(
    r"(?i)(^(?:y|e|o|u|and|or|el|la|los|las|un|una|unos|unas|the)\s+"
    r"|\s+(?:de|del|en|con|para|of|in|with|for|a|al)$)"
)
_TRAILING_NOISE_RE = re.compile(
    r"(?i)[\s,;]*\b(preferred|preferible|deseable|excluyente|requerido|required|"
    r"experiencia|experience|methods?|avanzad[oa]s?|b[aá]sic[oa]s?|vigente|"
    r"similar|afines?|af[ií]n)\b[\s.]*$"
)
# Enumerations: 'X y Z', 'X, Z', 'X / Z', 'X en Z'. Never ' de ': it splits real names.
_ITEM_SPLIT_RE = re.compile(r"(?i)(?:\s*[,;|]\s*|\s+/\s+|\s+(?:y|e|o|u|and|or|en|for|para)\s+)")
_PARENS_RE = re.compile(r"[()\[\]]")
_LANGUAGE_RE = re.compile(
    r"(?i)\b(english|spanish|ingl[eé]s|espa[nñ]ol|portugu[eé]s|portuguese|"
    r"idioma|language|proficiency|nativo|native|biling[uü]e)\b"
)
# Typography marks a tool name inside prose: SEO, WordPress, BigQuery, C++, A/B.
_TOOL_TOKEN_RE = re.compile(
    r"\b(?:[A-Z]{2,}[0-9]*|[A-Z][a-z0-9]+(?:[A-Z][a-zA-Z0-9]+)+|"
    r"[A-Za-z]+(?:\+\+|#|\.[a-z]{2,}))\b"
)
# In prose, typography alone is not enough: institutions, programmes and legal
# footers are written in capitals too. A tool name counts only in a clause that
# says it is used or known ('experiencia en SAP', 'proficiency with BigQuery').
_PROSE_LEAD_RE = re.compile(
    r"(?i)\b(?:manejo|dominio|uso|conocimientos?|experiencia|herramientas?|software|"
    r"plataformas?|lenguajes?|certificaci[oó]n(?:es)?|experience|knowledge|proficiency|"
    r"proficient|skills?|expertise|familiarity|using|tools?|stack)\b"
)
_CLAUSE_SPLIT_RE = re.compile(r"[.;:!?](?:\s+|$)")
_ITEM_MAX_WORDS = 5
_PROSE_MIN_WORDS = 13

# A career page carries its own chrome: deadlines, clock times, pay figures and
# upper-case section headings. None of it is something a candidate can have.
_MONTH = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|"
    r"sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?|"
    r"enero|ene|febrero|marzo|abril|abr|mayo|junio|julio|agosto|ago|"
    r"septiembre|setiembre|octubre|noviembre|diciembre|dic)"
)
_DATE_RE = re.compile(
    rf"(?i)\b\d{{4}}-\d{{1,2}}-\d{{1,2}}\b|\b\d{{1,2}}/\d{{1,2}}/\d{{2,4}}\b"
    rf"|\b\d{{1,2}}\s+(?:de\s+)?{_MONTH}\b|\b{_MONTH}\.?\s+\d{{1,4}}\b"
)
_CLOCK_RE = re.compile(r"(?i)\b\d{1,2}:\d{2}\b(?:\s*[ap]\.?\s?m\b\.?)?")
_CURRENCY_CODES = frozenset({"USD", "CLP", "EUR", "UF", "UTM", "US$"})
_MONEY_RE = re.compile(
    r"[$€£]\s*\d|\d[\d.,]*\s*(?:USD|CLP|EUR|UF|UTM)\b|\b(?:USD|CLP|EUR)\s*\d"
)
_LABEL_VALUE_RE = re.compile(r"^[^:\d]{1,40}:\s*\S*\d")
_HEADING_MIN_WORDS = 3
# Field labels career sites (Workday, Taleo, public boards) print next to their values.
_PAGE_FIELD_LABELS = frozenset(
    {
        "job posting",
        "posting date",
        "closing date",
        "deadline",
        "primary location",
        "location",
        "contractual agreement",
        "contract type",
        "schedule",
        "full time",
        "part time",
        "off site",
        "on site",
        "grade",
        "salary",
        "salary annually",
        "post adjustment annually",
        "duration",
        "job id",
        "requisition id",
        "fecha de cierre",
        "fecha de publicacion",
        "jornada",
        "tipo de contrato",
        "renta",
        "sueldo",
        # Workday prints each label on its own line and the value on the next.
        "locations",
        "time type",
        "posted on",
        "time left to apply",
        "end date",
        "job requisition id",
        "job family",
        # Public-sector boards (fichas) label their rows the same way.
        "titulo aviso",
        "no de vacantes",
        "n de vacantes",
        "vacantes",
        "ciudad",
        "region",
        "renta bruta",
        "rango",
        "grado",
    }
)
# Page chrome with no value of its own: buttons, table headings, reference numbers.
_PAGE_CHROME_WORDS = frozenset(
    {
        "apply",
        "apply now",
        "postular",
        "postula",
        "postula aqui",
        "deliverables",
        "deliverable",
        "deliverable date",
        "entregables",
        "product",
        "products",
        "producto",
        "value",
        "total",
        "amount",
        "monto",
        "reqid",
        "req id",
        "n",
        "no",
        "nro",
        "numero",
    }
)
# A deliverables table numbers its rows: 'Product 2: Training plan', 'Producto 1 - Informe'.
_DELIVERABLE_ROW_RE = re.compile(
    r"(?i)^(?:product|producto|deliverable|entregable)\s*\d+\s*[:.\-–]"
)


def looks_like_page_metadata(phrase: str) -> bool:
    """Deadlines, times, salary figures, links and page labels are chrome, not skills."""
    text = phrase.strip()
    if not text:
        return False
    folded = fold_text(text)
    bare = " ".join(re.sub(r"\d", " ", folded).split())
    if text in _CURRENCY_CODES or folded in _PAGE_FIELD_LABELS:
        return True
    if bare in _PAGE_FIELD_LABELS or bare in _PAGE_CHROME_WORDS:
        return True
    if _URLISH_RE.search(text) or _SOCIAL_RE.search(text) or _DELIVERABLE_ROW_RE.match(text):
        return True
    if ":" in text:
        label_part = fold_text(text.split(":", 1)[0].strip())
        if label_part in _PAGE_FIELD_LABELS:
            # ATS rows like "Primary Location: Santiago" (value has no digit).
            return True
    if _DATE_RE.search(text) or _CLOCK_RE.search(text) or _MONEY_RE.search(text):
        return True
    if _LABEL_VALUE_RE.match(text):
        return True
    lettered = [word for word in text.split() if any(char.isalpha() for char in word)]
    return len(lettered) >= _HEADING_MIN_WORDS and all(word.isupper() for word in lettered)

_ITEM_STOPWORDS = frozenset(
    {
        "experiencia",
        "experience",
        "conocimiento",
        "conocimientos",
        "manejo",
        "titulo",
        "años",
        "anos",
        "years",
        "equipo",
        "equipos",
        "team",
        "trabajo",
        "work",
        "capacidad",
        "disponibilidad",
        "rol",
        "role",
        "cargo",
        "puesto",
        "empresa",
        "company",
        "cliente",
        "clientes",
        "nosotros",
        "buscamos",
        "vigente",
        "otros",
        "otras",
        "afin",
        "similar",
        "carrera",
    }
)

# A degree requirement names a field of study, and only a degree in that field meets
# it: 'Título de Ingeniería Comercial' is not met by 'Ingeniería en Alimentos' plus a
# job title that says 'comercial'.
_DEGREE_LEAD_RE = re.compile(
    r"^(?:(?:university|bachelor'?s?|master'?s?|advanced|first|academic|postgraduate|"
    r"graduate)\s+)*"
    r"(?:(?:titulo(?:\s+(?:profesional|universitario|tecnico))?|grado(?:\s+academico)?|"
    r"licenciatura|licenciado|degree|profesional(?=\s+(?:de|del|en|in|of)\b))"
    r"(?:\s+(?:de\s+la|de|del|en|in|of|from|a|an))*\s+|(?=ingenieria\s+(?!de\b|del\b)))"
    r"(?P<field>.+)$"
)
_DEGREE_QUALIFIER_RE = re.compile(
    r"\s+(?:con|with|que|para|for|including|incluyendo|preferentemente|preferably)\s+.*$|\(.*$"
)
_DEGREE_ALTERNATIVES_RE = re.compile(r"\s*[,;/]\s*|\s+(?:o|u|or|y|e|and)\s+")
_DEGREE_FILLER = frozenset(
    {
        "area",
        "areas",
        "carrera",
        "carreras",
        "afin",
        "afines",
        "similar",
        "similares",
        "related",
        "relevant",
        "equivalent",
        "equivalente",
        "field",
        "fields",
        "otra",
        "otras",
        "other",
        "disciplina",
        "discipline",
        "universitario",
        "universitaria",
        "profesional",
        "vigente",
        "relacionada",
        "relacionado",
        "relacionadas",
        "relacionados",
    }
)
_DEGREE_MAX_WORDS = 20


def _deaccent(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(char for char in nfkd if not unicodedata.combining(char))


def degree_fields(requirement: str) -> list[str] | None:
    """Fields of study a degree requirement accepts, folded; None if it asks no degree.

    'University degree in veterinary medicine, epidemiology or public health' →
    ['veterinary medicine', 'epidemiology', 'public health']. Filler such as 'área',
    'carrera afín' or 'related field' is dropped; a qualifier after 'con'/'with'
    ('con registro vigente') is not part of the field.
    """
    text = _deaccent(" ".join(requirement.split())).strip(" .;:-•*")
    match = _DEGREE_LEAD_RE.match(text)
    if match is None:
        return None
    field = _DEGREE_QUALIFIER_RE.sub("", match.group("field"))
    alternatives: list[str] = []
    for part in _DEGREE_ALTERNATIVES_RE.split(field):
        words = [
            word
            for word in fold_text(part).split()
            if len(word) >= 4 and word not in _DEGREE_FILLER
        ]
        if words and " ".join(words) not in alternatives:
            alternatives.append(" ".join(words))
    return alternatives or None


def parse_job_text(
    text: str,
    *,
    job_id: str,
    source: str = "manual",
    url: str | None = None,
) -> JobPosting:
    """Best-effort parse of a pasted JD into a JobPosting."""
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    title = _field(lines, "title", "role", "cargo", "puesto") or (lines[0] if lines else "Untitled")
    company = _field(lines, "company", "empresa", "organization") or "Unknown"
    location = _field(lines, "location", "ubicacion", "ubicación", "city")
    seniority = _infer_seniority(text)
    remote_type = _infer_remote(text)
    skills = _extract_skills(text)
    requirements = _extract_requirements(text)
    languages = _extract_languages(text)

    description = text.strip()
    return JobPosting(
        id=job_id,
        source=source,
        url=url,
        title=title,
        company=company,
        location=location,
        description=description,
        raw_description=text,
        requirements=requirements,
        skills=skills,
        seniority=seniority,
        language_requirements=languages,
        remote_type=remote_type,
    )


def job_to_dict(job: JobPosting) -> dict[str, Any]:
    return job.model_dump(mode="json")


def _field(lines: list[str], *keys: str) -> str | None:
    for line in lines:
        for key in keys:
            match = re.match(rf"(?i)^{re.escape(key)}\s*[:\-]\s*(.+)$", line)
            if match:
                return match.group(1).strip()
    return None


def _infer_seniority(text: str) -> str | None:
    lower = text.lower()
    for label in ("staff", "principal", "senior", "semi-senior", "mid", "junior", "lead"):
        if re.search(rf"\b{re.escape(label)}\b", lower):
            return label
    return None


def _infer_remote(text: str) -> str | None:
    lower = text.lower()
    if "remote" in lower or "remoto" in lower:
        return "remote"
    if "hybrid" in lower or "híbrido" in lower or "hibrido" in lower:
        return "hybrid"
    if "on-site" in lower or "presencial" in lower:
        return "onsite"
    return None


def extract_skills_from_text(text: str) -> list[str]:
    """Public alias used by job sources that skip parse_job_text."""
    return _extract_skills(text)


def _extract_skills(text: str) -> list[str]:
    """Read the skills the JD itself names, whatever the field.

    A closed vocabulary only ever finds the domain it was written for, so the
    signal here is the shape of the text: list items name skills after a lead-in
    ('Manejo de reanimación cardiopulmonar'), and prose only gives up a name when
    its typography says tool ('SEO', 'WordPress', 'C++').
    """
    found: list[str] = []
    seen: set[str] = set()

    for raw_block in _text_blocks(text):
        block = " ".join(_URLISH_RE.sub(" ", raw_block).split())
        max_words = _ITEM_MAX_WORDS
        if not block:
            continue
        if degree_fields(block) is not None and len(block.split()) <= _DEGREE_MAX_WORDS:
            # Kept whole: split, 'Doctor' and 'Ciencias' would each read as a skill.
            phrases = [block]
            max_words = _DEGREE_MAX_WORDS
        elif len(block.split()) >= _PROSE_MIN_WORDS:
            phrases = _prose_tool_tokens(block)
        elif _LANGUAGE_RE.search(block):
            # Languages have their own field; the rest of that line is not a skill.
            continue
        else:
            phrases = _item_phrases(block)

        for phrase in phrases:
            cleaned = _clean_skill(phrase, max_words=max_words)
            if cleaned is None:
                continue
            token = normalize_skill(cleaned)
            if token and token not in seen:
                seen.add(token)
                found.append(cleaned)
    return found


def _prose_tool_tokens(block: str) -> list[str]:
    """Tool names in a paragraph, only from clauses that say a tool is used or known."""
    tokens: list[str] = []
    for clause in _CLAUSE_SPLIT_RE.split(block):
        lead = _PROSE_LEAD_RE.search(clause)
        if lead is not None:
            tokens.extend(_TOOL_TOKEN_RE.findall(clause[lead.end() :]))
    return tokens


def _text_blocks(text: str) -> list[str]:
    """One block per list item or per wrapped paragraph.

    Line by line a wrapped paragraph looks like a list of short items, and its
    fragments then read as skills ('and partner', 'commercial teams'). Sections about
    the employer or its benefits are skipped, and an ATS label printed on its own
    line ('time type', 'Closing Date') takes the next line with it as its value.
    """
    blocks: list[str] = []
    current: list[str] = []
    skipping_section = False
    value_pending = False

    def flush() -> None:
        if current:
            blocks.append(" ".join(current).strip())
            current.clear()

    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped:
            flush()
            continue
        folded = fold_text(stripped)
        if folded in _PAGE_FIELD_LABELS:
            flush()
            value_pending = True
            continue
        if value_pending:
            value_pending = False
            if not _SECTION_HEADING_RE.match(stripped):
                continue
        if _NON_REQUIREMENT_SECTION_RE.match(stripped):
            flush()
            skipping_section = True
            continue
        if _HEADER_FIELD_RE.match(stripped) or _SECTION_HEADING_RE.match(stripped):
            flush()
            skipping_section = False
            continue
        if skipping_section:
            if not stripped.endswith(":"):
                continue
            skipping_section = False
        if folded in _PAGE_CHROME_WORDS:
            flush()
            continue
        bullet = re.match(r"^[-*•·–—]\s*|^\d+[.)]\s+", stripped)
        if bullet:
            flush()
            current.append(stripped[bullet.end() :].strip())
            continue
        if current and not stripped[:1].islower():
            # A wrapped line continues the sentence in lowercase; a new line that
            # starts capitalised is its own item.
            flush()
        current.append(stripped)
    flush()
    return [block for block in blocks if block]


def _item_phrases(item: str) -> list[str]:
    """'Experiencia en ventilación mecánica y fármacos vasoactivos' → both skills."""
    body = _LEAD_IN_RE.sub("", item).strip()
    parts = _ITEM_SPLIT_RE.split(_PARENS_RE.sub(",", body))
    return [_LEAD_IN_RE.sub("", part).strip() for part in parts if part and part.strip()]


def _clean_skill(phrase: str, *, max_words: int = _ITEM_MAX_WORDS) -> str | None:
    if looks_like_page_metadata(phrase):
        return None
    cleaned = _TRAILING_NOISE_RE.sub("", phrase).strip(" .,:;-–—")
    for _ in range(3):
        trimmed = _DANGLING_RE.sub("", cleaned).strip(" .,:;-–—")
        if trimmed == cleaned:
            break
        cleaned = trimmed
    if not cleaned or _LANGUAGE_RE.search(cleaned):
        return None
    words = cleaned.split()
    if not words or len(words) > max_words:
        return None
    if not re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]{2}", cleaned):
        return None
    if all(fold_text(word) in _ITEM_STOPWORDS for word in words):
        return None
    return cleaned


def _extract_requirements(text: str) -> list[str]:
    reqs: list[str] = []
    in_block = False
    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r"(?i)^(requirements|requisitos|requirements:|what you.ll need)", stripped):
            in_block = True
            continue
        if in_block:
            if not stripped:
                if reqs:
                    break
                continue
            if re.match(r"(?i)^(benefits|beneficios|about us|sobre)", stripped):
                break
            bullet = re.sub(r"^[-*•\d.)\s]+", "", stripped)
            if bullet:
                reqs.append(bullet)
    return reqs


def _extract_languages(text: str) -> list[str]:
    langs: list[str] = []
    lower = text.lower()
    if re.search(r"\benglish\b|\bingl[eé]s\b", lower):
        langs.append("english")
    if re.search(r"\bspanish\b|\bespa[nñ]ol\b", lower):
        langs.append("spanish")
    return langs
