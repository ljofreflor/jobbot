"""Siguiente may be chosen. Enviar is never the button this step returns."""

from __future__ import annotations

from jobbot.adapters.ats.advance import button_role, pressable_advance


def test_siguiente_is_advance_and_enviar_is_submit() -> None:
    assert button_role("Siguiente") == "advance"
    assert button_role("Continue") == "advance"
    assert button_role("Enviar") == "submit"
    assert button_role("Postular ahora") == "submit"
    assert button_role("Submit application") == "submit"


def test_a_mixed_label_is_submit() -> None:
    assert button_role("Siguiente y enviar") == "submit"


def test_the_step_returns_siguiente_and_not_enviar() -> None:
    chosen = pressable_advance(["Enviar", "Siguiente", "Apply"])
    assert chosen == "Siguiente"


def test_submit_alone_is_not_pressed() -> None:
    assert pressable_advance(["Submit", "Postular"]) is None
