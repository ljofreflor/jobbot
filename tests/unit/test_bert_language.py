"""Language-aware BERT model selection (no model downloads)."""

from __future__ import annotations

import sys
from types import SimpleNamespace

from jobbot.matching.similarity import (
    DEFAULT_BERT_MODEL,
    MULTILINGUAL_BERT_MODEL,
    SPANISH_BERT_MODEL,
    is_spanish_text,
    resolve_bert_model_name,
)

_ES_JD = (
    "Buscamos Científico de Datos Senior con experiencia en machine learning, "
    "inferencia causal y experimentación. Requisitos: Python, SQL, PyTorch. "
    "Trabajo remoto en Chile. Conocimientos deseables en MLOps."
)

_EN_JD = (
    "We are hiring a Senior Data Scientist to lead causal inference, "
    "machine learning, and experimentation. Requirements: Python, SQL, PyTorch. "
    "Remote role with a strong team culture."
)


def test_is_spanish_text_detects_spanish_jd() -> None:
    assert is_spanish_text(_ES_JD) is True
    assert is_spanish_text("Data Scientist — requisitos y experiencia en el equipo") is True


def test_is_spanish_text_rejects_english_jd() -> None:
    assert is_spanish_text(_EN_JD) is False
    assert is_spanish_text("Senior Engineer — strong experience with the team") is False


def test_is_spanish_text_empty_is_not_spanish() -> None:
    assert is_spanish_text("") is False
    assert is_spanish_text("   ") is False


def test_default_bert_model_is_spanish_beto() -> None:
    assert "spanish" in DEFAULT_BERT_MODEL.casefold() or "dccuchile" in DEFAULT_BERT_MODEL
    assert DEFAULT_BERT_MODEL == SPANISH_BERT_MODEL


def test_resolve_bert_model_spanish_text_picks_beto(monkeypatch) -> None:
    monkeypatch.delenv("JOBBOT_BERT_MODEL", raising=False)
    assert resolve_bert_model_name(text=_ES_JD) == SPANISH_BERT_MODEL


def test_resolve_bert_model_english_text_picks_minilm(monkeypatch) -> None:
    monkeypatch.delenv("JOBBOT_BERT_MODEL", raising=False)
    assert resolve_bert_model_name(text=_EN_JD) == MULTILINGUAL_BERT_MODEL


def test_resolve_bert_model_no_text_defaults_to_beto(monkeypatch) -> None:
    monkeypatch.delenv("JOBBOT_BERT_MODEL", raising=False)
    assert resolve_bert_model_name() == DEFAULT_BERT_MODEL
    assert resolve_bert_model_name(text=None) == SPANISH_BERT_MODEL


def test_resolve_bert_model_env_forces_override(monkeypatch) -> None:
    forced = "sentence-transformers/all-MiniLM-L6-v2"
    monkeypatch.setenv("JOBBOT_BERT_MODEL", forced)
    assert resolve_bert_model_name(text=_ES_JD) == forced
    assert resolve_bert_model_name(text=_EN_JD) == forced


def test_resolve_bert_model_explicit_name_beats_env(monkeypatch) -> None:
    monkeypatch.setenv("JOBBOT_BERT_MODEL", "env-model")
    assert resolve_bert_model_name(model_name="explicit-model", text=_ES_JD) == "explicit-model"


def test_build_local_bert_embedder_uses_resolved_name_without_download(
    monkeypatch,
) -> None:
    """Inject a fake sentence_transformers so tests never download weights."""
    monkeypatch.delenv("JOBBOT_BERT_MODEL", raising=False)
    calls: list[str] = []

    class _FakeST:
        def __init__(self, name: str) -> None:
            calls.append(name)
            self.name = name

        def encode(self, text: str, **kwargs: object) -> list[float]:
            return [0.1, 0.2]

    fake_mod = SimpleNamespace(SentenceTransformer=_FakeST)
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_mod)

    from jobbot.matching.similarity import build_local_bert_embedder

    embedder_es = build_local_bert_embedder(text=_ES_JD)
    assert calls[-1] == SPANISH_BERT_MODEL
    assert embedder_es.name == SPANISH_BERT_MODEL  # type: ignore[attr-defined]

    embedder_en = build_local_bert_embedder(text=_EN_JD)
    assert calls[-1] == MULTILINGUAL_BERT_MODEL
    assert embedder_en.name == MULTILINGUAL_BERT_MODEL  # type: ignore[attr-defined]

    # Forced env still wins.
    monkeypatch.setenv("JOBBOT_BERT_MODEL", "forced-model")
    embedder_forced = build_local_bert_embedder(text=_ES_JD)
    assert calls[-1] == "forced-model"
    assert embedder_forced.name == "forced-model"  # type: ignore[attr-defined]
