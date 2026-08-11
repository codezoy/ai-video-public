"""caption_from_narration.py — Narration 텍스트 직접 기반 caption_segments 생성.

Whisper 없이 narration + audio_duration_ms 만으로 caption_segments를 생성한다.
Korean sentence/phrase boundary detection + proportional char-count timing.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

TARGET_MAX_CHARS: int = 35
HARD_MAX_CHARS: int = 50

# 한국어 문장 끝 패턴 (완결형 어미 + 선택적 구두점)
_SENTENCE_END_RE = re.compile(
    r"""(?x)
    (?:
        습니다|니다|해요|어요|아요|세요|셔요|예요|이에요|죠|
        나요|군요|네요|는걸요|는군요|랍니다|답니다|
        겠습니다|겠어요|합니다|입니다|됩니다
    )\s*[.!?！？。]?\s*$
    |
    [.!?！？。]\s*$
    """,
    re.VERBOSE,
)

# 구 경계: 접속사/부사절 앞 분리 지점 (lookahead → 접속사 자체는 다음 청크에 유지)
_PHRASE_BOUNDARY_RE = re.compile(
    r"""(?x)
    (?=
        (?:
            그리고|하지만|그러나|또한|즉|따라서|그래서|
            반면에?|그런데|또|그러면|그러므로|
            왜냐하면|결국|실제로|특히|예를\s*들어
        )\s+
    )
    """,
    re.VERBOSE,
)


def _is_sentence_end(text: str) -> bool:
    return bool(_SENTENCE_END_RE.search(text.rstrip()))


def _force_split(text: str) -> list[str]:
    """HARD_MAX_CHARS 초과 텍스트를 단어 경계에서 강제 분리."""
    if len(text) <= HARD_MAX_CHARS:
        return [text]

    result: list[str] = []
    remaining = text.strip()
    while len(remaining) > HARD_MAX_CHARS:
        split_at = remaining.rfind(" ", 0, HARD_MAX_CHARS)
        if split_at <= 0:
            split_at = HARD_MAX_CHARS
        result.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        result.append(remaining)
    return result


def semantic_split(text: str) -> list[str]:
    """텍스트를 의미 단위로 분리.

    1. 개행 기준 1차 분리
    2. 문장 끝 어미 기준 2차 분리
    3. 구 경계 기준 3차 분리
    4. 짧은 조각 병합 (TARGET_MAX_CHARS 미만 + 합쳐도 TARGET_MAX_CHARS 이하)
    5. HARD_MAX_CHARS 초과 강제 분리
    """
    # 1. 개행 기준 분리
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return []

    # 2. 문장 끝 어미 기준으로 재분리
    sentence_chunks: list[str] = []
    for line in lines:
        # 마침표/어미 뒤에서 분리: 패턴 매칭된 위치 기준 split
        parts = _split_on_sentence_endings(line)
        sentence_chunks.extend(parts)

    # 3. 구 경계 기준으로 재분리 (긴 청크만)
    phrase_chunks: list[str] = []
    for chunk in sentence_chunks:
        if len(chunk) > TARGET_MAX_CHARS:
            sub = _split_on_phrase_boundaries(chunk)
            phrase_chunks.extend(sub)
        else:
            phrase_chunks.append(chunk)

    # 4. 짧은 조각 병합
    merged = _merge_short_segments(phrase_chunks)

    # 5. HARD_MAX_CHARS 초과 강제 분리
    final: list[str] = []
    for seg in merged:
        final.extend(_force_split(seg))

    return [s for s in final if s]


def _split_on_sentence_endings(text: str) -> list[str]:
    """문장 끝 어미/구두점 기준으로 분리."""
    # 어미 패턴 뒤에서 분리 (어미 포함하여 앞 청크에 붙임)
    pattern = re.compile(
        r"""(?x)
        (
            (?:
                습니다|니다|해요|어요|아요|세요|셔요|예요|이에요|죠|
                나요|군요|네요|는걸요|는군요|랍니다|답니다|
                겠습니다|겠어요|합니다|입니다|됩니다
            )\s*[.!?！？。]?
            |
            [!?！？。]          # 느낌표/물음표는 항상 분리
            |
            \.(?=\s|$)         # 마침표는 뒤에 공백이나 문자열 끝이 있을 때만 분리 (URL/버전 번호 제외)
        )\s*
        """,
        re.VERBOSE,
    )

    parts: list[str] = []
    last_end = 0
    for m in pattern.finditer(text):
        end = m.end()
        chunk = text[last_end:end].strip()
        if chunk:
            parts.append(chunk)
        last_end = end

    remainder = text[last_end:].strip()
    if remainder:
        parts.append(remainder)

    return parts if parts else [text]


def _split_on_phrase_boundaries(text: str) -> list[str]:
    """접속사/부사 기준으로 앞에서 분리. 접속사는 뒤 청크에 포함된다."""
    parts = _PHRASE_BOUNDARY_RE.split(text)
    result = [p.strip() for p in parts if p.strip()]
    return result if result else [text]


def _merge_short_segments(segments: list[str]) -> list[str]:
    """TARGET_MAX_CHARS 미만의 짧은 조각을 이전/다음과 병합."""
    if not segments:
        return []

    merged: list[str] = [segments[0]]
    for seg in segments[1:]:
        prev = merged[-1]
        combined = prev + " " + seg
        if len(prev) < TARGET_MAX_CHARS // 2 and len(combined) <= TARGET_MAX_CHARS:
            merged[-1] = combined.strip()
        else:
            merged.append(seg)

    return merged


def timing_allocate(segments: list[str], total_ms: int) -> list[dict]:
    """글자 수 비율로 타이밍 배분. 전체가 [0, total_ms]를 빈틈없이 채운다.

    Returns:
        list of {"start_ms": int, "end_ms": int, "text": str}
    """
    if not segments:
        return []
    if len(segments) == 1:
        return [{"start_ms": 0, "end_ms": total_ms, "text": segments[0]}]

    total_chars = sum(len(s) for s in segments)
    if total_chars == 0:
        each = total_ms // len(segments)
        result = []
        for i, seg in enumerate(segments):
            start = i * each
            end = total_ms if i == len(segments) - 1 else (i + 1) * each
            result.append({"start_ms": start, "end_ms": end, "text": seg})
        return result

    result: list[dict] = []
    cursor_ms = 0
    for i, seg in enumerate(segments):
        is_last = i == len(segments) - 1
        if is_last:
            end_ms = total_ms
        else:
            ratio = len(seg) / total_chars
            duration = int(round(total_ms * ratio))
            end_ms = cursor_ms + duration

        result.append({"start_ms": cursor_ms, "end_ms": end_ms, "text": seg})
        cursor_ms = end_ms

    return result


def generate(narration: str, audio_duration_ms: int) -> list[dict]:
    """Narration + duration → caption_segments.

    Args:
        narration: 씬 대사 텍스트
        audio_duration_ms: TTS 오디오 길이 (ms)

    Returns:
        list of {"start_ms": int, "end_ms": int, "text": str}
    """
    if not narration or not narration.strip():
        logger.warning("narration 없음 → 빈 caption_segments 반환")
        return []

    if audio_duration_ms <= 0:
        logger.warning("audio_duration_ms=%d ≤ 0 → 0으로 처리", audio_duration_ms)
        return [{"start_ms": 0, "end_ms": 0, "text": narration.strip()}]

    segments = semantic_split(narration)
    if not segments:
        logger.warning("semantic_split 결과 없음 → 전체를 단일 캡션으로")
        segments = [narration.strip()]

    captions = timing_allocate(segments, audio_duration_ms)
    logger.debug("generate: %d 세그먼트 → %d 캡션", len(segments), len(captions))
    return captions


def run_on_scenes(scenes_json: Path) -> None:
    """scenes.json 내 모든 씬에 caption_from_narration 적용.

    각 씬에 caption_segments와 caption_source='direct'를 설정한다.
    audio_duration_ms가 없는 씬은 건너뛴다.
    """
    if not scenes_json.exists():
        raise FileNotFoundError(f"scenes.json 없음: {scenes_json}")

    data = json.loads(scenes_json.read_text(encoding="utf-8"))
    scenes: list[dict] = data if isinstance(data, list) else data.get("scenes", [])

    updated = 0
    skipped = 0
    for i, scene in enumerate(scenes):
        narration: str = scene.get("narration", "").strip()
        duration_ms: int = scene.get("audio_duration_ms", 0)

        if not narration:
            logger.warning("씬 %d: narration 없음 → 건너뜀", i)
            skipped += 1
            continue

        if duration_ms <= 0:
            logger.warning("씬 %d: audio_duration_ms=%d → 건너뜀", i, duration_ms)
            skipped += 1
            continue

        scene["caption_segments"] = generate(narration, duration_ms)
        scene["caption_source"] = "direct"
        updated += 1
        logger.info("씬 %d: %d 캡션 생성 (duration=%dms)", i, len(scene["caption_segments"]), duration_ms)

    if isinstance(data, list):
        out_data = scenes
    else:
        data["scenes"] = scenes
        out_data = data

    scenes_json.write_text(json.dumps(out_data, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("run_on_scenes 완료: %d 씬 업데이트, %d 씬 건너뜀", updated, skipped)
