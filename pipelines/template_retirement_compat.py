"""Compatibility guard for retired template types.

Retired templates are not exposed to new generation/schema/Root registration.
Existing scenes that still contain these names fail loudly instead of reaching
a missing Remotion composition or silently rendering the wrong component.
"""
from __future__ import annotations

RETIRED_TEMPLATE_TYPES: frozenset[str] = frozenset({
    "glass_cards",
    "keyword_cards",
    "keyword_cards_grid",
    "keyword_cards_stack",
    "underline_title",
    "side_accent_title",
    "architecture_diagram",
    "agent_workflow",
})


def is_retired_template_type(template_type: str | None) -> bool:
    return bool(template_type) and str(template_type) in RETIRED_TEMPLATE_TYPES


def retired_template_error(template_type: str | None) -> str:
    return (
        f"retired_template_type:{template_type}; "
        "regenerate the scene with an active template_type"
    )
