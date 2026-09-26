"""Knowledge compilation — vibecode (slow) → feature (fast).

Maps Kahneman's *Thinking, Fast and Slow* onto JobBot engineering:

- **System 2 / vibecode:** Cursor chat, exploratory judgment, high compute.
  Allowed for discovery. The transcript is a lab notebook.
- **Symptom / latent requirement:** The same judgment *returns* (Lacanian:
  what repeats). Still paid entirely with client tokens until compressed.
- **System 1 / feature:** A callable (+ test, optional CLI) that runs the
  discovered rule cheaply. This is the compression target.

Capture symptoms locally and redacted via ``jobbot ops symptom note``
(``ops/symptoms.py``). Never store raw chat or PII. Then compress:

1. Name a falsifiable rule (one sentence a unit test can break).
2. Implement deterministic heuristics first.
3. If prose still needs a model, wrap with ``jobbot.nlp.gateway.run_optional_llm``.
4. Next NL request calls the feature — it does not replay System 2.

See ``docs/software-design.md`` §3.8 and ``AGENTS.md`` Design economics.
"""

from __future__ import annotations

# One-line contract for greppability and agent checklists.
COMPRESS_CONTRACT = (
    "vibecode discovers (System 2) → symptom marks the return → "
    "feature executes (System 1, forever); "
    "never unpaid System 2 replay"
)

PROMOTION_STEPS: tuple[str, ...] = (
    "capture_symptom_redacted_locally",
    "name_falsifiable_rule",
    "implement_deterministic",
    "optional_llm_inside_via_gateway",
    "test_first_then_cli_if_human",
    "call_feature_do_not_rederive",
    "triage_symptom_resolved",
)
