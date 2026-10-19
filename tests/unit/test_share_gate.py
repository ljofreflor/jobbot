"""Contact data and a home path never become a shareable company observation."""

from __future__ import annotations

from jobbot.companies.share_gate import share_refusal


def test_a_public_career_url_is_shareable() -> None:
    text = "Servicio Neutro https://careers.example.com/jobs unknown"
    assert share_refusal(text) is None


def test_a_real_email_is_refused_without_echoing_it() -> None:
    address = "persona@mailbox.invalid"
    reason = share_refusal(f"notes {address}")
    assert reason == "real-looking email"
    assert address not in (reason or "")


def test_a_phone_is_refused() -> None:
    assert share_refusal("llamar +56 9 1234 5678") == "phone number"


def test_a_home_path_is_refused_without_echoing_it() -> None:
    home = "/Users/ada/cv.pdf"
    reason = share_refusal(f"seen at {home}")
    assert reason == "absolute home path"
    assert "ada" not in (reason or "")
