"""Easy Apply names its submit control and does not treat Next as send."""

from __future__ import annotations

from jobbot.adapters.linkedin.selectors import EASY_APPLY_SUBMIT, is_easy_apply_submit


def test_submit_application_is_the_send_control() -> None:
    assert is_easy_apply_submit("Submit application")
    assert is_easy_apply_submit("  Enviar solicitud  ")
    assert "Submit application" in EASY_APPLY_SUBMIT
    assert "Enviar solicitud" in EASY_APPLY_SUBMIT


def test_next_and_the_opener_are_not_the_send_control() -> None:
    assert not is_easy_apply_submit("Next")
    assert not is_easy_apply_submit("Siguiente")
    assert not is_easy_apply_submit("Review")
    assert not is_easy_apply_submit("Easy Apply")
    assert not is_easy_apply_submit("Solicitud sencilla")
    assert not is_easy_apply_submit("")
