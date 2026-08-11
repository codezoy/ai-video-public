"""caption_validator.py — Caption segment 품질 검증 및 자동 재생성 루프.

검증 규칙:
  Rule 1: 모든 음성 구간에 caption 존재 (coverage ≥ 95%)
  Rule 2: 문장 중간 누락 금지 (word_timestamps 기반)
  Rule 3: word_timestamps 누락 감지
  Rule 4: caption_segments time coverage 계산
  Rule 5: coverage < 95% → 자동 재생성 (최대 3회)
  Rule 6: caption gap > 1000ms → FAIL
  Rule 7: 최종 PASS 전까지 최대 3회 재생성
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

COVERAGE_THRESHOLD = 0.95   # 95% 이상 커버리지 요구
MAX_GAP_MS = 1000           # 1초 초과 갭 FAIL
MAX_RETRY = 3               # 최대 재생성 횟수


@dataclass
class SceneValidationResult:
    scene_id: int | str
    audio_duration_ms: int
    covered_ms: int
    coverage: float           # 0.0 ~ 1.0
    max_gap_ms: int
    gaps: list[dict[str, Any]]
    missing_word_timestamps: bool
    caption_count: int
    status: str               # "PASS" | "FAIL"
    errors: list[str]


@dataclass
class ValidationReport:
    status: str               # "PASS" | "FAIL"
    total_coverage: float
    max_gap_ms: int
    retry_count: int
    scenes: list[SceneValidationResult]
    errors: list[str] = field(default_factory=list)


def _audio_duration_ms(scene: dict[str, Any]) -> int:
    """씬의 오디오 길이(ms)를 추정한다.

    우선순위:
    1. audio_duration_ms 필드 (명시 값)
    2. word_timestamps 마지막 end_ms
    3. caption_segments 마지막 end_ms
    """
    dur = scene.get("audio_duration_ms")
    if dur and isinstance(dur, (int, float)) and dur > 0:
        return int(dur)

    wts: list[dict] = scene.get("word_timestamps") or []
    if wts:
        return int(wts[-1].get("end_ms", 0))

    segs: list[dict] = scene.get("caption_segments") or []
    if segs:
        return int(segs[-1].get("end_ms", 0))

    return 0


def _covered_ms(segs: list[dict[str, Any]]) -> int:
    """caption_segments 가 실제로 커버하는 총 ms."""
    return sum(
        max(0, s.get("end_ms", 0) - s.get("start_ms", 0))
        for s in segs
    )


def _find_gaps(segs: list[dict[str, Any]], audio_duration_ms: int) -> list[dict[str, Any]]:
    """연속 caption_segments 사이의 gap 목록 반환.

    gap_ms > 0 인 항목만 포함.
    """
    gaps: list[dict[str, Any]] = []

    # 첫 캡션 시작 전 gap
    if segs and segs[0].get("start_ms", 0) > 0:
        gaps.append({
            "type": "lead",
            "start_ms": 0,
            "end_ms": segs[0]["start_ms"],
            "gap_ms": segs[0]["start_ms"],
        })

    for i in range(1, len(segs)):
        prev_end = segs[i - 1].get("end_ms", 0)
        cur_start = segs[i].get("start_ms", 0)
        gap = cur_start - prev_end
        if gap > 0:
            gaps.append({
                "type": "inter",
                "start_ms": prev_end,
                "end_ms": cur_start,
                "gap_ms": gap,
            })

    # 마지막 캡션 이후 gap
    if segs and audio_duration_ms > 0:
        tail_gap = audio_duration_ms - segs[-1].get("end_ms", 0)
        if tail_gap > 0:
            gaps.append({
                "type": "tail",
                "start_ms": segs[-1]["end_ms"],
                "end_ms": audio_duration_ms,
                "gap_ms": tail_gap,
            })

    return gaps


def _validate_scene(scene: dict[str, Any]) -> SceneValidationResult:
    """단일 씬의 caption 품질을 검증한다."""
    sid = scene.get("id", 0)
    errors: list[str] = []

    # Rule 3: word_timestamps 누락 (caption_source='direct' 이면 면제)
    missing_wt = not bool(scene.get("word_timestamps"))
    is_direct = scene.get("caption_source") == "direct"
    if missing_wt and not is_direct:
        errors.append("word_timestamps 없음 (whisper_align 미실행 또는 실패)")

    segs: list[dict] = scene.get("caption_segments") or []
    caption_count = len(segs)

    if not segs:
        errors.append("caption_segments 없음")
        return SceneValidationResult(
            scene_id=sid,
            audio_duration_ms=0,
            covered_ms=0,
            coverage=0.0,
            max_gap_ms=0,
            gaps=[],
            missing_word_timestamps=missing_wt,
            caption_count=0,
            status="FAIL",
            errors=errors,
        )

    audio_dur = _audio_duration_ms(scene)
    covered = _covered_ms(segs)
    coverage = (covered / audio_dur) if audio_dur > 0 else 0.0

    gaps = _find_gaps(segs, audio_dur)
    inter_gaps = [g for g in gaps if g["type"] == "inter"]
    max_gap = max((g["gap_ms"] for g in inter_gaps), default=0)

    # Rule 1: coverage ≥ 95%
    if coverage < COVERAGE_THRESHOLD:
        errors.append(
            f"coverage {coverage:.1%} < {COVERAGE_THRESHOLD:.0%} "
            f"(커버 {covered}ms / 오디오 {audio_dur}ms)"
        )

    # Rule 6: inter-caption gap ≤ 1000ms
    large_gaps = [g for g in inter_gaps if g["gap_ms"] > MAX_GAP_MS]
    if large_gaps:
        for g in large_gaps:
            errors.append(
                f"gap {g['gap_ms']}ms > {MAX_GAP_MS}ms "
                f"({g['start_ms']}ms ~ {g['end_ms']}ms)"
            )

    # Rule 2: word_timestamps 기반 문장 누락 검사
    if not missing_wt:
        wts: list[dict] = scene.get("word_timestamps", [])
        wt_words = {wt["word"].strip() for wt in wts if wt.get("word", "").strip()}
        cap_text = " ".join(s.get("text", "") for s in segs)
        cap_words = set(cap_text.split())
        missing_words = wt_words - cap_words
        if len(missing_words) > len(wt_words) * 0.05:  # 5% 이상 누락
            errors.append(
                f"word_timestamps 대비 누락 단어 {len(missing_words)}개 "
                f"({len(missing_words)/len(wt_words):.0%})"
            )

    status = "PASS" if not errors else "FAIL"

    return SceneValidationResult(
        scene_id=sid,
        audio_duration_ms=audio_dur,
        covered_ms=covered,
        coverage=coverage,
        max_gap_ms=max_gap,
        gaps=gaps,
        missing_word_timestamps=missing_wt,
        caption_count=caption_count,
        status=status,
        errors=errors,
    )


def validate(
    scenes: list[dict[str, Any]],
    retry_count: int = 0,
) -> ValidationReport:
    """scenes 목록의 모든 씬 caption을 검증한다.

    Args:
        scenes: scenes.json 의 "scenes" 리스트
        retry_count: 현재 재시도 횟수

    Returns:
        ValidationReport
    """
    scene_results: list[SceneValidationResult] = []
    all_errors: list[str] = []

    for scene in scenes:
        result = _validate_scene(scene)
        scene_results.append(result)
        if result.errors:
            all_errors.extend(
                f"[씬 {result.scene_id}] {e}" for e in result.errors
            )

    # 전체 coverage 계산
    total_audio = sum(r.audio_duration_ms for r in scene_results)
    total_covered = sum(r.covered_ms for r in scene_results)
    total_coverage = (total_covered / total_audio) if total_audio > 0 else 0.0

    # 전체 max gap
    global_max_gap = max((r.max_gap_ms for r in scene_results), default=0)

    status = "PASS" if not all_errors else "FAIL"

    return ValidationReport(
        status=status,
        total_coverage=total_coverage,
        max_gap_ms=global_max_gap,
        retry_count=retry_count,
        scenes=scene_results,
        errors=all_errors,
    )


def _bridge_gaps(
    segs: list[dict[str, Any]],
    audio_duration_ms: int,
) -> list[dict[str, Any]]:
    """caption_segments 사이 gap을 인접 캡션 확장으로 메운다.

    전략:
    - 인접 캡션 사이 gap: 중간 지점(midpoint)에서 분할 — 앞 캡션 end_ms 연장, 뒤 캡션 start_ms 앞당김
    - 마지막 캡션 이후 tail gap: 마지막 캡션 end_ms를 audio_duration_ms까지 연장
    """
    if not segs:
        return segs

    bridged = [dict(s) for s in segs]

    for i in range(len(bridged) - 1):
        gap = bridged[i + 1]["start_ms"] - bridged[i]["end_ms"]
        if gap > 0:
            mid = bridged[i]["end_ms"] + gap // 2
            bridged[i]["end_ms"] = mid
            bridged[i + 1]["start_ms"] = mid

    if audio_duration_ms > 0 and bridged[-1]["end_ms"] < audio_duration_ms:
        bridged[-1]["end_ms"] = audio_duration_ms

    return bridged


def validate_and_retry(
    scenes_json: Path,
    iter_dir: Path,
    max_retry: int = MAX_RETRY,
) -> ValidationReport:
    """caption 검증 → FAIL 시 재생성/갭 브리징 → 재검증 루프.

    전략:
      retry 1: GAP_SPLIT_MS 완화 재분할
      retry 2: gap bridging (인접 캡션 확장)
      retry 3: gap bridging + tail 연장 (full coverage)

    Args:
        scenes_json: scenes.json 경로
        iter_dir: 중간 산출물 디렉토리
        max_retry: 최대 재시도 횟수 (기본 3)

    Returns:
        최종 ValidationReport
    """
    pipelines_dir = str(Path(__file__).parent)
    if pipelines_dir not in sys.path:
        sys.path.insert(0, pipelines_dir)

    import caption_segmenter as _cseg  # type: ignore[import]
    from caption_segmenter import segment as _segment  # type: ignore[import]

    data = json.loads(scenes_json.read_text(encoding="utf-8"))
    scenes: list[dict] = data.get("scenes", [])

    report = validate(scenes, retry_count=0)
    log.info(
        "caption_validator: 초기 검증 — %s (coverage=%.1f%%, max_gap=%dms)",
        report.status, report.total_coverage * 100, report.max_gap_ms,
    )

    retry = 0
    while report.status == "FAIL" and retry < max_retry:
        retry += 1
        log.info("caption_validator: retry %d/%d", retry, max_retry)

        if retry == 1:
            # 전략 1: GAP_SPLIT_MS 완화 재분할
            log.info("  전략: GAP_SPLIT_MS 완화 재분할 (200ms)")
            _cseg.GAP_SPLIT_MS = 200
            _cseg.MAX_SEGMENT_MS = 2500
            _cseg.MAX_WORDS_PER_SEG = 6
            for scene in scenes:
                word_ts = scene.get("word_timestamps")
                if not word_ts:
                    continue
                try:
                    scene["caption_segments"] = _segment(word_ts)
                except Exception as exc:
                    log.warning("씬 %s caption 재생성 실패: %s", scene.get("id"), exc)

        elif retry == 2:
            # 전략 2: gap bridging (인접 캡션 사이 gap 메우기)
            log.info("  전략: gap bridging (인접 캡션 확장)")
            for scene in scenes:
                segs = scene.get("caption_segments") or []
                if not segs:
                    continue
                audio_dur = _audio_duration_ms(scene)
                scene["caption_segments"] = _bridge_gaps(segs, audio_dur)

        else:
            # 전략 3: 재분할 + full gap bridging
            log.info("  전략: 재분할 + full gap bridging")
            _cseg.GAP_SPLIT_MS = 100
            _cseg.MAX_SEGMENT_MS = 3000
            _cseg.MAX_WORDS_PER_SEG = 8
            for scene in scenes:
                word_ts = scene.get("word_timestamps")
                if not word_ts:
                    continue
                try:
                    new_segs = _segment(word_ts)
                    audio_dur = _audio_duration_ms(scene)
                    scene["caption_segments"] = _bridge_gaps(new_segs, audio_dur)
                except Exception as exc:
                    log.warning("씬 %s caption 재생성 실패: %s", scene.get("id"), exc)

        scenes_json.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        report = validate(scenes, retry_count=retry)
        log.info(
            "caption_validator: retry %d 결과 — %s (coverage=%.1f%%, max_gap=%dms)",
            retry, report.status, report.total_coverage * 100, report.max_gap_ms,
        )

    return report


def report_to_dict(report: ValidationReport) -> dict[str, Any]:
    """ValidationReport → JSON 직렬화 가능한 dict."""
    return {
        "status": report.status,
        "coverage_pct": round(report.total_coverage * 100, 2),
        "max_gap_ms": report.max_gap_ms,
        "max_gap_s": round(report.max_gap_ms / 1000, 3),
        "retry_count": report.retry_count,
        "errors": report.errors,
        "scenes": [
            {
                "scene_id": r.scene_id,
                "status": r.status,
                "audio_duration_ms": r.audio_duration_ms,
                "covered_ms": r.covered_ms,
                "coverage_pct": round(r.coverage * 100, 2),
                "max_gap_ms": r.max_gap_ms,
                "caption_count": r.caption_count,
                "missing_word_timestamps": r.missing_word_timestamps,
                "gaps": r.gaps,
                "errors": r.errors,
            }
            for r in report.scenes
        ],
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Caption validation loop.")
    parser.add_argument("scenes_json", type=Path, help="scenes.json 경로")
    parser.add_argument(
        "--iter-dir", type=Path, default=None,
        help="중간 산출물 디렉토리 (기본: scenes_json 부모)",
    )
    parser.add_argument(
        "--output", type=Path, default=None,
        help="caption_validation.json 출력 경로 (기본: iter_dir/caption_validation.json)",
    )
    parser.add_argument(
        "--max-retry", type=int, default=MAX_RETRY,
        help=f"최대 재시도 횟수 (기본: {MAX_RETRY})",
    )
    parser.add_argument(
        "--no-retry", action="store_true",
        help="검증만 수행 (재시도 없음)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    scenes_json: Path = args.scenes_json
    iter_dir: Path = args.iter_dir or scenes_json.parent
    output: Path = args.output or (iter_dir / "caption_validation.json")

    if not scenes_json.exists():
        log.error("scenes.json 없음: %s", scenes_json)
        sys.exit(1)

    if args.no_retry:
        data = json.loads(scenes_json.read_text(encoding="utf-8"))
        scenes: list[dict] = data.get("scenes", [])
        report = validate(scenes)
    else:
        report = validate_and_retry(
            scenes_json=scenes_json,
            iter_dir=iter_dir,
            max_retry=args.max_retry,
        )

    result = report_to_dict(report)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{'='*50}")
    print(f"Caption Validation: {report.status}")
    print(f"  Coverage : {result['coverage_pct']:.1f}% (threshold: {COVERAGE_THRESHOLD*100:.0f}%)")
    print(f"  Max Gap  : {result['max_gap_s']:.3f}s (threshold: {MAX_GAP_MS/1000:.1f}s)")
    print(f"  Retries  : {report.retry_count}")
    print(f"  Output   : {output}")
    if report.errors:
        print(f"  Errors   : {len(report.errors)}")
        for e in report.errors[:5]:
            print(f"    - {e}")
    print(f"{'='*50}\n")

    sys.exit(0 if report.status == "PASS" else 1)


if __name__ == "__main__":
    main()
