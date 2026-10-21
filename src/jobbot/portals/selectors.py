"""CSS for a learned form field. Shared by apply and signup fill.

Workday inputs often have no ``name``. The selector names the attribute that
is actually in the DOM: ``name``, then ``data-automation-id``, then ``id``.
Ids that start with a digit, or values that contain quotes, stay inside an
attribute selector so the CSS still points at the element.
"""

from __future__ import annotations

from jobbot.portals.form_learn import FieldKind, FormField


def field_selector(field: FormField) -> str | None:
    """CSS that matches this field by name, automation id, or id."""
    name = field.name.strip()
    if not name:
        return None
    quoted = name.replace("\\", "\\\\").replace('"', '\\"')
    if field.kind is FieldKind.LONG_TEXT:
        return (
            f'textarea[name="{quoted}"], '
            f'textarea[data-automation-id="{quoted}"], '
            f'textarea[id="{quoted}"]'
        )
    return (
        f'[name="{quoted}"], '
        f'[data-automation-id="{quoted}"], '
        f'[id="{quoted}"]'
    )
