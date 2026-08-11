"""Motion Narration Adapter — AI Motion Mode TTS/Caption 브릿지.

Template Mode의 TTS/Caption 산출물을 AI Motion Mode에 연결한다.

Input:
  work/scenes.json              (script → TTS → caption 실행된 씬 데이터)
  work/motion/primitive_tree.json  (AI Motion 씬 ID 목록)

Output:
  work/motion/narration_manifest.json

Manifest 스키마:
  {
    "generated_at": "ISO8601",
    "scenes": [
      {
        "scene_id": "scene01",
        "narration": "...",
        "audio_path": "/abs/path/work/audio/scene00.mp3",
        "audio_duration_ms": 8500,
        "caption_segments": [{"start_ms": 0, "end_ms": 2000, "text": "..."}]
      }
    ]
  }

매칭 전략:
  - scenes.json[i] → primitive_tree[i] (인덱스 기반)
  - 길이가 다르면 min(len(scenes), len(trees)) 까지만 처리 (경고 출력)
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent
_WORK_DIR = _PROJECT_ROOT / "work"
_AUDIO_DIR = _WORK_DIR / "audio"
_NARRATION_DIR = _WORK_DIR / "narration"
_SCENES_JSON = _WORK_DIR / "scenes.json"
_PRIMITIVE_TREE_JSON = _WORK_DIR / "motion" / "primitive_tree.json"
_MANIFEST_JSON = _WORK_DIR / "motion" / "narration_manifest.json"


# ────────────────────────────────────────────────────────────────
# Manifest Schema
# ────────────────────────────────────────────────────────────────

def _make_manifest_scene(
    scene_id: str,
    narration: str,
    audio_path: Path | None,
    audio_duration_ms: int,
    caption_segments: list[dict],
) -> dict:
    return {
        "scene_id": scene_id,
        "narration": narration,
        "audio_path": str(audio_path.resolve()) if audio_path and audio_path.exists() else "",
        "audio_duration_ms": audio_duration_ms,
        "caption_segments": caption_segments,
    }


# ────────────────────────────────────────────────────────────────
# TTS / Caption helpers
# ────────────────────────────────────────────────────────────────

def _ensure_tts(
    scene: dict,
    audio_dir: Path,
    narration_dir: Path,
    topic: str | None,
) -> tuple[Path | None, int]:
    """씬의 TTS MP3가 없으면 synth_scene_to_mp3를 호출한다.

    Returns:
        (mp3_path, audio_duration_ms)
    """
    audio_path_str = scene.get("audio_path", "")
    audio_duration_ms: int = scene.get("audio_duration_ms", 0)

    if audio_path_str and Path(audio_path_str).exists() and audio_duration_ms > 0:
        log.debug("TTS 캐시 사용: %s", audio_path_str)
        return Path(audio_path_str), audio_duration_ms

    narration = scene.get("narration", "").strip()
    if not narration:
        log.warning("씬 %s: narration 없음 → TTS 스킵", scene.get("id", "?"))
        return None, 0

    pipelines_dir = str(Path(__file__).parent)
    if pipelines_dir not in sys.path:
        sys.path.insert(0, pipelines_dir)

    from synth_narration import synth_scene_to_mp3  # type: ignore[import]

    audio_dir.mkdir(parents=True, exist_ok=True)
    narration_dir.mkdir(parents=True, exist_ok=True)

    mp3_path = synth_scene_to_mp3(
        scene,
        sentence_wav_dir=narration_dir,
        audio_dir=audio_dir,
        topic=topic,
    )
    return mp3_path, scene.get("audio_duration_ms", 0)


def _ensure_captions(
    scene: dict,
    audio_duration_ms: int,
) -> list[dict]:
    """씬의 caption_segments가 없으면 caption_from_narration.generate를 호출한다."""
    existing = scene.get("caption_segments")
    if existing:
        return existing

    narration = scene.get("narration", "").strip()
    if not narration or audio_duration_ms <= 0:
        log.warning(
            "씬 %s: caption 생성 불가 (narration=%s, duration=%dms)",
            scene.get("id", "?"), bool(narration), audio_duration_ms,
        )
        return []

    pipelines_dir = str(Path(__file__).parent)
    if pipelines_dir not in sys.path:
        sys.path.insert(0, pipelines_dir)

    from caption_from_narration import generate  # type: ignore[import]
    return generate(narration, audio_duration_ms)


# ────────────────────────────────────────────────────────────────
# Core: build manifest
# ────────────────────────────────────────────────────────────────

def build_manifest(
    scenes_json: Path,
    primitive_tree_json: Path,
    audio_dir: Path,
    narration_dir: Path,
    topic: str | None = None,
) -> list[dict]:
    """scenes.json + primitive_tree.json → manifest scenes 리스트.

    Args:
        scenes_json: Template pipeline이 생성한 work/scenes.json
        primitive_tree_json: AI Motion pipeline의 work/motion/primitive_tree.json
        audio_dir: TTS MP3 출력 디렉토리
        narration_dir: 문장별 WAV 중간 산출물 디렉토리
        topic: 프로젝트 슬러그 (TTS 엔진 선택용)

    Returns:
        manifest scenes 리스트 (narration_manifest.json의 "scenes" 키 값)
    """
    if not scenes_json.exists():
        log.error("scenes.json 없음: %s", scenes_json)
        sys.exit(1)

    if not primitive_tree_json.exists():
        log.error("primitive_tree.json 없음: %s", primitive_tree_json)
        sys.exit(1)

    raw_scenes = json.loads(scenes_json.read_text(encoding="utf-8"))
    if isinstance(raw_scenes, dict):
        scenes: list[dict] = raw_scenes.get("scenes", [])
    else:
        scenes = raw_scenes

    trees: list[dict] = json.loads(primitive_tree_json.read_text(encoding="utf-8"))
    if not isinstance(trees, list):
        log.error("primitive_tree.json가 배열 형식이 아님")
        sys.exit(1)

    count = min(len(scenes), len(trees))
    if len(scenes) != len(trees):
        log.warning(
            "씬 수 불일치: scenes.json=%d, primitive_tree.json=%d → %d개 처리",
            len(scenes), len(trees), count,
        )

    manifest_scenes: list[dict] = []

    for i in range(count):
        scene = scenes[i]
        tree = trees[i]
        scene_id = tree.get("scene_id", f"scene{i+1:02d}")

        log.info("[NARRATION_ADAPTER] 씬 %d/%d: scene_id=%s", i + 1, count, scene_id)

        # TTS
        mp3_path, audio_duration_ms = _ensure_tts(scene, audio_dir, narration_dir, topic)

        # Caption
        caption_segments = _ensure_captions(scene, audio_duration_ms)

        entry = _make_manifest_scene(
            scene_id=scene_id,
            narration=scene.get("narration", ""),
            audio_path=mp3_path,
            audio_duration_ms=audio_duration_ms,
            caption_segments=caption_segments,
        )
        manifest_scenes.append(entry)

        print(
            f"[NARRATION_ADAPTER] scene_id={scene_id}"
            f" audio_exists={bool(mp3_path and mp3_path.exists())}"
            f" audio_duration_ms={audio_duration_ms}"
            f" caption_count={len(caption_segments)}",
            flush=True,
        )

    return manifest_scenes


def run(
    scenes_json: Path | None = None,
    primitive_tree_json: Path | None = None,
    audio_dir: Path | None = None,
    narration_dir: Path | None = None,
    output_path: Path | None = None,
    topic: str | None = None,
) -> Path:
    """엔트리포인트: manifest 생성 후 파일로 저장.

    Returns:
        저장된 narration_manifest.json 경로
    """
    scenes_json = scenes_json or _SCENES_JSON
    primitive_tree_json = primitive_tree_json or _PRIMITIVE_TREE_JSON
    audio_dir = audio_dir or _AUDIO_DIR
    narration_dir = narration_dir or _NARRATION_DIR
    output_path = output_path or _MANIFEST_JSON

    log.info("[NARRATION_ADAPTER] start scenes=%s tree=%s", scenes_json.name, primitive_tree_json.name)

    manifest_scenes = build_manifest(
        scenes_json=scenes_json,
        primitive_tree_json=primitive_tree_json,
        audio_dir=audio_dir,
        narration_dir=narration_dir,
        topic=topic,
    )

    manifest = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_scenes_json": str(scenes_json),
        "source_primitive_tree": str(primitive_tree_json),
        "scenes": manifest_scenes,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    audio_count = sum(1 for s in manifest_scenes if s["audio_path"])
    caption_count = sum(1 for s in manifest_scenes if s["caption_segments"])
    print(
        f"[NARRATION_ADAPTER] manifest saved: scenes={len(manifest_scenes)}"
        f" with_audio={audio_count} with_captions={caption_count}"
        f" → {output_path}",
        flush=True,
    )
    log.info("[NARRATION_ADAPTER] done: %s", output_path)
    return output_path


# ────────────────────────────────────────────────────────────────
# Validation
# ────────────────────────────────────────────────────────────────

def validate_manifest(manifest_path: Path) -> bool:
    """narration_manifest.json 스키마 검증.

    Returns:
        True if valid, False otherwise
    """
    if not manifest_path.exists():
        print(f"[NARRATION_ADAPTER_VALIDATE] FAIL manifest not found: {manifest_path}", flush=True)
        return False

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"[NARRATION_ADAPTER_VALIDATE] FAIL json_error: {exc}", flush=True)
        return False

    scenes = data.get("scenes", [])
    if not scenes:
        print("[NARRATION_ADAPTER_VALIDATE] FAIL scenes empty", flush=True)
        return False

    errors: list[str] = []
    required_keys = {"scene_id", "narration", "audio_path", "audio_duration_ms", "caption_segments"}
    for i, s in enumerate(scenes):
        missing = required_keys - set(s.keys())
        if missing:
            errors.append(f"scene[{i}] missing keys: {missing}")

    if errors:
        for err in errors:
            print(f"[NARRATION_ADAPTER_VALIDATE] FAIL {err}", flush=True)
        return False

    audio_count = sum(1 for s in scenes if s.get("audio_path"))
    caption_count = sum(1 for s in scenes if s.get("caption_segments"))
    print(
        f"[NARRATION_ADAPTER_VALIDATE] PASS scenes={len(scenes)}"
        f" with_audio={audio_count} with_captions={caption_count}",
        flush=True,
    )
    return True


# ────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────

def _build_parser() -> Any:
    import argparse
    p = argparse.ArgumentParser(
        prog="motion_narration_adapter.py",
        description="AI Motion Mode TTS/Caption 브릿지 — narration_manifest.json 생성",
    )
    sub = p.add_subparsers(dest="cmd")

    run_p = sub.add_parser("run", help="manifest 생성")
    run_p.add_argument("--scenes-json", default=None, help="work/scenes.json 경로")
    run_p.add_argument("--primitive-tree", default=None, help="primitive_tree.json 경로")
    run_p.add_argument("--output", default=None, help="narration_manifest.json 출력 경로")
    run_p.add_argument("--topic", default=None, help="프로젝트 슬러그")

    sub.add_parser("validate", help="기존 manifest 스키마 검증")

    return p


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = _build_parser()
    args = p.parse_args()

    if args.cmd == "validate":
        ok = validate_manifest(_MANIFEST_JSON)
        sys.exit(0 if ok else 1)

    elif args.cmd == "run":
        run(
            scenes_json=Path(args.scenes_json) if args.scenes_json else None,
            primitive_tree_json=Path(args.primitive_tree) if args.primitive_tree else None,
            output_path=Path(args.output) if args.output else None,
            topic=args.topic,
        )

    else:
        p.print_help()


if __name__ == "__main__":
    main()
