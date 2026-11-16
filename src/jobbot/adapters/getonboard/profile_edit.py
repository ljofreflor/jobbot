"""Write the permanent Get on Board profile through its own edit form.

Long blocks used to be Trix editors (`editor.loadHTML`). The current form is Lexxy:
a contenteditable div synced to a hidden input. Reads come from the portal itself,
so the plan can show what each field holds today. A field that is not on the page
is reported; it is never skipped in silence.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from html import escape
from typing import Any, Protocol

logger = logging.getLogger("jobbot.getonboard.profile_edit")

GOB_EDIT_URL = "https://www.getonbrd.com/webpros/edit"
SAVE_BUTTON = 'input[type="submit"][value*="Guardar"]'


@dataclass(frozen=True)
class GobField:
    """One editable field of the permanent profile."""

    key: str
    label: str
    selectors: tuple[str, ...]
    trix: bool
    hidden_selector: str = ""

    @property
    def selector(self) -> str:
        """First selector. Older callers and fakes still key the Trix node by it."""
        return self.selectors[0]


class ProfileEditError(Exception):
    """The edit form is not the one this writer knows. Nothing was saved."""


FIELDS: tuple[GobField, ...] = (
    GobField(
        key="description_es",
        label="Descripción profesional",
        selectors=('input[name="webpro[description_es]"]',),
        trix=False,
    ),
    GobField(
        key="professional_es",
        label="Perfil profesional y experiencia laboral",
        selectors=(
            "trix-editor#trix-professional_es",
            "#trix-professional_es-content[contenteditable]",
        ),
        trix=True,
        hidden_selector='input[name="webpro[professional_background_es]"]',
    ),
    GobField(
        key="academic_background_es",
        label="Formación académica y estudios",
        selectors=(
            "trix-editor#trix-academic_background_es",
            "#trix-academic_background_es-content[contenteditable]",
        ),
        trix=True,
        hidden_selector='input[name="webpro[academic_background_es]"]',
    ),
)

COUNTRY_SELECTOR = "select.chzn-select"


@dataclass(frozen=True)
class FieldWrite:
    """A pending change on one field, with the text the portal holds today."""

    field: GobField
    current: str
    new: str

    @property
    def verb(self) -> str:
        return "fill" if not self.current else "replace"

    def describe(self) -> str:
        if self.verb == "fill":
            return f"fill {self.field.label} ({len(self.new)} chars, empty today)"
        return f"replace {self.field.label} ({len(self.current)} → {len(self.new)} chars)"


class ElementLike(Protocol):
    def inner_text(self) -> str: ...
    def input_value(self) -> str: ...
    def evaluate(self, expression: str, arg: Any = None) -> Any: ...
    def fill(self, value: str) -> None: ...


class KeyboardLike(Protocol):
    def insert_text(self, text: str) -> None: ...
    def press(self, key: str) -> None: ...


class PageLike(Protocol):
    def goto(self, url: str, **kwargs: Any) -> Any: ...
    def query_selector(self, selector: str) -> ElementLike | None: ...
    def click(self, selector: str, **kwargs: Any) -> None: ...
    def wait_for_timeout(self, timeout: float) -> None: ...

    @property
    def keyboard(self) -> KeyboardLike: ...


def _locate(page: PageLike, field: GobField) -> tuple[str, ElementLike] | None:
    for selector in field.selectors:
        element = page.query_selector(selector)
        if element is not None:
            return selector, element
    return None


def missing_field_message(field: GobField) -> str:
    return f"campo no encontrado: {field.label} (¿cambió el portal?)"


def ensure_present(page: PageLike) -> None:
    """Raise when an expected field has none of its selectors. Does not save."""
    for field in FIELDS:
        if _locate(page, field) is None:
            raise ProfileEditError(missing_field_message(field))


def read_current(page: PageLike) -> dict[str, str]:
    """What the portal shows right now, per field key. Absent fields are omitted."""
    out: dict[str, str] = {}
    for field in FIELDS:
        located = _locate(page, field)
        if located is None:
            logger.debug("Field %s not present on the edit form", field.key)
            continue
        _selector, element = located
        text = element.inner_text() if field.trix else element.input_value()
        out[field.key] = (text or "").strip()
    return out


def plan_writes(
    current: dict[str, str],
    desired: dict[str, str],
    *,
    page: PageLike | None = None,
) -> list[FieldWrite]:
    """Only real changes, and never an empty text over something the portal holds."""
    if page is not None:
        ensure_present(page)
    writes: list[FieldWrite] = []
    for field in FIELDS:
        if field.key not in current:
            continue
        new = (desired.get(field.key) or "").strip()
        old = current[field.key].strip()
        if not new or _same_text(new, old):
            continue
        writes.append(FieldWrite(field=field, current=old, new=new))
    return writes


def apply_writes(page: PageLike, writes: list[FieldWrite]) -> list[FieldWrite]:
    """Set each field, then save the form. Returns the writes that went through.

    A missing field or a Lexxy editor that leaves its hidden input empty raises
    ``ProfileEditError`` before the save button is clicked.
    """
    ensure_present(page)
    done: list[FieldWrite] = []
    for write in writes:
        located = _locate(page, write.field)
        if located is None:
            raise ProfileEditError(missing_field_message(write.field))
        selector, element = located
        if selector.startswith("trix-editor"):
            element.evaluate("(node, html) => node.editor.loadHTML(html)", _as_html(write.new))
        elif write.field.trix:
            _type_paragraphs(page, element, write.new)
            _require_hidden_sync(page, write.field)
        else:
            element.fill(write.new)
        done.append(write)
    if done:
        page.click(SAVE_BUTTON)
        page.wait_for_timeout(2500)
    return done


_CHOSEN_JS = (
    "(node, value) => {"
    " node.value = value;"
    " node.dispatchEvent(new Event('change', { bubbles: true }));"
    " if (window.jQuery) { window.jQuery(node).trigger('chosen:updated'); }"
    " }"
)


def set_chosen_select(page: PageLike, selector: str, value: str, *, missing: str) -> None:
    """Set a Chosen-hidden select. Visibility is irrelevant: the node gets value and change."""
    element = page.query_selector(selector)
    if element is None:
        raise ProfileEditError(missing)
    element.evaluate(_CHOSEN_JS, value)


def set_country(page: PageLike, value: str) -> None:
    """Set the Chosen-hidden residence select without waiting for it to be visible."""
    set_chosen_select(
        page,
        COUNTRY_SELECTOR,
        value,
        missing="campo no encontrado: ¿Dónde vives? (¿cambió el portal?)",
    )


def _type_paragraphs(page: PageLike, element: ElementLike, text: str) -> None:
    focus = getattr(element, "focus", None)
    if callable(focus):
        focus()
    keyboard = page.keyboard
    keyboard.press("ControlOrMeta+a")
    keyboard.press("Backspace")
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    for index, paragraph in enumerate(paragraphs):
        if index:
            keyboard.press("Enter")
        keyboard.insert_text(paragraph)


def _require_hidden_sync(page: PageLike, field: GobField) -> None:
    hidden = page.query_selector(field.hidden_selector) if field.hidden_selector else None
    synced = (hidden.input_value() if hidden is not None else "").strip()
    if not synced:
        raise ProfileEditError(f"el editor no sincronizó el campo oculto: {field.label}")


def desired_from_fields(headline: str, professional: str, academic: str) -> dict[str, str]:
    """Map the permanent profile blocks onto the portal's Spanish fields."""
    return {
        "description_es": headline.strip(),
        "professional_es": professional.strip(),
        "academic_background_es": academic.strip(),
    }


def _as_html(text: str) -> str:
    """Trix stores HTML: keep paragraph breaks, escape everything else."""
    paragraphs = [escape(p.strip()) for p in text.split("\n\n") if p.strip()]
    return "".join(f"<div>{p}</div>" for p in paragraphs)


def _same_text(left: str, right: str) -> bool:
    return " ".join(left.split()) == " ".join(right.split())
