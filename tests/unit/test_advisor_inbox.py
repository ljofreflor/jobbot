"""WhatsApp is a transport: questions and CV HITL, never submit, never secrets."""

from __future__ import annotations

from jobbot.advisor_inbox import (
    InboundKind,
    PendingPrompt,
    classify_inbound,
)


def test_empty_message_is_ignored() -> None:
    decision = classify_inbound("   ")
    assert decision.kind is InboundKind.IGNORE
    assert decision.store_body is False
    assert decision.may_submit is False
    assert decision.writes_profile is False


def test_a_yes_writes_only_when_a_cv_prompt_is_pending() -> None:
    pending = PendingPrompt(summary="years in the role")
    yes = classify_inbound("sí", pending=pending)
    assert yes.kind is InboundKind.FACT_CONFIRM
    assert yes.writes_profile is True
    assert yes.may_submit is False

    stray = classify_inbound("sí")
    assert stray.kind is not InboundKind.FACT_CONFIRM
    assert stray.writes_profile is False


def test_a_no_declines_the_pending_fact_and_writes_nothing() -> None:
    decision = classify_inbound("no", pending=PendingPrompt(summary="add a skill"))
    assert decision.kind is InboundKind.FACT_DECLINE
    assert decision.writes_profile is False
    assert decision.may_submit is False


def test_a_new_fact_is_offered_not_written() -> None:
    decision = classify_inbound("En realidad fueron cinco años en ese cargo.")
    assert decision.kind is InboundKind.FACT_OFFER
    assert decision.writes_profile is False
    assert "sí" in decision.reply.casefold()


def test_questions_are_read_only() -> None:
    for text in (
        "¿Qué dejamos en el resumen del CV?",
        "Tengo una pregunta sobre el CV.",
        "I have a question about the summary.",
    ):
        decision = classify_inbound(text)
        assert decision.kind is InboundKind.QUESTION, text
        assert decision.writes_profile is False
        assert decision.may_submit is False
        assert decision.needs_human is False


def test_passwords_and_otp_are_refused_and_not_stored() -> None:
    for text in (
        "mi contraseña es secret123",
        "el código de verificación es 847291",
        "te paso el 2FA",
    ):
        decision = classify_inbound(text)
        assert decision.kind is InboundKind.SECRET, text
        assert decision.store_body is False
        assert decision.writes_profile is False
        assert decision.may_submit is False
        assert "portal" in decision.reply.casefold()


def test_a_password_question_is_still_a_secret() -> None:
    """Asking JobBot to handle a password is refused, even with a question mark."""
    decision = classify_inbound("¿cuál es mi contraseña de LinkedIn?")
    assert decision.kind is InboundKind.SECRET
    assert decision.store_body is False


def test_submit_intents_never_send() -> None:
    for text in (
        "postula a esa",
        "envíalo ahora",
        "dale enviar",
        "submit that application",
    ):
        decision = classify_inbound(text)
        assert decision.kind is InboundKind.SUBMIT, text
        assert decision.may_submit is False
        assert decision.writes_profile is False


def test_judgment_calls_go_to_the_human_advisor() -> None:
    decision = classify_inbound("No sé si vale la pena seguir con esa empresa.")
    assert decision.kind is InboundKind.ADVISOR
    assert decision.needs_human is True
    assert decision.writes_profile is False
    assert decision.may_submit is False


def test_every_kind_keeps_submit_off() -> None:
    pending = PendingPrompt(summary="confirm a date")
    samples = (
        "",
        "sí",
        "no",
        "¿cómo va la búsqueda?",
        "tengo registro vigente",
        "mi password es x",
        "postula por mí",
        "conversemos el honorario",
    )
    for text in samples:
        decision = classify_inbound(text, pending=pending)
        assert decision.may_submit is False, text
