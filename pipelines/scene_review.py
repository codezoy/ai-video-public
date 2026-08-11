"""Scene LLM Review.

direct_scene_gen이 생성한 scenes.json에서
반복 문장·중복 나레이션을 검출·제거한다.

단계:
  1. 알고리즘 dedup  — 씬 내/씬 간 동일 문장 제거
  2. LLM 의미 중복 검토 — judge role로 cross-scene 의미 중복 정리 (best-effort)

실패해도 파이프라인을 중단하지 않는다.
알고리즘 단계 결과는 LLM 실패와 무관하게 항상 저장한다.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

_MAX_SCENES_FOR_LLM = 80
_MIN_SENTENCE_LEN = 5


def _split_sentences(text: str) -> list[str]:
    return [
        p.strip()
        for p in re.split(r"(?<=[.!?。！？\n])\s*", text.strip())
        if p.strip()
    ]


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def _algo_dedup(scenes: list[dict]) -> int:
    """씬 간 동일 문장을 제거한다. 수정된 씬 수를 반환한다."""
    seen: set[str] = set()
    changed = 0

    for scene in scenes:
        narration = scene.get("narration", "")
        if not narration:
            continue

        sentences = _split_sentences(narration)
        unique: list[str] = []
        for s in sentences:
            norm = _normalize(s)
            if norm and len(norm) >= _MIN_SENTENCE_LEN and norm not in seen:
                seen.add(norm)
                unique.append(s)

        if len(unique) < len(sentences):
            scene["narration"] = " ".join(unique)
            changed += 1

    return changed


def _llm_review(scenes: list[dict], topic: str) -> int:
    """LLM으로 의미 중복 씬을 감지하고 정리한다.

    실패 시 0을 반환하고 로그만 남긴다 (best-effort).
    """
    try:
        from llm_client import generate  # type: ignore[import]
    except ImportError:
        log.warning("[scene_review] llm_client import 실패 — LLM 단계 스킵")
        return 0

    narration_lines = [
        f"[씬{s.get('id', '?')}] {s.get('narration', '')[:200]}"
        for s in scenes
    ]
    narration_text = "\n".join(narration_lines)

    prompt = (
        f'다음은 교육 영상 "{topic}"의 씬별 나레이션 목록이다.\n\n'
        f"{narration_text}\n\n"
        "위 나레이션에서 의미상 중복되거나 반복되는 씬을 찾아 "
        "아래 JSON 형식으로만 응답하라. "
        "수정이 필요한 씬만 포함하라. "
        '변경 없으면 {"changes": []} 를 반환하라.\n'
        "```json\n"
        '{"changes": [{"scene_id": <int>, "issue": "<중복 유형>", '
        '"cleaned": "<수정된 나레이션 200자 이내>"}]}\n'
        "```"
    )

    try:
        raw = generate(prompt, role="judge", max_tokens=2048, timeout_sec=60)
    except Exception as exc:
        log.warning("[scene_review] LLM generate 실패: %s", exc)
        return 0

    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        log.warning("[scene_review] LLM 응답에서 JSON 파싱 실패")
        return 0

    try:
        data = json.loads(m.group())
    except json.JSONDecodeError as exc:
        log.warning("[scene_review] LLM JSON 디코드 실패: %s", exc)
        return 0

    changes = data.get("changes", [])
    scene_map = {int(s["id"]): s for s in scenes if "id" in s}
    applied = 0

    for change in changes:
        try:
            sid = int(change.get("scene_id", -1))
        except (TypeError, ValueError):
            continue
        cleaned = (change.get("cleaned") or "").strip()
        if sid in scene_map and cleaned and len(cleaned) >= _MIN_SENTENCE_LEN:
            scene_map[sid]["narration"] = cleaned
            applied += 1

    return applied


def run(
    scenes_json: Path,
    run_dir: Path,
    topic: str,
    force: bool = False,
) -> dict[str, object]:
    """scenes.json을 in-place로 정리하고 결과 dict를 반환한다.

    Returns:
        {"status": "PASS", "algo_changes": int, "llm_changes": int}
    """
    if not scenes_json.exists():
        log.error("[scene_review] scenes.json 없음: %s", scenes_json)
        return {"status": "PASS", "algo_changes": 0, "llm_changes": 0}

    try:
        data = json.loads(scenes_json.read_text(encoding="utf-8"))
    except Exception as exc:
        log.error("[scene_review] scenes.json 읽기 실패: %s", exc)
        return {"status": "PASS", "algo_changes": 0, "llm_changes": 0}

    scenes = data.get("scenes", [])
    if not scenes:
        log.warning("[scene_review] 씬이 없음 — 스킵")
        return {"status": "PASS", "algo_changes": 0, "llm_changes": 0}

    algo_changes = _algo_dedup(scenes)

    llm_changes = 0
    if len(scenes) <= _MAX_SCENES_FOR_LLM:
        llm_changes = _llm_review(scenes, topic)
    else:
        log.info(
            "[scene_review] 씬 수 %d > %d — LLM 단계 스킵",
            len(scenes),
            _MAX_SCENES_FOR_LLM,
        )

    try:
        scenes_json.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        log.error("[scene_review] scenes.json 쓰기 실패: %s", exc)

    log.info(
        "[scene_review] 완료: 알고리즘=%d씬, LLM=%d씬 수정",
        algo_changes,
        llm_changes,
    )
    return {"status": "PASS", "algo_changes": algo_changes, "llm_changes": llm_changes}
