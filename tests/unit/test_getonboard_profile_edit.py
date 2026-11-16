"""Writing the permanent Get on Board profile: plan first, never delete facts."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from jobbot.adapters.getonboard.profile_edit import (
    COUNTRY_SELECTOR,
    FIELDS,
    SAVE_BUTTON,
    ProfileEditError,
    apply_writes,
    desired_from_fields,
    plan_writes,
    read_current,
    set_country,
)

OLD_TEXT = "Me he dedicado a trabajos numéricos en matlab y C++."
NEW_TEXT = "Senior Data Scientist con 12 años de experiencia.\n\nStack: Python, SQL, R."


class FakeTrix:
    """A Trix editor: text is read from the node, written through editor.loadHTML."""

    def __init__(self, text: str = "") -> None:
        self.text = text
        self.loaded_html: str | None = None

    def inner_text(self) -> str:
        return self.text

    def input_value(self) -> str:  # pragma: no cover - trix reads via inner_text
        raise AssertionError("a trix editor must not be read as an input")

    def evaluate(self, expression: str, arg: Any = None) -> Any:
        assert "editor.loadHTML" in expression, expression
        self.loaded_html = str(arg)
        return None

    def fill(self, value: str) -> None:  # pragma: no cover - would silently no-op
        raise AssertionError("fill() does not reach the Trix hidden input")


class FakeInput:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def inner_text(self) -> str:  # pragma: no cover
        raise AssertionError("a plain input must be read with input_value()")

    def input_value(self) -> str:
        return self.value

    def evaluate(self, expression: str, arg: Any = None) -> Any:  # pragma: no cover
        raise AssertionError("a plain input needs no JS")

    def fill(self, value: str) -> None:
        self.value = value


class FakeEditPage:
    def __init__(self, elements: dict[str, Any]) -> None:
        self.elements = elements
        self.clicked: list[str] = []
        self.visited: list[str] = []

    def goto(self, url: str, **_: Any) -> None:
        self.visited.append(url)

    def query_selector(self, selector: str) -> Any:
        return self.elements.get(selector)

    def click(self, selector: str, **_: Any) -> None:
        self.clicked.append(selector)

    def wait_for_timeout(self, _timeout: float) -> None:
        return None


def _page(
    *, description: str = "", professional: str = OLD_TEXT, academic: str = ""
) -> FakeEditPage:
    by_key = {
        "description_es": FakeInput(description),
        "professional_es": FakeTrix(professional),
        "academic_background_es": FakeTrix(academic),
    }
    return FakeEditPage({field.selector: by_key[field.key] for field in FIELDS})


def test_plan_reports_what_the_portal_holds_today() -> None:
    page = _page()
    desired = desired_from_fields(
        "Senior Data Scientist", NEW_TEXT, "Magíster en Estadística — PUC."
    )

    writes = plan_writes(read_current(page), desired)

    described = " ".join(write.describe() for write in writes)
    assert "replace Perfil profesional y experiencia laboral" in described
    assert "fill Formación académica y estudios" in described
    assert "fill Descripción profesional" in described
    assert page.clicked == [], "planning must not touch the form"


def test_unchanged_fields_are_not_rewritten() -> None:
    page = _page(description="Senior Data Scientist", professional=NEW_TEXT, academic="PUC.")
    desired = desired_from_fields("Senior Data Scientist", NEW_TEXT, "PUC.")

    assert plan_writes(read_current(page), desired) == []


def test_whitespace_only_differences_are_not_a_change() -> None:
    page = _page(professional="Senior   Data Scientist\n\nStack: Python.")
    desired = desired_from_fields("", "Senior Data Scientist\n\nStack: Python.", "")

    assert plan_writes(read_current(page), desired) == []


def test_an_empty_draft_never_wipes_the_portal() -> None:
    page = _page(description="Algo escrito", professional=OLD_TEXT, academic="Estudios.")

    assert plan_writes(read_current(page), desired_from_fields("", "", "")) == []


def test_apply_writes_trix_as_html_and_saves_once() -> None:
    page = _page()
    desired = desired_from_fields("Senior Data Scientist", NEW_TEXT, "PUC.")

    done = apply_writes(page, plan_writes(read_current(page), desired))

    assert {write.field.key for write in done} == {
        "description_es",
        "professional_es",
        "academic_background_es",
    }
    professional = page.elements[next(f.selector for f in FIELDS if f.key == "professional_es")]
    assert professional.loaded_html is not None
    # Paragraphs survive as HTML blocks; the portal stores rich text, not plain text.
    assert professional.loaded_html.count("<div>") == 2
    description = page.elements[next(f.selector for f in FIELDS if f.key == "description_es")]
    assert description.value == "Senior Data Scientist"
    assert page.clicked == [SAVE_BUTTON]


def test_nothing_to_write_means_nothing_is_saved() -> None:
    page = _page(description="X", professional=OLD_TEXT, academic="Y")

    assert apply_writes(page, []) == []
    assert page.clicked == []


def test_html_in_the_draft_is_escaped_not_injected() -> None:
    page = _page()
    desired = desired_from_fields("", "Trabajé con <script>alert(1)</script> y R.", "")

    apply_writes(page, plan_writes(read_current(page), desired))

    professional = page.elements[next(f.selector for f in FIELDS if f.key == "professional_es")]
    assert professional.loaded_html is not None
    assert "<script>" not in professional.loaded_html
    assert "&lt;script&gt;" in professional.loaded_html


class _HtmlNode:
    def __init__(self, text: str, *, value: str = "") -> None:
        self.text = text
        self.value = value
        self.evaluated: list[tuple[str, Any]] = []

    def inner_text(self) -> str:
        return self.text

    def input_value(self) -> str:
        return self.value

    def evaluate(self, expression: str, arg: Any = None) -> Any:
        self.evaluated.append((expression, arg))
        return None

    def fill(self, value: str) -> None:
        self.value = value


class _HtmlPage:
    """Enough of a page to resolve the selectors the writer actually uses."""

    def __init__(self, html: str) -> None:
        self.html = html
        self.clicked: list[str] = []

    def query_selector(self, selector: str) -> _HtmlNode | None:
        if selector.startswith("trix-editor#"):
            node_id = selector.split("#", 1)[1]
            match = re.search(
                rf'<trix-editor[^>]*id="{re.escape(node_id)}"[^>]*>(.*?)</trix-editor>',
                self.html,
                re.S,
            )
            return None if match is None else _HtmlNode(match.group(1).strip())
        if selector.endswith("[contenteditable]"):
            node_id = selector[1:].split("[", 1)[0]
            match = re.search(
                rf'<div[^>]*id="{re.escape(node_id)}"[^>]*>(.*?)</div>',
                self.html,
                re.S,
            )
            if match is None or "contenteditable" not in match.group(0):
                return None
            return _HtmlNode(re.sub(r"<[^>]+>", "", match.group(1)).strip())
        if selector.startswith('input[name="') and selector.endswith('"]'):
            name = selector[len('input[name="') : -2]
            match = re.search(
                rf'<input[^>]*name="{re.escape(name)}"[^>]*>',
                self.html,
            )
            if match is None:
                return None
            value = re.search(r'value="([^"]*)"', match.group(0))
            return _HtmlNode("", value="" if value is None else value.group(1))
        if selector == COUNTRY_SELECTOR:
            if "chzn-select" not in self.html:
                return None
            return _HtmlNode("")
        return None

    def goto(self, _url: str, **_: Any) -> None:
        return None

    def click(self, selector: str, **_: Any) -> None:
        self.clicked.append(selector)

    def wait_for_timeout(self, _timeout: float) -> None:
        return None

    @property
    def keyboard(self) -> Any:
        raise AssertionError("reading a fixture does not type")


def test_lexxy_fixture_reads_the_three_fields(project_root: Path) -> None:
    html = (project_root / "tests/fixtures/getonboard/webpros_edit_lexxy.html").read_text(
        encoding="utf-8"
    )
    current = read_current(_HtmlPage(html))

    assert current["description_es"] == "Titular de ejemplo"
    assert current["professional_es"] == "Perfil de ejemplo"
    assert current["academic_background_es"] == ""


def test_trix_fixture_still_reads_the_three_fields(project_root: Path) -> None:
    html = (project_root / "tests/fixtures/getonboard/webpros_edit_trix.html").read_text(
        encoding="utf-8"
    )
    current = read_current(_HtmlPage(html))

    assert current["professional_es"] == "Texto trix de ejemplo"
    assert current["academic_background_es"] == "Estudios de ejemplo"
    assert "description_es" in current


class _Hidden:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def input_value(self) -> str:
        return self.value

    def inner_text(self) -> str:
        return self.value

    def evaluate(self, _expression: str, _arg: Any = None) -> None:
        return None

    def fill(self, value: str) -> None:
        self.value = value


class _Lexxy:
    def __init__(self, hidden: _Hidden, *, sync: bool) -> None:
        self.hidden = hidden
        self.sync = sync
        self.focused = False

    def inner_text(self) -> str:
        return ""

    def input_value(self) -> str:
        return ""

    def evaluate(self, _expression: str, _arg: Any = None) -> None:
        raise AssertionError("Lexxy has no editor.loadHTML")

    def fill(self, _value: str) -> None:
        raise AssertionError("fill() does not sync Lexxy")

    def focus(self) -> None:
        self.focused = True


class _Keyboard:
    def __init__(self, editor: _Lexxy) -> None:
        self.editor = editor
        self.pressed: list[str] = []
        self.inserted: list[str] = []

    def press(self, key: str) -> None:
        self.pressed.append(key)

    def insert_text(self, text: str) -> None:
        self.inserted.append(text)
        if self.editor.sync:
            self.editor.hidden.value = (self.editor.hidden.value + "\n\n" + text).strip()


class _LexxyPage:
    def __init__(self, *, academic: bool = True, sync: bool = True) -> None:
        self.hidden = _Hidden()
        self.editor = _Lexxy(self.hidden, sync=sync)
        self.keys = _Keyboard(self.editor)
        self.clicked: list[str] = []
        self.academic = academic
        description = FakeInput("Titular")
        professional = FakeTrix("Perfil viejo")
        self.elements = {
            'input[name="webpro[description_es]"]': description,
            "trix-editor#trix-professional_es": professional,
            'input[name="webpro[professional_background_es]"]': _Hidden("Perfil viejo"),
        }
        if academic:
            self.elements["#trix-academic_background_es-content[contenteditable]"] = self.editor
            self.elements['input[name="webpro[academic_background_es]"]'] = self.hidden

    def query_selector(self, selector: str) -> Any:
        return self.elements.get(selector)

    def click(self, selector: str, **_: Any) -> None:
        self.clicked.append(selector)

    def goto(self, _url: str, **_: Any) -> None:
        return None

    def wait_for_timeout(self, _timeout: float) -> None:
        return None

    @property
    def keyboard(self) -> _Keyboard:
        return self.keys


def test_a_missing_academic_field_is_reported_and_not_saved() -> None:
    page = _LexxyPage(academic=False)
    desired = desired_from_fields("Titular nuevo", NEW_TEXT, "Estudios nuevos.")

    with pytest.raises(ProfileEditError, match="campo no encontrado: Formación académica"):
        plan_writes(read_current(page), desired, page=page)
    with pytest.raises(ProfileEditError, match="campo no encontrado: Formación académica"):
        apply_writes(page, [])

    assert page.clicked == []


def test_an_unsynced_hidden_input_does_not_save() -> None:
    page = _LexxyPage(sync=False)
    desired = desired_from_fields("Titular", "Perfil viejo", "Estudios nuevos.")
    writes = plan_writes(read_current(page), desired, page=page)

    with pytest.raises(ProfileEditError, match="no sincronizó el campo oculto: Formación"):
        apply_writes(page, writes)

    assert page.clicked == []
    assert page.keys.inserted == ["Estudios nuevos."]
    assert "Enter" not in page.keys.pressed or page.keys.pressed.count("Enter") == 0


def test_lexxy_types_paragraphs_and_saves_when_the_hidden_input_syncs() -> None:
    page = _LexxyPage(sync=True)
    desired = desired_from_fields("Titular", "Perfil viejo", "Uno.\n\nDos.")
    writes = plan_writes(read_current(page), desired, page=page)

    done = apply_writes(page, writes)

    assert [write.field.key for write in done] == ["academic_background_es"]
    assert page.keys.inserted == ["Uno.", "Dos."]
    assert page.keys.pressed.count("Enter") == 1
    assert page.clicked == [SAVE_BUTTON]
    assert page.hidden.value == "Uno.\n\nDos."


def test_country_is_set_on_the_hidden_select_without_waiting_for_it() -> None:
    node = _HtmlNode("")
    page = FakeEditPage({COUNTRY_SELECTOR: node})

    set_country(page, "CL")

    expression, arg = node.evaluated[0]
    assert arg == "CL"
    assert "chosen:updated" in expression
    assert "dispatchEvent" in expression
