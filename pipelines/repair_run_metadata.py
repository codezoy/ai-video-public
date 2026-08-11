#!/usr/bin/env python3
"""repair_run_metadata.py — 기존 run의 audio 메타데이터를 복구하고 render를 재실행한다.

사용법:
  python pipelines/repair_run_metadata.py <run_id>
  python pipelines/repair_run_metadata.py <run_id> --dry-run

금지사항:
  - 새로운 Script/Scene/TTS 생성 금지
  - audio/ 폴더 및 MP3 파일 삭제 금지
  - stage_tts.done 삭제 금지
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
WORK_DIR = ROOT / "work"

# 재실행 대상 stage (downstream only — tts/render/slides는 보존)
_STAGES_TO_RERUN = [
    "caption_from_narration",
    "caption_validate",
    "scene_render",
    "final_concat",
    "qa",
]

# 절대 삭제 금지 stage
_PROTECTED_STAGES = {"tts", "script", "polish", "critique", "regen", "scenes",
                     "scene_quality", "scene_review", "render", "visual_correct",
                     "motion_anchor", "whisper_align", "caption_segment",
                     "caption_overlay"}


def repair_run_metadata(run_dir: Path) -> dict:
    """audio/ 폴더 스캔 → scenes.json의 audio_path + audio_duration_ms 복구."""
    scenes_json = run_dir / "scenes.json"
    audio_dir = run_dir / "audio"

    if not scenes_json.exists():
        raise FileNotFoundError(f"scenes.json not found: {scenes_json}")
    if not audio_dir.exists():
        raise FileNotFoundError(f"audio/ dir not found: {audio_dir}")

    data = json.loads(scenes_json.read_text(encoding="utf-8"))
    scenes = data.get("scenes", [])
    repaired = 0
    missing = 0

    for scene in scenes:
        sid = scene.get("id", "?")
        try:
            mp3 = audio_dir / f"scene{int(sid):02d}.mp3"
        except (ValueError, TypeError):
            mp3 = audio_dir / f"{sid}.mp3"

        if not mp3.exists():
            print(f"  [WARN] 오디오 없음: {mp3.name}", flush=True)
            missing += 1
            continue

        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(mp3),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0 or not result.stdout.strip():
            print(f"  [WARN] ffprobe 실패: {mp3.name} — {result.stderr.strip()}", flush=True)
            missing += 1
            continue

        try:
            dur_s = float(result.stdout.strip())
        except ValueError:
            print(f"  [WARN] ffprobe 비정상 출력: {mp3.name} — {result.stdout.strip()!r}", flush=True)
            missing += 1
            continue
        scene["audio_path"] = str(mp3)
        scene["audio_duration_ms"] = int(dur_s * 1000)
        repaired += 1

    scenes_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    total_dur_ms = sum(
        s.get("audio_duration_ms", 0) for s in scenes if s.get("audio_duration_ms")
    )
    return {
        "repaired": repaired,
        "missing": missing,
        "total": len(scenes),
        "total_duration_s": total_dur_ms / 1000,
    }


def _remove_done_files(run_dir: Path, dry_run: bool = False) -> list[str]:
    """재실행 대상 stage의 .done 파일 삭제 (protected 스테이지 절대 보존)."""
    removed = []
    for stage in _STAGES_TO_RERUN:
        if stage in _PROTECTED_STAGES:
            raise RuntimeError(f"BUG: {stage} is in both RERUN and PROTECTED — fix _STAGES_TO_RERUN")
        done_file = run_dir / f"stage_{stage}.done"
        if done_file.exists():
            if not dry_run:
                done_file.unlink()
            removed.append(f"stage_{stage}.done")
    return removed


def main() -> None:
    p = argparse.ArgumentParser(description="run audio metadata 복구 + render 재실행")
    p.add_argument("run_id", help="복구할 run_id")
    p.add_argument("--dry-run", action="store_true",
                   help="scenes.json 수정 없이 복구 대상만 확인")
    args = p.parse_args()

    run_dir = WORK_DIR / "runs" / args.run_id
    if not run_dir.exists():
        print(f"[ERROR] run_dir not found: {run_dir}", file=sys.stderr)
        sys.exit(1)

    # artifact_manifest.json에서 topic, language 추출
    manifest_path = run_dir / "artifact_manifest.json"
    if not manifest_path.exists():
        print(f"[ERROR] artifact_manifest.json not found", file=sys.stderr)
        sys.exit(1)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    topic = manifest.get("topic", args.run_id)
    language = manifest.get("language", "ko")

    print(f"[REPAIR] run_id   = {args.run_id}", flush=True)
    print(f"[REPAIR] topic    = {topic!r}", flush=True)
    print(f"[REPAIR] language = {language}", flush=True)
    print(f"[REPAIR] run_dir  = {run_dir}", flush=True)

    # 보호 확인 — stage_tts.done 반드시 존재해야 함
    if not (run_dir / "stage_tts.done").exists():
        print("[ERROR] stage_tts.done 없음 — TTS가 완료된 런이 아님", file=sys.stderr)
        sys.exit(1)

    # STEP 1: audio metadata 복구
    print("\n[STEP 1] audio metadata 복구 중...", flush=True)
    if args.dry_run:
        print("  (dry-run: scenes.json 수정 없음)", flush=True)
        data = json.loads((run_dir / "scenes.json").read_text(encoding="utf-8"))
        scenes = data.get("scenes", [])
        audio_dir = run_dir / "audio"
        def _mp3_path(sid: object) -> Path:
            try:
                return audio_dir / f"scene{int(sid):02d}.mp3"
            except (ValueError, TypeError):
                return audio_dir / f"{sid}.mp3"
        found = sum(1 for s in scenes if _mp3_path(s.get("id", -1)).exists())
        print(f"  scenes.json: {len(scenes)}씬 / audio/: {found}개 MP3 감지", flush=True)
    else:
        stats = repair_run_metadata(run_dir)
        print(
            f"  완료: {stats['repaired']}/{stats['total']}씬 복구 "
            f"(누락 {stats['missing']}씬, 총 {stats['total_duration_s']:.1f}s)",
            flush=True,
        )

    # STEP 2: downstream .done 파일 삭제
    print("\n[STEP 2] downstream stage .done 삭제 중...", flush=True)
    removed = _remove_done_files(run_dir, dry_run=args.dry_run)
    for f in removed:
        print(f"  {'(dry) ' if args.dry_run else ''}삭제: {f}", flush=True)
    print(f"  총 {len(removed)}개 삭제 {'예정' if args.dry_run else '완료'}", flush=True)

    if args.dry_run:
        print("\n[DRY-RUN] 실제 실행 없이 종료.", flush=True)
        return

    # STEP 3: 파이프라인 재실행
    try:
        data = json.loads((run_dir / "scenes.json").read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"[ERROR] scenes.json 복구 후 파싱 실패: {e}", file=sys.stderr)
        sys.exit(1)
    total_dur_s = sum(
        s.get("audio_duration_ms", 0) for s in data.get("scenes", [])
        if s.get("audio_duration_ms")
    ) / 1000
    target_dur = max(120, int(total_dur_s))

    print(f"\n[STEP 3] 파이프라인 재실행 (target_duration_sec={target_dur})", flush=True)
    print("  caption_from_narration → caption_validate → scene_render → final_concat → qa",
          flush=True)

    sys.path.insert(0, str(ROOT / "pipelines"))
    import run_pipeline  # type: ignore[import]

    run_pipeline.run(
        topic=topic,
        input_path=None,
        stop_after="final",
        dry_run=False,
        force=False,
        iteration="latest",
        target_duration_sec=target_dur,
        run_id=args.run_id,
        language=language,
    )


if __name__ == "__main__":
    main()
