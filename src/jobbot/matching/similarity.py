"""Document-level CV↔JD similarity — less dependent on parsed skill lists.

Chat-first cleans structured fields (title, company, skills for CV adaptation).
Match % uses the JD description as a bag(+synonyms) by default, or a **local
BERT-family** sentence embedding when ``jobbot[bert]`` is installed — no paid
API, no OpenAI key. Spanish JDs use BETO; other languages use multilingual
MiniLM (override with ``JOBBOT_BERT_MODEL``).

Also compares **base vs job-adapted ATS text** against the same JD: the adapted
CV should score closer (higher similarity) than the full base CV.
"""

from __future__ import annotations

import logging
import math
import os
import re
from collections import Counter
from dataclasses import dataclass
from typing import Protocol

from jobbot.jobs.normalization import fold_text
from jobbot.models.candidate import Candidate
from jobbot.models.job import JobPosting
from jobbot.ops.pii_guard import redact

logger = logging.getLogger("jobbot.matching.similarity")

# Language-aware local embedders (free; download once to HF cache).
# Spanish JDs → BETO; other languages → multilingual MiniLM.
SPANISH_BERT_MODEL = "dccuchile/bert-base-spanish-wwm-uncased"
MULTILINGUAL_BERT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_BERT_MODEL = SPANISH_BERT_MODEL  # Spanish-first default when no JD text
BERT_MODEL_ENV = "JOBBOT_BERT_MODEL"
# Prefer description over a long raw paste that still has LinkedIn chrome.
_MAX_DOC_CHARS = 8000
_MIN_RICH_CHARS = 180

# Offline Spanish vs other detection for embedder selection (no paid API).
_SPANISH_CHAR_RE = re.compile(r"[ñáéíóúü¿¡]", re.IGNORECASE)
# Folded (accent-stripped) function / JD words that lean Spanish.
_SPANISH_MARKERS = frozenset(
    {
        "el",
        "la",
        "los",
        "las",
        "un",
        "una",
        "unos",
        "unas",
        "del",
        "al",
        "por",
        "para",
        "con",
        "que",
        "como",
        "mas",
        "muy",
        "tambien",
        "esta",
        "este",
        "estos",
        "estas",
        "esa",
        "ese",
        "esos",
        "esas",
        "buscamos",
        "requisitos",
        "experiencia",
        "conocimientos",
        "deseable",
        "excluyente",
        "anos",
        "trabajo",
        "equipo",
        "empleo",
        "puesto",
        "vacante",
        "oferta",
        "desarrollador",
        "ingeniero",
        "ingeniera",
        "cientifico",
        "cientifica",
        "habilidades",
        "responsabilidades",
        "funciones",
        "contrato",
        "jornada",
        "presencial",
        "hibrido",
        "nuestra",
        "nuestro",
        "empresa",
        "candidato",
        "candidata",
        "perfil",
        "se",
        "su",
        "sus",
        "le",
        "les",
        "nos",
        "tiene",
        "tener",
        "debe",
        "deben",
        "sera",
        "seran",
        "ubicacion",
        "remoto",
        "remota",
    }
)
_ENGLISH_MARKERS = frozenset(
    {
        "the",
        "and",
        "with",
        "for",
        "your",
        "you",
        "our",
        "we",
        "are",
        "is",
        "will",
        "must",
        "should",
        "have",
        "has",
        "this",
        "that",
        "from",
        "about",
        "who",
        "what",
        "into",
        "requirements",
        "experience",
        "responsibilities",
        "looking",
        "role",
        "team",
        "company",
        "skills",
        "preferred",
        "required",
        "hiring",
        "join",
        "across",
        "within",
        "using",
        "strong",
        "ability",
        "years",
        "remote",
        "location",
        "opportunity",
        "position",
        "engineer",
        "scientist",
        "developer",
    }
)

# Offline stand-in for embedding neighborhoods when BERT is not installed.
_SYNONYM_GROUPS: tuple[frozenset[str], ...] = (
    frozenset(
        {
            "llm",
            "llms",
            "gpt",
            "openai",
            "transformer",
            "transformers",
            "ia",
            "ai",
            "inteligencia",
            "artificial",
            "ml",
            "machine",
            "learning",
            "aprendizaje",
            "automatico",
            "modelo",
            "modelos",
            "deep",
            "neural",
            "pytorch",
            "tensorflow",
            "keras",
            "scikit",
            "sklearn",
            "xgboost",
            "razonamiento",
            "reasoning",
            "inference",
            "inferencia",
            "agent",
            "agents",
            "multiagente",
            "multiagent",
            "agente",
            "agentes",
        }
    ),
    frozenset({"datos", "data", "dataset", "datasets", "analytics", "analitica"}),
    frozenset({"scientist", "science", "ciencias", "cientifico", "cientifica"}),
    frozenset({"mineria", "minero", "minera", "mining"}),
    frozenset({"python", "sql", "api", "apis", "backend"}),
    frozenset({"arquitectura", "arquitecturas", "architecture", "architectures"}),
    frozenset({"scrum", "agile", "agiles", "agil", "kanban"}),
    frozenset({"proyecto", "proyectos", "project", "projects", "gestion"}),
)


class TextEmbedder(Protocol):
    """Embeds one text; injectable so tests never download a model."""

    def embed(self, text: str) -> list[float]: ...


def job_document(job: JobPosting) -> str:
    """Employment signal only: title + description (+ requirements), not chrome-heavy raw."""
    parts = [
        job.title,
        job.company,
        job.description.strip() or job.raw_description.strip(),
        "\n".join(job.requirements),
    ]
    return _clip("\n".join(p for p in parts if p))


def candidate_document(candidate: Candidate) -> str:
    """What the profile claims in prose — skills, titles, summary, achievements."""
    parts: list[str] = [
        candidate.personal.headline,
        candidate.summary or "",
        " ".join(candidate.specialties),
        " ".join(candidate.skills.all_skills()),
    ]
    for exp in candidate.experience:
        parts.append(exp.title)
        parts.append(exp.company)
        if exp.description:
            parts.append(exp.description)
        for ach in exp.achievements:
            parts.append(ach.text)
            parts.extend(ach.tags)
    for edu in candidate.education:
        parts.append(edu.degree)
        parts.append(edu.institution)
    return _clip("\n".join(p for p in parts if p))


def description_is_rich(job: JobPosting) -> bool:
    blob = (job.description or job.raw_description or "").strip()
    return len(blob) >= _MIN_RICH_CHARS


def bag_cosine(a: str, b: str) -> float:
    """Offline content-word cosine in [0, 1], boosted by synonym coverage.

    Plain bag-of-words fails across ES/EN (``LLMs`` vs ``PyTorch``). Synonym
    groups bridge that gap without a model. Prefer ``--bert`` when installed.
    """
    va, vb = _bow(a), _bow(b)
    if not va or not vb:
        return 0.0
    keys = set(va) | set(vb)
    dot = sum(va[k] * vb[k] for k in keys)
    na = math.sqrt(sum(v * v for v in va.values()))
    nb = math.sqrt(sum(v * v for v in vb.values()))
    if na == 0.0 or nb == 0.0:
        return 0.0
    lexical = max(0.0, min(1.0, dot / (na * nb)))
    coverage = _synonym_coverage(set(va), set(vb))
    return max(0.0, min(1.0, 0.35 * lexical + 0.65 * coverage))


def _synonym_coverage(candidate_words: set[str], job_words: set[str]) -> float:
    """Weighted fraction of JD synonym themes also present in the CV (0–1)."""
    weights = {0: 3.0}
    job_hits = [i for i, g in enumerate(_SYNONYM_GROUPS) if job_words & g]
    if not job_hits:
        return 0.0
    total = sum(weights.get(i, 1.0) for i in job_hits)
    covered = sum(weights.get(i, 1.0) for i in job_hits if candidate_words & _SYNONYM_GROUPS[i])
    return covered / total


def embedding_cosine(a: str, b: str, embedder: TextEmbedder) -> float:
    """Cosine of two embedding vectors in [0, 1] (negative → 0)."""
    va = embedder.embed(redact(a)[:_MAX_DOC_CHARS])
    vb = embedder.embed(redact(b)[:_MAX_DOC_CHARS])
    return _vector_cosine(va, vb)


def document_similarity(
    candidate: Candidate,
    job: JobPosting,
    *,
    embedder: TextEmbedder | None = None,
) -> tuple[float, str]:
    """Return (score 0–100, mode label: bag|bert)."""
    return text_similarity(
        candidate_document(candidate),
        job_document(job),
        embedder=embedder,
    )


def text_similarity(
    left: str,
    right: str,
    *,
    embedder: TextEmbedder | None = None,
) -> tuple[float, str]:
    """Compare two free-text documents. Return (score 0–100, mode: bag|bert)."""
    a, b = _clip(left), _clip(right)
    if embedder is not None:
        try:
            return round(100.0 * embedding_cosine(a, b, embedder), 1), "bert"
        except Exception as exc:  # noqa: BLE001 — fall back offline
            logger.warning("local BERT similarity failed, using bag cosine: %s", exc)
    return round(100.0 * bag_cosine(a, b), 1), "bag"


@dataclass(frozen=True)
class AdaptationFit:
    """Base ATS vs job-adapted ATS similarity to the same JD (0–100 each)."""

    base_score: float
    adapted_score: float
    mode: str
    job_id: str | None = None

    @property
    def delta(self) -> float:
        return round(self.adapted_score - self.base_score, 1)

    @property
    def adapted_beats_base(self) -> bool:
        """True when the job-adapted CV is at least as close to the JD as base."""
        return self.adapted_score >= self.base_score

    def to_dict(self) -> dict[str, object]:
        return {
            "base_score": self.base_score,
            "adapted_score": self.adapted_score,
            "delta": self.delta,
            "mode": self.mode,
            "adapted_beats_base": self.adapted_beats_base,
            "job_id": self.job_id,
        }


def compare_adaptation_fit(
    base_ats: str,
    adapted_ats: str,
    job: JobPosting,
    *,
    embedder: TextEmbedder | None = None,
) -> AdaptationFit:
    """Score base and job-adapted ATS text against the same JD.

    Condition of interest: the CV adapted to the job should score **closer /
    higher** than the base CV (``adapted_beats_base``).
    """
    jd = job_document(job)
    base_score, mode_a = text_similarity(base_ats, jd, embedder=embedder)
    adapted_score, mode_b = text_similarity(adapted_ats, jd, embedder=embedder)
    mode = mode_b if mode_b == mode_a else f"{mode_a}/{mode_b}"
    return AdaptationFit(
        base_score=base_score,
        adapted_score=adapted_score,
        mode=mode,
        job_id=job.id,
    )


def is_spanish_text(text: str) -> bool:
    """Heuristic: True when title+description lean Spanish (offline, deterministic).

    Uses Spanish orthography (ñ, accents, ¿¡) plus stopword/JD-marker counts
    against English markers. Ties and empty text → not Spanish (use MiniLM).
    """
    sample = (text or "").strip()
    if not sample:
        return False
    char_hits = len(_SPANISH_CHAR_RE.findall(sample))
    tokens = re.findall(r"[a-z0-9]+", fold_text(sample))
    if not tokens and char_hits == 0:
        return False
    es = sum(1 for t in tokens if t in _SPANISH_MARKERS) + 2 * char_hits
    en = sum(1 for t in tokens if t in _ENGLISH_MARKERS)
    return es > en


def resolve_bert_model_name(
    *,
    model_name: str | None = None,
    text: str | None = None,
) -> str:
    """Pick embedder: explicit name → env force → Spanish BETO / multilingual MiniLM."""
    if model_name:
        return model_name
    forced = (os.environ.get(BERT_MODEL_ENV) or "").strip()
    if forced:
        return forced
    if text is None:
        return DEFAULT_BERT_MODEL
    if is_spanish_text(text):
        return SPANISH_BERT_MODEL
    return MULTILINGUAL_BERT_MODEL


def bert_available() -> bool:
    """True when the optional local sentence-transformers stack is importable."""
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        return False
    return True


def build_local_bert_embedder(
    *,
    model_name: str | None = None,
    text: str | None = None,
) -> TextEmbedder:
    """Load a free local BERT-family sentence model (downloads once to HF cache).

    When ``model_name`` and ``JOBBOT_BERT_MODEL`` are unset, chooses BETO for
    Spanish JD text and multilingual MiniLM otherwise. Pass ``text`` (title +
    description) so language-aware selection can run.
    """
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        msg = "Local BERT not installed. Run: uv sync --extra bert"
        raise RuntimeError(msg) from exc
    name = resolve_bert_model_name(model_name=model_name, text=text)
    logger.info("loading local BERT embedder: %s", name)
    model = SentenceTransformer(name)
    return _SentenceTransformerEmbedder(model, name)


class _SentenceTransformerEmbedder:
    """Wraps sentence-transformers; runs on CPU; no network after first download."""

    def __init__(self, model: object, name: str) -> None:
        self._model = model
        self.name = name

    def embed(self, text: str) -> list[float]:
        vector = self._model.encode(  # type: ignore[attr-defined]
            text,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [float(x) for x in vector]


def _clip(text: str) -> str:
    return text.strip()[:_MAX_DOC_CHARS]


# Shared with analyzer content-word filtering (keep in sync; no circular import).
_STOPWORDS = frozenset(
    {
        "años",
        "anos",
        "para",
        "con",
        "como",
        "experiencia",
        "experience",
        "conocimiento",
        "conocimientos",
        "manejo",
        "titulo",
        "deseable",
        "excluyente",
        "trabajo",
        "equipo",
        "equipos",
        "afin",
        "otros",
        "otras",
        "sobre",
        "strong",
        "comfortable",
        "preferred",
        "nice",
        "have",
        "with",
        "and",
        "the",
        "role",
        "senior",
        "junior",
        "semi",
        "company",
        "title",
        "location",
        "requirements",
    }
)


def _bow(text: str) -> Counter[str]:
    words = [
        w
        for w in re.findall(r"[a-z0-9áéíóúñü]+", fold_text(text))
        if len(w) >= 3 and w not in _STOPWORDS
    ]
    return Counter(words)


def _vector_cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    raw = dot / (na * nb)
    return max(0.0, min(1.0, (raw + 1.0) / 2.0)) if raw < 0 else max(0.0, min(1.0, raw))
