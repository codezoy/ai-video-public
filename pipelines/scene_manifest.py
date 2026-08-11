"""Scene Manifest Validator.

scene_render 직전에 씬 수·오디오 수·슬라이드 수 일치 여부와
파일 존재·인덱스 연속성을 검증한다.
불일치 발견 시 RuntimeError를 발생시켜 파이프라인을 중단한다.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)


def validate(
    scenes_json: Path,
    audio_dir: Path,
    slides_dir: Path,
    narration_dir: Path | None = None,
) -> None:
    """씬 정합성을 검증한다.

    Args:
        scenes_json: scenes.json 경로
        audio_dir: audio 디렉토리 (scene{NN}.mp3)
        slides_dir: slides 디렉토리 (scene{NN}.png)
        narration_dir: 나레이션 디렉토리 (선택 — 전달 시 .txt 파일도 검증)

    Raises:
        RuntimeError: 정합성 오류 발견 시
    """
    if not scenes_json.exists():
        raise RuntimeError(f"[MANIFEST_ERROR] scenes.json 없음: {scenes_json}")

    try:
        data = json.loads(scenes_json.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"[MANIFEST_ERROR] scenes.json 파싱 실패: {exc}") from exc

    scenes = data.get("scenes", [])
    if not scenes:
        raise RuntimeError("[MANIFEST_ERROR] scenes.json에 씬이 없음")

    missing_id = [i for i, s in enumerate(scenes) if "id" not in s]
    if missing_id:
        raise RuntimeError(
            f"[MANIFEST_ERROR] 씬 {missing_id}에 'id' 필드 없음 — scenes.json 손상"
        )
    scene_ids = [int(s["id"]) for s in scenes]
    n = len(scene_ids)
    errors: list[str] = []

    # 인덱스 연속성 검사
    first = scene_ids[0]
    expected = list(range(first, first + n))
    if scene_ids != expected:
        errors.append(
            f"scene id 연속성 오류: expected={expected[:8]}... got={scene_ids[:8]}..."
        )

    # Audio 검사
    if audio_dir.exists():
        missing_audio = [
            sid for sid in scene_ids
            if not (audio_dir / f"scene{sid:02d}.mp3").exists()
        ]
        if missing_audio:
            errors.append(
                f"audio 파일 누락 {len(missing_audio)}개: {missing_audio[:8]}"
            )
        audio_files = sorted(audio_dir.glob("scene*.mp3"))
        if len(audio_files) != n:
            errors.append(
                f"audio 파일 수 불일치: scenes={n}, audio files={len(audio_files)}"
            )
    else:
        errors.append(f"audio 디렉토리 없음: {audio_dir}")

    # Slides 검사
    if slides_dir.exists():
        missing_slides = [
            sid for sid in scene_ids
            if not (slides_dir / f"scene{sid:02d}.png").exists()
        ]
        if missing_slides:
            errors.append(
                f"slide 파일 누락 {len(missing_slides)}개: {missing_slides[:8]}"
            )
        slide_files = sorted(slides_dir.glob("scene*.png"))
        if len(slide_files) != n:
            errors.append(
                f"slide 파일 수 불일치: scenes={n}, slide files={len(slide_files)}"
            )
    else:
        errors.append(f"slides 디렉토리 없음: {slides_dir}")

    # Narration 검사 (선택)
    if narration_dir is not None and narration_dir.exists():
        narr_files = sorted(narration_dir.glob("scene*.txt"))
        if len(narr_files) != n:
            errors.append(
                f"narration 파일 수 불일치: scenes={n}, narration files={len(narr_files)}"
            )

    if errors:
        msg = (
            f"[MANIFEST_ERROR] Scene 정합성 검증 실패 "
            f"({n}개 씬):\n"
            + "\n".join(f"  - {e}" for e in errors)
        )
        log.error(msg)
        raise RuntimeError(msg)

    log.info("[scene_manifest] PASS — %d씬 정합성 확인 완료", n)
