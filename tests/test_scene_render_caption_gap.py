from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest


def test_target_scene_caption_data_is_active_at_91s() -> None:
    """The reported run has active caption data at final 91s / scene06 local 12.458s."""
    scene_start_ms = 78542
    final_timestamp_ms = 91000
    local_ms = final_timestamp_ms - scene_start_ms
    captions = [
        {
            "start_ms": 0,
            "end_ms": 4931,
            "text": "위험 점수가 높다고 모든 거래를 자동 차단하면 정상 고객도 불편을 겪습니다.",
        },
        {
            "start_ms": 4931,
            "end_ms": 10482,
            "text": "그래서 금융사는 AI의 판단 뒤에 설명 가능한 근거와 사람의 검토 절차를 둡니다.",
        },
        {
            "start_ms": 10482,
            "end_ms": 18782,
            "text": "정확도만큼 고객이 납득할 수 있는 판단 과정이 중요합니다.",
        },
    ]

    active = [
        seg for seg in captions
        if seg["start_ms"] <= local_ms < seg["end_ms"]
    ]

    assert local_ms == 12458
    assert [seg["text"] for seg in active] == [
        "정확도만큼 고객이 납득할 수 있는 판단 과정이 중요합니다."
    ]


def test_caption_bearing_remotion_failure_does_not_fall_back_to_static(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from pipelines import scene_render

    def fail_render(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("simulated remotion failure")

    fake_render_template = types.SimpleNamespace(
        render_scene=fail_render,
        validate_template_type=lambda *_args, **_kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "render_template", fake_render_template)
    monkeypatch.setattr(
        scene_render,
        "_render_static",
        lambda *_args, **_kwargs: Path(_args[3]).write_bytes(b"captionless fallback"),
    )

    audio_path = tmp_path / "scene.mp3"
    slide_path = tmp_path / "scene.png"
    audio_path.write_bytes(b"placeholder")
    slide_path.write_bytes(b"placeholder")
    output_path = tmp_path / "scene.mp4"
    scene = {
        "id": 6,
        "template_type": "flow_steps",
        "audio_path": str(audio_path),
        "slide_path": str(slide_path),
        "audio_duration_sec": 1.0,
        "caption_segments": [
            {"start_ms": 0, "end_ms": 1000, "text": "caption must not disappear"}
        ],
    }

    with pytest.raises(RuntimeError, match="caption_segments"):
        scene_render.render_scene(scene, output_path, force=True)

    assert not output_path.exists()


def test_render_scenes_prevalidates_all_retired_templates_before_partial_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from pipelines import scene_render

    calls: list[int] = []

    def fake_render_scene(scene: dict, output_path: Path, *, force: bool = False) -> Path:
        calls.append(int(scene["id"]))
        output_path.write_bytes(b"partial")
        return output_path

    monkeypatch.setattr(scene_render, "render_scene", fake_render_scene)

    scenes = [
        {"id": 1, "template_type": "flow_steps"},
        {"id": 2, "template_type": "architecture_diagram"},
    ]

    with pytest.raises(RuntimeError, match="retired_template_type:architecture_diagram"):
        scene_render.render_scenes(scenes, tmp_path, force=True)

    assert calls == []
    assert not list(tmp_path.glob("*.mp4"))


def test_retired_template_failure_never_falls_back_even_without_captions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from pipelines import scene_render

    def fail_render(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError(
            "Retired template type rejected for scene 6: "
            "retired_template_type:architecture_diagram; regenerate the scene"
        )

    def fail_validate(*_args: object, **_kwargs: object) -> None:
        raise ValueError(
            "Retired template type rejected for scene 6: "
            "retired_template_type:architecture_diagram; regenerate the scene"
        )

    fake_render_template = types.SimpleNamespace(
        render_scene=fail_render,
        validate_template_type=fail_validate,
    )
    monkeypatch.setitem(sys.modules, "render_template", fake_render_template)
    monkeypatch.setattr(
        scene_render,
        "_render_static",
        lambda *_args, **_kwargs: Path(_args[3]).write_bytes(b"retired fallback"),
    )

    audio_path = tmp_path / "scene.mp3"
    slide_path = tmp_path / "scene.png"
    audio_path.write_bytes(b"placeholder")
    slide_path.write_bytes(b"placeholder")
    output_path = tmp_path / "scene.mp4"
    scene = {
        "id": 6,
        "template_type": "architecture_diagram",
        "audio_path": str(audio_path),
        "slide_path": str(slide_path),
        "audio_duration_sec": 1.0,
        "caption_segments": [],
    }

    with pytest.raises(RuntimeError, match="template validation"):
        scene_render.render_scene(scene, output_path, force=True)

    assert not output_path.exists()


def test_scene_render_validates_template_before_cache_reuse(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from pipelines import scene_render

    def fail_validate(*_args: object, **_kwargs: object) -> None:
        raise ValueError(
            "Retired template type rejected for scene 6: "
            "retired_template_type:architecture_diagram; regenerate the scene"
        )

    fake_render_template = types.SimpleNamespace(validate_template_type=fail_validate)
    monkeypatch.setitem(sys.modules, "render_template", fake_render_template)

    output_path = tmp_path / "scene.mp4"
    output_path.write_bytes(b"old captionless cache")
    scene = {
        "id": 6,
        "template_type": "architecture_diagram",
        "audio_duration_sec": 1.0,
    }

    with pytest.raises(RuntimeError, match="retired_template_type:architecture_diagram"):
        scene_render.render_scene(scene, output_path, force=False)

    assert output_path.read_bytes() == b"old captionless cache"


def test_render_scenes_raises_when_any_scene_render_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from pipelines import scene_render

    def fake_validate_scene_templates(_scenes: list[dict]) -> None:
        return None

    fake_render_template = types.SimpleNamespace(
        validate_scene_templates=fake_validate_scene_templates
    )
    monkeypatch.setitem(sys.modules, "render_template", fake_render_template)

    def fake_render_scene(scene: dict, output_path: Path, *, force: bool = False) -> Path:
        if scene["id"] == 2:
            raise RuntimeError("scene 2 failed")
        output_path.write_bytes(b"ok")
        return output_path

    monkeypatch.setattr(scene_render, "render_scene", fake_render_scene)

    with pytest.raises(RuntimeError, match="scene_render failed for 1/2 scenes"):
        scene_render.render_scenes(
            [
                {"id": 1, "template_type": "flow_steps"},
                {"id": 2, "template_type": "flow_steps"},
            ],
            tmp_path,
            force=True,
        )
