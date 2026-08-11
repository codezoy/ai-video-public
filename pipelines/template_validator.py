"""Validation for scene template_type and visual_data.

validate_scene(scene, idx) → list[str] of error tokens.
Empty list means PASS.

Error token format:
  [TEMPLATE_VALIDATION_FAIL] scene=<id> reason=<reason>
"""
from __future__ import annotations

import logging
from typing import Any

from template_schema import TEMPLATE_TYPES, VISUAL_DATA_SCHEMA, is_valid_template_type  # type: ignore[import]

log = logging.getLogger(__name__)

_TITLE_KEYS = {
    "title",
    "subtitle",
    "source",
    "left_title",
    "right_title",
    "before_title",
    "after_title",
}
_ITEM_KEYS = {
    "keywords",
    "steps",
    "events",
    "nodes",
    "takeaways",
    "left_items",
    "right_items",
    "headers",
    "rows",
    "before_items",
    "after_items",
}
_SENTENCE_ENDINGS = (
    "합니다",
    "했습니다",
    "됩니다",
    "입니다",
    "였습니다",
    "습니다",
    "죠",
    "다",
    "다.",
    "요.",
)
_MAX_TITLE_CHARS = 20
_MAX_ITEM_CHARS = 20
_MAX_QUOTE_CHARS = 40


def _flatten_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        flattened: list[str] = []
        for item in value:
            flattened.extend(_flatten_values(item))
        return flattened
    if isinstance(value, dict):
        flattened = []
        for item in value.values():
            flattened.extend(_flatten_values(item))
        return flattened
    return []


def _normalized(text: str) -> str:
    return "".join(ch for ch in text if ch.isalnum())


def _looks_like_sentence(text: str) -> bool:
    stripped = text.strip()
    return any(stripped.endswith(ending) for ending in _SENTENCE_ENDINGS)


def _validate_visual_text(
    scene: dict[str, Any],
    template_type: str,
    visual_data: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    scene_id = scene.get("id", "?")
    narration_norm = _normalized(str(scene.get("narration", "")))

    for key in _TITLE_KEYS:
        value = visual_data.get(key)
        if isinstance(value, str) and len(value.strip()) > _MAX_TITLE_CHARS:
            errors.append(
                f"[TEMPLATE_VALIDATION_FAIL] scene={scene_id} reason=visual_title_too_long:{key}:{len(value.strip())}"
            )

    quote = visual_data.get("quote")
    if isinstance(quote, str):
        stripped = quote.strip()
        if len(stripped) > _MAX_QUOTE_CHARS:
            errors.append(
                f"[TEMPLATE_VALIDATION_FAIL] scene={scene_id} reason=visual_quote_too_long:{len(stripped)}"
            )
        quote_norm = _normalized(stripped)
        if len(quote_norm) >= 20 and quote_norm in narration_norm:
            errors.append(
                f"[TEMPLATE_VALIDATION_FAIL] scene={scene_id} reason=visual_quote_duplicates_narration"
            )

    for key in _ITEM_KEYS:
        if key not in visual_data:
            continue
        for text in _flatten_values(visual_data.get(key)):
            stripped = text.strip()
            if not stripped:
                continue
            if len(stripped) > _MAX_ITEM_CHARS:
                errors.append(
                    f"[TEMPLATE_VALIDATION_FAIL] scene={scene_id} reason=visual_item_too_long:{key}:{len(stripped)}"
                )
            if _looks_like_sentence(stripped):
                errors.append(
                    f"[TEMPLATE_VALIDATION_FAIL] scene={scene_id} reason=visual_item_sentence:{key}"
                )
            text_norm = _normalized(stripped)
            if len(text_norm) >= 20 and text_norm in narration_norm:
                errors.append(
                    f"[TEMPLATE_VALIDATION_FAIL] scene={scene_id} reason=visual_item_duplicates_narration:{key}"
                )

    return errors


def validate_scene(scene: dict[str, Any], idx: int | None = None) -> list[str]:
    """Return list of validation error tokens. Empty → PASS."""
    errors: list[str] = []
    scene_id = scene.get("id", idx)

    template_type = scene.get("template_type")
    visual_data = scene.get("visual_data")

    if "visual_summary" in scene and scene["visual_summary"]:
        errors.append(
            f"[TEMPLATE_VALIDATION_FAIL] scene={scene_id} reason=visual_summary_present"
        )

    if not template_type:
        errors.append(
            f"[TEMPLATE_VALIDATION_FAIL] scene={scene_id} reason=missing_template_type"
        )
        return errors

    if not is_valid_template_type(template_type):
        allowed = " | ".join(TEMPLATE_TYPES)
        errors.append(
            f"[TEMPLATE_VALIDATION_FAIL] scene={scene_id} reason=unsupported_template_type:{template_type}"
            f" | allowed={allowed}"
            f" | recommendation=use one of the allowed types above"
        )
        return errors

    if visual_data is None:
        errors.append(
            f"[TEMPLATE_VALIDATION_FAIL] scene={scene_id} reason=missing_visual_data"
        )
        return errors

    if not isinstance(visual_data, dict):
        errors.append(
            f"[TEMPLATE_VALIDATION_FAIL] scene={scene_id} reason=visual_data_not_dict"
        )
        return errors

    schema = VISUAL_DATA_SCHEMA.get(template_type, {})
    for req_key in schema.get("required", []):
        if req_key not in visual_data or visual_data[req_key] in (None, [], ""):
            errors.append(
                f"[TEMPLATE_VALIDATION_FAIL] scene={scene_id} reason=missing_visual_data_key:{req_key}"
            )

    errors.extend(_validate_visual_text(scene, template_type, visual_data))

    return errors


def validate_scenes(scenes: list[dict[str, Any]]) -> tuple[int, int, list[str]]:
    """Validate all scenes. Returns (pass_count, fail_count, all_errors)."""
    all_errors: list[str] = []
    for i, scene in enumerate(scenes):
        errs = validate_scene(scene, i + 1)
        all_errors.extend(errs)

    hero_title_count = sum(1 for s in scenes if s.get("template_type") == "hero_title")
    if hero_title_count > 1:
        all_errors.append(
            f"[TEMPLATE_VALIDATION_FAIL] reason=hero_title_count:{hero_title_count} max=1"
        )
    # hero_title must appear only at scene[0]; mid-video hero_title breaks flow
    for i, s in enumerate(scenes):
        if i > 0 and s.get("template_type") == "hero_title":
            all_errors.append(
                f"[TEMPLATE_VALIDATION_FAIL] scene={i + 1} reason=hero_title_at_non_first_position"
            )

    fail_count = len(all_errors)
    pass_count = len(scenes) - sum(
        1 for i, scene in enumerate(scenes) if validate_scene(scene, i + 1)
    )
    return pass_count, fail_count, all_errors
