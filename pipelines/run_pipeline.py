"""파이프라인 통합 러너 — S2(대본) → S8(QA) 전 단계.

stage 순서: script → polish → critique → regen → scenes
           → tts → whisper_align → caption_segment → caption_timing_align
           → caption_validate → motion_anchor
           → render → visual_correct → compose → qa → final
Audio Driven Scene 원칙: render 이전에 audio_duration, caption, motion_anchor 가 확보되어야 한다.
각 stage 완료 시 iter_dir/stage_{stage}.done 플래그를 기록하며, 재실행 시 해당 stage 를 스킵한다.
"""

from __future__ import annotations

import argparse
import datetime
import importlib
import json
import os
import re
import shutil
import signal
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FuturesTimeoutError
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

try:
    from rich.console import Console
    from rich.rule import Rule
    _console = Console(stderr=True)

    def _log(msg: str, level: str = "info") -> None:
        color = {"info": "cyan", "warning": "yellow", "error": "red",
                 "success": "green"}.get(level, "white")
        _console.print(f"[{color}][pipeline][/{color}] {msg}")

    def _rule(title: str) -> None:
        _console.print(Rule(f"[bold]{title}[/bold]"))
except ImportError:
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO)

    def _log(msg: str, level: str = "info") -> None:  # type: ignore[misc]
        getattr(_logging, level, _logging.info)(f"[pipeline] {msg}")

    def _rule(title: str) -> None:  # type: ignore[misc]
        print(f"\n{'─'*40} {title} {'─'*40}")


ROOT           = Path(os.environ.get("PROJECT_ROOT", Path(__file__).parent.parent))
_WORK_DIR_BASE = Path(os.getenv("WORK_DIR", str(ROOT / "work")))  # 기존 전역 work 루트 (runs/ 상위)
WORK_DIR       = _WORK_DIR_BASE  # 하위 호환 — run() 내에서 run_dir로 재정의됨
VIDEOS_DIR     = Path(os.getenv("VIDEOS_DIR", str(ROOT / "videos")))

_VALID_GENERATION_MODES = frozenset({"template", "ai_motion", "auto"})

_tls = threading.local()  # thread-local: _tls.run_id set per-run to avoid concurrent-run races

STOP_STAGES = [
    "script", "polish", "critique", "regen",
    "scenes", "scene_review", "scene_quality", "content_repair", "tts", "whisper_align", "caption_segment", "caption_timing_align", "caption_validate", "motion_anchor",
    "render", "visual_correct", "scene_render", "caption_overlay", "final_concat", "compose", "qa", "final",
]


# ── 버전 관리 헬퍼 ─────────────────────────────────────────────────────────────

def _iter_versions(iterations_dir: Path) -> list[int]:
    if not iterations_dir.exists():
        return []
    versions = []
    for d in iterations_dir.iterdir():
        m = re.match(r"^v(\d+)$", d.name)
        if m and d.is_dir():
            versions.append(int(m.group(1)))
    return sorted(versions)


def _resolve_iteration(iteration: str) -> tuple[Path, int]:
    """--iteration 플래그 → (출력 디렉토리, 버전 번호)."""
    iter_base = WORK_DIR / "iterations"
    versions = _iter_versions(iter_base)

    if iteration == "latest":
        latest = WORK_DIR / "latest"
        if latest.is_symlink():
            target = latest.resolve()
            m = re.match(r".*v(\d+)$", str(target))
            cur = int(m.group(1)) if m else (max(versions) if versions else 1)
            n = cur + 1
        else:
            n = max(versions) + 1 if versions else 2
        return iter_base / f"v{n}", n

    if iteration == "new":
        n = max(versions) + 1 if versions else 2
        return iter_base / f"v{n}", n

    m = re.match(r"^v(\d+)$", iteration)
    if m:
        n = int(m.group(1))
        return iter_base / f"v{n}", n

    raise ValueError(
        f"잘못된 --iteration 값: {iteration!r}. new|latest|v<n> 형식이어야 합니다."
    )


# ── Topic-Content Alignment Guardrail (LLM 기반 의미 검증) ──────────────────

def _llm_topic_guard(scenes_json: Path, topic: str) -> None:
    """LLM 기반 씬-주제 적합성 의미 검증.

    verdict=FAIL (콘텐츠 불일치) → DB에 FAIL 기록 후 RuntimeError 발생 (파이프라인 중단)
    verdict=WARN (저적합)        → DB에 WARN 기록 후 계속
    verdict=PASS                 → DB에 PASS 기록 후 계속
    LLM/API 호출 실패            → DB에 WARN 기록 후 계속 (하드 실패 방지)
    """
    if not scenes_json.exists():
        return
    _t0 = time.monotonic()
    import json as _json
    import re as _re
    try:
        _data = _json.loads(scenes_json.read_text(encoding="utf-8"))
        _scenes = _data if isinstance(_data, list) else _data.get("scenes", [])
        if not _scenes:
            return

        _scenes_summary = _json.dumps(
            [
                {
                    "title": s.get("title", ""),
                    "narration": (s.get("narration") or "")[:200],
                }
                for s in _scenes[:20]
            ],
            ensure_ascii=False,
        )

        _prompt = (
            "You are a topic validation system for AI video content generation.\n\n"
            f"Topic: {topic}\n\n"
            f"Scene summaries (title + narration excerpt, up to 20 scenes):\n{_scenes_summary}\n\n"
            "Determine whether the scenes are semantically relevant to the topic.\n"
            "Important: English terms may appear as Korean loanwords:\n"
            '  "agent" → "에이전트", "AI" → "인공지능", "cloud" → "클라우드"\n'
            "Partial topic coverage is acceptable. Technical synonyms and related concepts count as a match.\n\n"
            "Respond with JSON only (no other text):\n"
            '{"verdict": "PASS"|"WARN"|"FAIL", "match_rate": 0.0-1.0, "reason": "brief explanation"}\n\n'
            "Use FAIL only when content is completely unrelated to the topic (<5% relevance).\n"
            "Use WARN when content is low-relevance (<20%) but not completely unrelated.\n"
            "Use PASS otherwise."
        )

        try:
            from llm_client import generate as _llm_generate
            _raw = _llm_generate(_prompt, role="topic_guard")
        except Exception as _llm_exc:
            _elapsed = time.monotonic() - _t0
            _msg = f"LLM 호출 실패, WARN 후 계속: {type(_llm_exc).__name__}"
            _log(f"[TOPIC_GUARD] {_msg}", "warning")
            _db_record_stage("topic_guard", "WARN", _elapsed, _msg)
            return

        try:
            _result = _json.loads(_raw)
            if not isinstance(_result, dict):
                raise ValueError("expected JSON object")
        except (_json.JSONDecodeError, ValueError):
            _m = _re.search(r"\{[^{}]*\}", _raw, _re.DOTALL)
            if not _m:
                _elapsed = time.monotonic() - _t0
                _msg = "응답에서 JSON 파싱 실패, WARN 후 계속"
                _log(f"[TOPIC_GUARD] {_msg}", "warning")
                _db_record_stage("topic_guard", "WARN", _elapsed, _msg)
                return
            try:
                _result = _json.loads(_m.group())
            except _json.JSONDecodeError:
                _elapsed = time.monotonic() - _t0
                _msg = "응답에서 JSON 파싱 실패, WARN 후 계속"
                _log(f"[TOPIC_GUARD] {_msg}", "warning")
                _db_record_stage("topic_guard", "WARN", _elapsed, _msg)
                return

        _allowed_verdicts = {"PASS", "WARN", "FAIL"}
        _verdict = (_result.get("verdict") or "WARN").upper()
        if _verdict not in _allowed_verdicts:
            _verdict = "WARN"
        _match_rate = float(_result.get("match_rate", 0.5))
        _reason = str(_result.get("reason", ""))
        _elapsed = time.monotonic() - _t0

        _log(
            f"[TOPIC_GUARD] verdict={_verdict} match_rate={_match_rate:.0%} reason={_reason!r}"
        )
        print(
            f"[TOPIC_GUARD] verdict={_verdict} match_rate={_match_rate:.0%} reason={_reason!r}",
            flush=True,
        )

        if _verdict == "FAIL":
            _err = f"match_rate={_match_rate:.0%} — {_reason}"
            _db_record_stage("topic_guard", "FAIL", _elapsed, _err)
            raise RuntimeError(f"[TOPIC_GUARD] ABORT: topic='{topic}' {_err}")
        elif _verdict == "WARN":
            _db_record_stage("topic_guard", "WARN", _elapsed, f"match_rate={_match_rate:.0%}: {_reason}")
            _log(
                f"[TOPIC_GUARD] WARN match_rate={_match_rate:.0%} — {_reason}. 파이프라인 계속.",
                "warning",
            )
        else:
            _db_record_stage("topic_guard", "PASS", _elapsed)

    except RuntimeError:
        raise
    except Exception as _exc:
        _elapsed = time.monotonic() - _t0
        _msg = f"예외 발생, WARN 후 계속: {type(_exc).__name__}"
        _log(f"[TOPIC_GUARD] {_msg}", "warning")
        _db_record_stage("topic_guard", "WARN", _elapsed, _msg)


# ── .done 플래그 ──────────────────────────────────────────────────────────────

def _is_done(iter_dir: Path, stage_key: str) -> bool:
    return (iter_dir / f"stage_{stage_key}.done").exists()


def _mark_done(iter_dir: Path, stage_key: str) -> None:
    iter_dir.mkdir(parents=True, exist_ok=True)
    (iter_dir / f"stage_{stage_key}.done").touch()
    _log(f"플래그 기록: stage_{stage_key}.done")


# ── 단계 실행 헬퍼 ─────────────────────────────────────────────────────────────

def _db_record_stage(stage_key: str, status: str, elapsed: float, error: str = "") -> None:
    run_id = getattr(_tls, "run_id", None)
    if run_id is None:
        return
    try:
        sys.path.insert(0, str(ROOT))
        from db import ops as _db_ops
        _db_ops.record_stage(run_id, stage_key, status, elapsed, error)
    except Exception:
        pass


def _db_record_artifact(artifact_type: str, file_path: str) -> None:
    run_id = getattr(_tls, "run_id", None)
    if run_id is None:
        return
    try:
        sys.path.insert(0, str(ROOT))
        from db import ops as _db_ops
        _db_ops.record_artifact(run_id, artifact_type, file_path)
    except Exception:
        pass


def _publish_htube_output(run_id: str, topic: str, run_dir: Path, final_mp4_path: str) -> None:
    try:
        pipelines_dir = str(Path(__file__).parent)
        if pipelines_dir not in sys.path:
            sys.path.insert(0, pipelines_dir)
        from htube_publish import publish_from_env  # type: ignore[import]

        result = publish_from_env(
            run_id=run_id,
            topic=topic,
            run_dir=run_dir,
            final_mp4_path=final_mp4_path,
        )
        if result is not None:
            _log(f"[HTUBE_PUBLISH] published final MP4 to {result.destination_dir}", "success")
    except Exception as exc:
        _log(f"[HTUBE_PUBLISH] publish failed (ignored): {exc}", "warning")


def _module_exists(name: str) -> bool:
    return (Path(__file__).parent / f"{name}.py").exists()


def is_scene_plan_compatible(plan_scene_count: int, target_scene_count: int) -> bool:
    """True if scene_plan can guide generation for target_scene_count.
    Rule: plan must cover at least half the target to be useful.
    """
    compatible = plan_scene_count >= target_scene_count // 2
    print(
        f"[SCENE_PLAN_COMPAT]"
        f" plan_scene_count={plan_scene_count}"
        f" target_scene_count={target_scene_count}"
        f" compatible={str(compatible).lower()}"
        f" decision={'use_scene_plan' if compatible else 'skip_scene_plan'}"
        f" reason={'plan_sufficient_for_target_duration' if compatible else 'plan_too_small_for_target_duration'}",
        flush=True,
    )
    return compatible


def _run_stage(
    stage_name: str,
    module_name: str,
    func_name: str,
    kwargs: dict,
    dry_run: bool,
    iter_dir: Path,
    stage_key: str,
    force: bool,
    stage_timeout_sec: int | None = None,
) -> None:
    """단일 단계 실행 — .done 스킵, 경과시간 측정, 실패 시 exit(1)."""
    _rule(f"[{stage_name}] 시작")

    if not force and _is_done(iter_dir, stage_key):
        _log(f"stage_{stage_key}.done 존재 → 스킵", "warning")
        print(f"[PROFILE] stage={stage_key} duration_sec=0.0 status=SKIP", flush=True)
        _db_record_stage(stage_key, "SKIP", 0.0)
        return

    if dry_run:
        _log(f"dry-run: {module_name}.{func_name}({kwargs})", "info")
        _mark_done(iter_dir, stage_key)
        print(f"[PROFILE] stage={stage_key} duration_sec=0.0 status=DRYRUN", flush=True)
        return

    pipelines_dir = str(Path(__file__).parent)
    if pipelines_dir not in sys.path:
        sys.path.insert(0, pipelines_dir)

    print(f"[STAGE_START] stage={stage_key} timeout_sec={stage_timeout_sec or 'none'}", flush=True)
    t0 = time.monotonic()
    _stage_timed_out = False
    try:
        mod = importlib.import_module(module_name)
        fn = getattr(mod, func_name)
        if stage_timeout_sec is not None:
            with ThreadPoolExecutor(max_workers=1) as _exe:
                future = _exe.submit(fn, **kwargs)
                try:
                    future.result(timeout=stage_timeout_sec)
                except _FuturesTimeoutError:
                    _stage_timed_out = True
        else:
            fn(**kwargs)
    except SystemExit as exc:
        elapsed = time.monotonic() - t0
        _log(f"[{stage_name}] 실패 (exit {exc.code}) — {elapsed:.1f}s", "error")
        print(f"[PROFILE] stage={stage_key} duration_sec={elapsed:.1f} status=FAIL", flush=True)
        _db_record_stage(stage_key, "FAIL", elapsed, str(exc.code))
        sys.exit(int(exc.code) if exc.code is not None else 1)
    except Exception as exc:
        elapsed = time.monotonic() - t0
        _log(f"[{stage_name}] 예외 ({elapsed:.1f}s): {exc}", "error")
        print(f"[PROFILE] stage={stage_key} duration_sec={elapsed:.1f} status=FAIL", flush=True)
        _db_record_stage(stage_key, "FAIL", elapsed, str(exc))
        sys.exit(1)

    if _stage_timed_out:
        elapsed = time.monotonic() - t0
        print(
            f"[STAGE_TIMEOUT] stage={stage_key} limit_sec={stage_timeout_sec}"
            f" elapsed_sec={elapsed:.0f} status=FAIL",
            flush=True,
        )
        print(f"[PROFILE] stage={stage_key} duration_sec={elapsed:.1f} status=FAIL", flush=True)
        _db_record_stage(stage_key, "FAIL", elapsed, "timeout")
        sys.exit(2)

    elapsed = time.monotonic() - t0
    _log(f"[{stage_name}] 완료 — {elapsed:.1f}s", "success")
    print(f"[STAGE_DONE] stage={stage_key} elapsed_sec={elapsed:.1f} status=PASS", flush=True)
    print(f"[PROFILE] stage={stage_key} duration_sec={elapsed:.1f} status=PASS", flush=True)
    _db_record_stage(stage_key, "PASS", elapsed)
    _mark_done(iter_dir, stage_key)


# ── 렌더 진입 전 무결성 검증 (PART D) ────────────────────────────────────────

def _pre_render_integrity_check(scenes_json: Path) -> None:
    """Render 진입 전 scenes.json 무결성 검증 — audio/caption 누락 시 FAIL FAST."""
    if not scenes_json.exists():
        _log("[PRE_RENDER_GUARD] scenes.json 없음 → FAIL", "error")
        print("[PRE_RENDER_GUARD] status=FAIL reason=scenes_json_missing", flush=True)
        sys.exit(1)

    import json as _json
    data = _json.loads(scenes_json.read_text(encoding="utf-8"))
    scenes = data.get("scenes", [])
    if not scenes:
        _log("[PRE_RENDER_GUARD] scenes 비어있음 → FAIL", "error")
        print("[PRE_RENDER_GUARD] status=FAIL reason=empty_scenes", flush=True)
        sys.exit(1)

    errors: list[str] = []
    for scene in scenes:
        sid = scene.get("id", "?")
        audio_path = scene.get("audio_path")
        if not audio_path:
            errors.append(f"scene {sid}: audio_path=None")
        elif not Path(audio_path).exists():
            errors.append(f"scene {sid}: audio_path not found")

        audio_dur = scene.get("audio_duration_ms")
        if audio_dur is None or audio_dur <= 0:
            errors.append(f"scene {sid}: audio_duration_ms={audio_dur}")

    scenes_with_captions = sum(1 for s in scenes if s.get("caption_segments"))
    caption_coverage = scenes_with_captions / len(scenes)
    if caption_coverage < 0.1:
        errors.append(
            f"caption_coverage={caption_coverage:.0%} ({scenes_with_captions}/{len(scenes)}) < 10%"
        )

    if errors:
        for e in errors:
            _log(f"[PRE_RENDER_GUARD] {e}", "error")
        _log(f"[PRE_RENDER_GUARD] FAIL — {len(errors)}개 무결성 오류 → 렌더 중단", "error")
        print(f"[PRE_RENDER_GUARD] status=FAIL errors={len(errors)}", flush=True)
        sys.exit(1)

    _log(f"[PRE_RENDER_GUARD] PASS — {len(scenes)}씬 audio/caption 무결성 확인", "success")
    print(f"[PRE_RENDER_GUARD] status=PASS scenes={len(scenes)}", flush=True)


# ── 인라인 render 단계 ────────────────────────────────────────────────────────

def _run_render(
    scenes_json: Path,
    slides_dir: Path,
    iter_dir: Path,
    dry_run: bool,
    force: bool,
    cancel_event: "threading.Event | None" = None,
) -> None:
    """S6 render — scenes.json 으로 씬별 PNG 슬라이드를 생성한다. (audio/caption/motion 확보 후)"""
    _rule("[S6 render] 시작")

    if not force and _is_done(iter_dir, "render"):
        _log("stage_render.done 존재 → 스킵", "warning")
        _db_record_stage("render", "SKIP", 0.0)
        return

    if not scenes_json.exists():
        _log(f"scenes.json 없음: {scenes_json}", "error")
        sys.exit(1)

    if dry_run:
        _log(f"dry-run: render PNGs from {scenes_json}")
        _mark_done(iter_dir, "render")
        return

    pipelines_dir = str(Path(__file__).parent)
    if pipelines_dir not in sys.path:
        sys.path.insert(0, pipelines_dir)

    from render_animated_slide import render_bullet_frame  # type: ignore[import]

    slides_dir.mkdir(parents=True, exist_ok=True)
    data = json.loads(scenes_json.read_text(encoding="utf-8"))
    scenes = data.get("scenes", [])

    t0 = time.monotonic()
    _render_timed_out = False

    def _do_render() -> None:
        for scene in scenes:
            if cancel_event and cancel_event.is_set():
                _log("cancel_event 감지 — render PNG 루프 중단", "warning")
                break
            sid = scene.get("id", 0)
            bullets = scene.get("bullets", [])
            normalized = [
                b if isinstance(b, dict)
                else {"text": b, "emphasis": [], "appear_at_ms": i * 3000}
                for i, b in enumerate(bullets)
            ]
            out_path = slides_dir / f"scene{sid:02d}.png"
            render_bullet_frame(normalized, visible_until_idx=len(normalized) - 1, out_path=out_path)
            _log(f"씬 {sid} PNG 완료: {out_path.name}")

    with ThreadPoolExecutor(max_workers=1) as _exe:
        future = _exe.submit(_do_render)
        try:
            future.result(timeout=_RENDER_TIMEOUT_SEC)
        except _FuturesTimeoutError:
            _render_timed_out = True

    elapsed = time.monotonic() - t0
    if _render_timed_out:
        print(
            f"[STAGE_TIMEOUT] stage=render limit_sec={_RENDER_TIMEOUT_SEC}"
            f" elapsed_sec={elapsed:.0f} status=FAIL",
            flush=True,
        )
        print(f"[PROFILE] stage=render duration_sec={elapsed:.1f} status=FAIL", flush=True)
        _db_record_stage("render", "FAIL", elapsed, "STAGE_TIMEOUT")
        sys.exit(2)

    _log(f"render 완료 — {len(scenes)}개 씬 ({elapsed:.1f}s)", "success")
    _db_record_stage("render", "DONE", elapsed)
    _mark_done(iter_dir, "render")


# ── 인라인 tts 단계 (synth_narration) ─────────────────────────────────────────

def _run_tts_synth(
    scenes_json: Path,
    audio_dir: Path,
    narration_dir: Path,
    iter_dir: Path,
    dry_run: bool,
    force: bool,
    topic: str = "",
    language: str = "ko",
    tts_timeout_sec: int | None = None,
    tts_provider: str = "azure",
    tts_voice: str | None = None,
    cancel_event: "threading.Event | None" = None,
) -> bool | None:
    """S5 tts — 씬별 MP3 를 생성하고 appear_at_ms 를 갱신한다 (엔진 자동 선택). render 이전 실행."""
    _rule("[S5 tts/synth_narration] 시작")

    if not force and _is_done(iter_dir, "tts"):
        _log("stage_tts.done 존재 → 스킵", "warning")
        _db_record_stage("tts", "SKIP", 0.0)
        return

    if not scenes_json.exists():
        _log(f"scenes.json 없음: {scenes_json}", "error")
        sys.exit(1)

    if dry_run:
        _log(f"dry-run: synth_narration from {scenes_json}")
        _mark_done(iter_dir, "tts")
        return

    pipelines_dir = str(Path(__file__).parent)
    if pipelines_dir not in sys.path:
        sys.path.insert(0, pipelines_dir)

    from synth_narration import get_cache_usage, reset_cache_usage, synth_scene_to_mp3  # type: ignore[import]

    audio_dir.mkdir(parents=True, exist_ok=True)
    narration_dir.mkdir(parents=True, exist_ok=True)

    from video_defaults import get_tts_speed  # type: ignore[import]

    _tts_rate = get_tts_speed()
    _log(f"TTS rate: {_tts_rate} (config/video_defaults.yaml)")

    data = json.loads(scenes_json.read_text(encoding="utf-8"))
    scenes = data.get("scenes", [])

    _effective_tts_timeout = tts_timeout_sec if tts_timeout_sec is not None else _TTS_STAGE_TIMEOUT_SEC
    print(f"[STAGE_START] stage=tts timeout_sec={_effective_tts_timeout}", flush=True)
    t0 = time.monotonic()
    _tts_timed_out = False

    _tts_cache_used = False

    def _do_tts() -> None:
        nonlocal _tts_cache_used
        reset_cache_usage()
        for scene in scenes:
            if cancel_event and cancel_event.is_set():
                _log("cancel_event 감지 — TTS 씬 루프 중단", "warning")
                break
            mp3_path = synth_scene_to_mp3(scene, narration_dir, audio_dir, rate=_tts_rate, topic=topic, language=language, tts_provider=tts_provider, tts_voice=tts_voice)
            if mp3_path and mp3_path.exists():
                scene["audio_path"] = str(mp3_path)
        _tts_cache_used = get_cache_usage()

    with ThreadPoolExecutor(max_workers=1) as _exe:
        future = _exe.submit(_do_tts)
        try:
            future.result(timeout=_effective_tts_timeout)
        except _FuturesTimeoutError:
            _tts_timed_out = True
        except Exception as exc:
            _elapsed = time.monotonic() - t0
            _db_record_stage("tts", "FAIL", _elapsed, str(exc))
            _log(f"TTS 예외 발생: {exc}", "error")
            print(f"[STAGE_FAIL] stage=tts elapsed_sec={_elapsed:.1f} error={exc}", flush=True)
            sys.exit(1)

    if _tts_timed_out:
        elapsed = time.monotonic() - t0
        # Artifact-based completion check: thread ran to end via shutdown(wait=True)
        # so files may already be fully generated despite the timeout flag.
        _completed_mp3s = sorted(p for p in audio_dir.glob("scene*.mp3") if p.stat().st_size > 0)
        _expected_count = len(scenes)
        if _expected_count > 0 and len(_completed_mp3s) >= _expected_count:
            _log(
                f"TTS timeout 감지됐으나 audio 파일 완전({len(_completed_mp3s)}/{_expected_count}) "
                f"— 완료 처리 (elapsed={elapsed:.0f}s)",
                "warning",
            )
            print(
                f"[STAGE_DONE] stage=tts elapsed_sec={elapsed:.1f} status=PASS"
                f" artifact_complete=True files={len(_completed_mp3s)}",
                flush=True,
            )
            _db_record_stage("tts", "DONE", elapsed)
            _mark_done(iter_dir, "tts")
            # FIX: persist audio_path values that _do_tts() wrote into scene dicts
            # (thread completed via shutdown(wait=True) before we get here)
            scenes_json.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return
        print(
            f"[STAGE_TIMEOUT] stage=tts limit_sec={_effective_tts_timeout}"
            f" elapsed_sec={elapsed:.0f} files={len(_completed_mp3s)}/{_expected_count} status=FAIL",
            flush=True,
        )
        print(f"[PROFILE] stage=tts duration_sec={elapsed:.1f} status=FAIL", flush=True)
        _db_record_stage("tts", "FAIL", elapsed, f"STAGE_TIMEOUT files={len(_completed_mp3s)}/{_expected_count}")
        sys.exit(2)

    if cancel_event and cancel_event.is_set():
        elapsed = time.monotonic() - t0
        _log("TTS 단계 cancel_event 감지 — 조기 종료", "warning")
        _db_record_stage("tts", "CANCELLED", elapsed, "CANCELLED")
        return

    # appear_at_ms 갱신 + audio_path 저장된 scenes.json 을 다시 저장
    scenes_json.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _tts_elapsed = time.monotonic() - t0
    _log(f"tts 완료 — {len(scenes)}개 씬 ({_tts_elapsed:.1f}s)", "success")
    print(f"[STAGE_DONE] stage=tts elapsed_sec={_tts_elapsed:.1f} status=PASS", flush=True)
    _db_record_stage("tts", "DONE", _tts_elapsed)
    for _mp3 in sorted(narration_dir.glob("*.mp3")):
        _db_record_artifact("narration_mp3", str(_mp3))
    _mark_done(iter_dir, "tts")
    return _tts_cache_used


# ── 인라인 whisper_align 단계 ─────────────────────────────────────────────────
# DEPRECATED: 2026-05-30 — 표준 run_pipeline.py 경로에서 미호출. REMOVAL_CANDIDATE: 2026-06-30

def _run_whisper_align(
    scenes_json: Path,
    audio_dir: Path,
    iter_dir: Path,
    dry_run: bool,
    force: bool,
) -> None:
    """S5.1 whisper_align (audio_measure) — 씬별 MP3 에서 단어 타임스탬프를 추출하여 scenes.json 에 저장한다."""
    _rule("[S5.1 whisper_align] 시작")

    if not force and _is_done(iter_dir, "whisper_align"):
        _log("stage_whisper_align.done 존재 → 스킵", "warning")
        return

    if not scenes_json.exists():
        _log(f"scenes.json 없음: {scenes_json}", "error")
        sys.exit(1)

    if dry_run:
        _log(f"dry-run: whisper_align on {audio_dir}")
        _mark_done(iter_dir, "whisper_align")
        return

    pipelines_dir = str(Path(__file__).parent)
    if pipelines_dir not in sys.path:
        sys.path.insert(0, pipelines_dir)

    from whisper_align import align  # type: ignore[import]

    data = json.loads(scenes_json.read_text(encoding="utf-8"))
    scenes = data.get("scenes", [])

    t0 = time.monotonic()
    updated = 0
    for scene in scenes:
        sid = scene.get("id", 0)
        mp3_path = audio_dir / f"scene{sid:02d}.mp3"
        if not mp3_path.exists():
            _log(f"씬 {sid}: MP3 없음 ({mp3_path.name}) → 스킵", "warning")
            continue

        narration = scene.get("narration", "")
        try:
            word_ts = align(mp3_path, expected_text=narration)
            scene["word_timestamps"] = word_ts
            updated += 1
            _log(f"씬 {sid}: {len(word_ts)}개 단어 타임스탬프 추출")
        except Exception as exc:
            _log(f"씬 {sid}: whisper_align 실패 — {exc}", "warning")
            scene.setdefault("word_timestamps", None)

    scenes_json.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _log(f"whisper_align 완료 — {updated}/{len(scenes)}개 씬 ({time.monotonic() - t0:.1f}s)", "success")
    _mark_done(iter_dir, "whisper_align")


# ── 인라인 caption_segment 단계 ──────────────────────────────────────────────
# DEPRECATED: 2026-05-30 — 표준 run_pipeline.py 경로에서 미호출. REMOVAL_CANDIDATE: 2026-06-30

def _run_caption_segment(
    scenes_json: Path,
    iter_dir: Path,
    dry_run: bool,
    force: bool,
) -> None:
    """S5.2 caption_segment — word_timestamps → phrase 단위 caption_segments 생성 + QA."""
    _rule("[S5.2 caption_segment] 시작")

    if not force and _is_done(iter_dir, "caption_segment"):
        _log("stage_caption_segment.done 존재 → 스킵", "warning")
        return

    if not scenes_json.exists():
        _log(f"scenes.json 없음: {scenes_json}", "error")
        sys.exit(1)

    if dry_run:
        _log(f"dry-run: caption_segment on {scenes_json}")
        _mark_done(iter_dir, "caption_segment")
        return

    pipelines_dir = str(Path(__file__).parent)
    if pipelines_dir not in sys.path:
        sys.path.insert(0, pipelines_dir)

    from caption_segmenter import segment  # type: ignore[import]

    data = json.loads(scenes_json.read_text(encoding="utf-8"))
    scenes = data.get("scenes", [])

    t0 = time.monotonic()
    all_captions: list[dict] = []
    qa_errors: list[str] = []
    updated = 0

    for scene in scenes:
        sid = scene.get("id", 0)
        word_ts = scene.get("word_timestamps")
        narration = scene.get("narration", "")

        if not word_ts:
            _log(f"씬 {sid}: word_timestamps 없음 → caption_segment 스킵", "warning")
            scene.setdefault("caption_segments", None)
            continue

        try:
            segs = segment(word_ts)
        except Exception as exc:
            _log(f"씬 {sid}: caption_segmenter 실패 — {exc}", "error")
            scene["caption_segments"] = None
            continue

        # ── Caption QA (인라인) ────────────────────────────────────────────
        scene_errors: list[str] = []

        # 빈 캡션 검사
        empty = [i for i, s in enumerate(segs) if not s.get("text", "").strip()]
        if empty:
            scene_errors.append(f"빈 caption {len(empty)}개 (idx: {empty})")

        # 시간 오류 검사
        for i, s in enumerate(segs):
            if s["start_ms"] >= s["end_ms"]:
                scene_errors.append(f"캡션 {i}: start_ms >= end_ms ({s['start_ms']} >= {s['end_ms']})")
            if i > 0 and s["start_ms"] < segs[i - 1]["end_ms"]:
                scene_errors.append(f"캡션 {i}: 이전 캡션과 시간 겹침")

        # 문자 누락률 검사 (>20% 이면 경고)
        total_caption_chars = sum(len(s["text"].replace(" ", "")) for s in segs)
        narration_chars = len(narration.replace(" ", ""))
        if narration_chars > 0:
            drop_rate = 1.0 - total_caption_chars / narration_chars
            if drop_rate > 0.20:
                scene_errors.append(
                    f"문자 누락률 {drop_rate:.0%} (캡션 {total_caption_chars}자 / 나레이션 {narration_chars}자)"
                )

        if scene_errors:
            for err in scene_errors:
                _log(f"씬 {sid} Caption QA 실패: {err}", "warning")
                qa_errors.append(f"[씬 {sid}] {err}")
            # FAIL 시 caption_segments 는 그대로 저장 (렌더는 허용, 경고만)

        scene["caption_segments"] = segs
        updated += 1

        all_captions.append({"scene_id": sid, "caption_segments": segs})
        _log(f"씬 {sid}: {len(segs)}개 phrase caption 생성")

    # scenes.json 갱신
    scenes_json.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # captions.json 별도 저장
    captions_json = iter_dir / "captions.json"
    captions_json.write_text(
        json.dumps(all_captions, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    elapsed = time.monotonic() - t0
    if qa_errors:
        _log(f"caption_segment 완료 (QA 경고 {len(qa_errors)}건) — {updated}/{len(scenes)}씬 ({elapsed:.1f}s)", "warning")
    else:
        _log(f"caption_segment 완료 — {updated}/{len(scenes)}씬 ({elapsed:.1f}s)", "success")

    _mark_done(iter_dir, "caption_segment")


# ── 인라인 caption_from_narration 단계 ───────────────────────────────────────

def _run_caption_from_narration(
    scenes_json: Path,
    iter_dir: Path,
    dry_run: bool,
    force: bool,
) -> None:
    """S5.2 caption_from_narration — narration 텍스트 직접 기반 caption_segments 생성 (Whisper 불필요)."""
    _rule("[S5.2 caption_from_narration] 시작")

    stage_key = "caption_from_narration"
    if not force and _is_done(iter_dir, stage_key):
        _log(f"stage_{stage_key}.done 존재 → 스킵", "warning")
        _db_record_stage(stage_key, "SKIP", 0.0)
        return

    if not scenes_json.exists():
        _log(f"scenes.json 없음: {scenes_json}", "error")
        sys.exit(1)

    if dry_run:
        _log(f"dry-run: caption_from_narration on {scenes_json}")
        _mark_done(iter_dir, stage_key)
        return

    pipelines_dir = str(Path(__file__).parent)
    if pipelines_dir not in sys.path:
        sys.path.insert(0, pipelines_dir)

    from caption_from_narration import run_on_scenes  # type: ignore[import]

    t0 = time.monotonic()
    run_on_scenes(scenes_json)
    _cfn_elapsed = time.monotonic() - t0
    _log(f"caption_from_narration 완료 — {_cfn_elapsed:.1f}s", "success")
    _db_record_stage(stage_key, "DONE", _cfn_elapsed)
    _mark_done(iter_dir, stage_key)


# ── 인라인 caption_timing_align 단계 ──────────────────────────────────────────

def _run_caption_timing_align(
    scenes_json: Path,
    audio_dir: Path,
    iter_dir: Path,
    dry_run: bool,
    force: bool,
) -> None:
    """S5.2a caption_timing_align — Whisper timing signal로 start/end만 보정한다."""
    stage_key = "caption_timing_align"
    _rule("[S5.2a caption_timing_align] 시작")

    if not force and _is_done(iter_dir, stage_key):
        _log(f"stage_{stage_key}.done 존재 → 스킵", "warning")
        _db_record_stage(stage_key, "SKIP", 0.0)
        return

    if not scenes_json.exists():
        _log(f"scenes.json 없음: {scenes_json}", "error")
        _db_record_stage(stage_key, "FAIL", 0.0, "scenes.json 없음")
        sys.exit(1)

    report_path = iter_dir / "caption_timing_alignment.json"
    if dry_run:
        _log(f"dry-run: caption_timing_align on {scenes_json}")
        _mark_done(iter_dir, stage_key)
        return

    pipelines_dir = str(Path(__file__).parent)
    if pipelines_dir not in sys.path:
        sys.path.insert(0, pipelines_dir)

    from caption_timing_align import run_on_scenes  # type: ignore[import]

    t0 = time.monotonic()
    result = run_on_scenes(scenes_json=scenes_json, audio_dir=audio_dir, report_path=report_path)
    elapsed = time.monotonic() - t0

    synced = result.get("synced", 0)
    fallback = result.get("fallback", 0)
    skipped = result.get("skipped", 0)
    total = result.get("total", 0)
    if synced:
        _log(
            f"caption_timing_align DONE — synced={synced}/{total}, fallback={fallback}, skipped={skipped}, report={report_path}",
            "success",
        )
        _db_record_stage(stage_key, "DONE", elapsed)
    else:
        _log(
            f"caption_timing_align FALLBACK/SKIP — synced=0/{total}, fallback={fallback}, skipped={skipped}, report={report_path}",
            "warning",
        )
        _db_record_stage(stage_key, "WARN", elapsed, f"synced=0 fallback={fallback} skipped={skipped}")

    _mark_done(iter_dir, stage_key)


# ── 인라인 caption_validate 단계 ──────────────────────────────────────────────

def _run_caption_validate(
    scenes_json: Path,
    iter_dir: Path,
    dry_run: bool,
    force: bool,
) -> None:
    """S5.3 caption_validate — coverage·gap 검증 후 자동 재생성 루프 (최대 3회)."""
    _rule("[S5.3 caption_validate] 시작")

    if not force and _is_done(iter_dir, "caption_validate"):
        _log("stage_caption_validate.done 존재 → 스킵", "warning")
        _db_record_stage("caption_validate", "SKIP", 0.0)
        return

    if not scenes_json.exists():
        _log(f"scenes.json 없음: {scenes_json}", "error")
        sys.exit(1)

    if dry_run:
        _log(f"dry-run: caption_validate on {scenes_json}")
        _mark_done(iter_dir, "caption_validate")
        return

    pipelines_dir = str(Path(__file__).parent)
    if pipelines_dir not in sys.path:
        sys.path.insert(0, pipelines_dir)

    from caption_validator import (  # type: ignore[import]
        validate_and_retry, report_to_dict,
        COVERAGE_THRESHOLD, MAX_GAP_MS,
    )

    t0 = time.monotonic()
    report = validate_and_retry(scenes_json=scenes_json, iter_dir=iter_dir)

    result = report_to_dict(report)
    out_path = iter_dir / "caption_validation.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    elapsed = time.monotonic() - t0
    cov_pct = result["coverage_pct"]
    gap_s = result["max_gap_s"]

    if report.status == "PASS":
        _log(
            f"caption_validate PASS — coverage={cov_pct:.1f}%, max_gap={gap_s:.3f}s, "
            f"retry={report.retry_count}, ({elapsed:.1f}s)",
            "success",
        )
    else:
        _log(
            f"caption_validate FAIL — coverage={cov_pct:.1f}% (need ≥{COVERAGE_THRESHOLD*100:.0f}%), "
            f"max_gap={gap_s:.3f}s (need ≤{MAX_GAP_MS/1000:.1f}s), retry={report.retry_count}",
            "error",
        )
        for err in result["errors"][:5]:
            _log(f"  {err}", "error")
        # FAIL이어도 파이프라인 중단하지 않음 — 경고 후 계속 진행

    _db_record_stage("caption_validate", "DONE", elapsed)
    _mark_done(iter_dir, "caption_validate")


# ── 인라인 motion_anchor_gen 단계 ─────────────────────────────────────────────

def _run_motion_anchor_gen(
    scenes_json: Path,
    iter_dir: Path,
    dry_run: bool,
    force: bool,
) -> None:
    """S5.4 motion_anchor — word_timestamps → motion_anchors 생성 후 scenes.json 저장. render 이전 실행."""
    _rule("[S5.4 motion_anchor_gen] 시작")

    if not force and _is_done(iter_dir, "motion_anchor"):
        _log("stage_motion_anchor.done 존재 → 스킵", "warning")
        _db_record_stage("motion_anchor", "SKIP", 0.0)
        return

    if not scenes_json.exists():
        _log(f"scenes.json 없음: {scenes_json}", "error")
        sys.exit(1)

    if dry_run:
        _log(f"dry-run: motion_anchor_gen on {scenes_json}")
        _mark_done(iter_dir, "motion_anchor")
        return

    pipelines_dir = str(Path(__file__).parent)
    if pipelines_dir not in sys.path:
        sys.path.insert(0, pipelines_dir)

    from motion_anchor_gen import generate_anchors  # type: ignore[import]

    data = json.loads(scenes_json.read_text(encoding="utf-8"))
    scenes = data.get("scenes", [])

    t0 = time.monotonic()
    updated = 0
    for scene in scenes:
        sid = scene.get("id", 0)
        word_ts = scene.get("word_timestamps")
        if not word_ts:
            _log(f"씬 {sid}: word_timestamps 없음 → uniform fallback 사용", "warning")
            word_ts = []

        try:
            anchors = generate_anchors(scene, word_ts)
            scene["motion_anchors"] = anchors
            updated += 1
            _log(f"씬 {sid}: {len(anchors)}개 motion_anchor 생성")
        except Exception as exc:
            _log(f"씬 {sid}: motion_anchor_gen 실패 — {exc}", "warning")
            scene.setdefault("motion_anchors", None)

    scenes_json.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _ma_elapsed = time.monotonic() - t0
    _log(f"motion_anchor_gen 완료 — {updated}/{len(scenes)}개 씬 ({_ma_elapsed:.1f}s)", "success")
    _db_record_stage("motion_anchor", "DONE", _ma_elapsed)
    _mark_done(iter_dir, "motion_anchor")


# ── 인라인 compose 단계 ───────────────────────────────────────────────────────
# DEPRECATED: 2026-05-30 — 표준 run_pipeline.py 경로에서 미호출. REMOVAL_CANDIDATE: 2026-06-30

def _run_compose(
    topic: str,
    scenes_json: Path,
    slides_dir: Path,
    audio_dir: Path,
    iter_dir: Path,
    dry_run: bool,
    force: bool,
) -> Path:
    """S7 compose — slides + audio → final.mp4."""
    _rule("[S7 compose] 시작")

    video_path = iter_dir / "video.mp4"

    if not force and _is_done(iter_dir, "compose"):
        _log("stage_compose.done 존재 → 스킵", "warning")
        return video_path

    if dry_run:
        _log(f"dry-run: compose → {video_path}")
        _mark_done(iter_dir, "compose")
        return video_path

    pipelines_dir = str(Path(__file__).parent)
    if pipelines_dir not in sys.path:
        sys.path.insert(0, pipelines_dir)

    from compose_video import compose  # type: ignore[import]

    # compose_video 는 videos/<topic>/final.mp4 로 출력
    out_dir = VIDEOS_DIR / topic
    t0 = time.monotonic()
    final = compose(
        topic=topic,
        scenes_json=scenes_json,
        slides_dir=slides_dir,
        audio_dir=audio_dir,
        output_dir=out_dir,
        force=force,
    )

    # iter_dir/video.mp4 로도 복사
    iter_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(final, video_path)
    _log(f"compose 완료 ({time.monotonic() - t0:.1f}s): {video_path}", "success")
    _mark_done(iter_dir, "compose")
    return video_path


def _run_scene_render(
    scenes_json: Path,
    scenes_dir: Path,
    slides_dir: Path,
    iter_dir: Path,
    dry_run: bool,
    force: bool,
) -> list[Path]:
    """S6.5 scene_render — Scene Object → sceneNN.mp4 per-scene."""
    _rule("[S6.5 scene_render] 시작")

    data = json.loads(scenes_json.read_text(encoding="utf-8"))
    scenes = data.get("scenes", [])

    pipelines_dir = str(Path(__file__).parent)
    if pipelines_dir not in sys.path:
        sys.path.insert(0, pipelines_dir)

    from render_template import validate_scene_templates  # type: ignore[import]

    validate_scene_templates(scenes)

    if not force and _is_done(iter_dir, "scene_render"):
        _log("stage_scene_render.done 존재 → 스킵", "warning")
        _db_record_stage("scene_render", "SKIP", 0.0)
        result = []
        for s in scenes:
            sid = s.get("id", 0)
            try:
                p = scenes_dir / f"scene{int(sid):02d}.mp4"
            except (ValueError, TypeError):
                p = scenes_dir / f"{sid}.mp4"
            result.append(p)
        return result

    if dry_run:
        _log(f"dry-run: scene_render → {scenes_dir}")
        _mark_done(iter_dir, "scene_render")
        return []

    from scene_render import render_scenes  # type: ignore[import]

    scenes_dir.mkdir(parents=True, exist_ok=True)

    for scene in scenes:
        if not scene.get("slide_path"):
            sid = scene.get("id", 0)
            try:
                png = slides_dir / f"scene{int(sid):02d}.png"
            except (ValueError, TypeError):
                png = slides_dir / f"{sid}.png"
            scene["slide_path"] = str(png)

    t0 = time.monotonic()
    rendered = render_scenes(scenes, scenes_dir, force=force)
    _sr_elapsed = time.monotonic() - t0
    _log(f"scene_render 완료 ({_sr_elapsed:.1f}s): {len(rendered)} 씬", "success")

    # render_path를 scenes.json에 저장 — _run_caption_overlay가 다음 단계에서 읽음
    scenes_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    _db_record_stage("scene_render", "DONE", _sr_elapsed)
    _mark_done(iter_dir, "scene_render")
    return rendered


def _run_caption_overlay(
    scenes_json: Path,
    scenes_dir: Path,
    iter_dir: Path,
    dry_run: bool,
    force: bool,
) -> None:
    """S6.8 caption_overlay — sceneNN.mp4 + caption_segments → sceneNN_captioned.mp4.

    DEPRECATED: Python caption overlay는 Remotion CaptionOverlay로 대체되었습니다.
    기본 파이프라인에서는 실행되지 않습니다.
    legacy 모드: 환경변수 LEGACY_CAPTION_OVERLAY=true 로만 활성화 가능.
    """
    _rule("[S6.8 caption_overlay] 시작")

    if not force and _is_done(iter_dir, "caption_overlay"):
        _log("stage_caption_overlay.done 존재 → 스킵", "warning")
        return

    if dry_run:
        _log(f"dry-run: caption_overlay → {scenes_dir}")
        _mark_done(iter_dir, "caption_overlay")
        return

    pipelines_dir = str(Path(__file__).parent)
    if pipelines_dir not in sys.path:
        sys.path.insert(0, pipelines_dir)

    from caption_renderer import make_caption_clips  # type: ignore[import]

    canvas_w = int(os.getenv("VIDEO_WIDTH", "1920"))
    canvas_h = int(os.getenv("VIDEO_HEIGHT", "1080"))

    data = json.loads(scenes_json.read_text(encoding="utf-8"))
    scenes = data.get("scenes", [])

    total_scenes = 0
    captioned_count = 0
    skipped_count = 0

    for scene in scenes:
        sid = scene.get("id", 0)
        render_path_str = scene.get("render_path")
        caption_segments = scene.get("caption_segments", [])
        total_scenes += 1

        try:
            sid_int = int(sid)
        except (ValueError, TypeError):
            sid_int = 0

        if not render_path_str or not Path(render_path_str).exists():
            _log(f"씬 {sid}: render_path 없음/미존재 → captioned_path=render_path", "warning")
            scene["captioned_path"] = render_path_str
            skipped_count += 1
            continue

        if not caption_segments:
            _log(f"씬 {sid}: caption_segments 없음 → captioned_path=render_path")
            scene["captioned_path"] = render_path_str
            skipped_count += 1
            continue

        captioned_path = scenes_dir / f"scene{sid_int:02d}_captioned.mp4"

        if not force and captioned_path.exists():
            _log(f"씬 {sid}: captioned 캐시 존재 → 스킵 ({captioned_path.name})", "warning")
            scene["captioned_path"] = str(captioned_path)
            captioned_count += 1
            print(
                f"[CAPTION_OVERLAY_AUDIT] scene={sid} segments={len(caption_segments)} "
                f"rendered=cached coverage_pct=cached captioned_path={captioned_path} result=SKIP",
                flush=True,
            )
            continue

        try:
            from moviepy.editor import VideoFileClip, CompositeVideoClip  # type: ignore[import]

            base_clip = VideoFileClip(str(render_path_str))

            # BASE_CLIP_AUDIT: 검정 프레임 검사
            first_frame = base_clip.get_frame(0)
            base_mean = float(first_frame.mean())
            base_non_black = base_mean > 5.0
            print(
                f"[BASE_CLIP_AUDIT] scene={sid} mean_pixel={base_mean:.1f} "
                f"frame_non_black={str(base_non_black).lower()}",
                flush=True,
            )

            if not base_non_black:
                _log(f"씬 {sid}: BASE_CLIP 검정 프레임 — captioned_path=render_path", "warning")
                scene["captioned_path"] = render_path_str
                skipped_count += 1
                base_clip.close()
                continue

            caption_clips = make_caption_clips(caption_segments, canvas_w, canvas_h, base_clip.duration)

            if not caption_clips:
                _log(f"씬 {sid}: caption_clips 생성 0개 → captioned_path=render_path", "warning")
                scene["captioned_path"] = render_path_str
                skipped_count += 1
                base_clip.close()
                continue

            composite = CompositeVideoClip([base_clip] + caption_clips, use_bgclip=True)
            # MoviePy CompositeVideoClip은 오디오를 자동 상속하지 않을 수 있으므로 명시적으로 설정
            if base_clip.audio is not None:
                composite = composite.set_audio(base_clip.audio)
            composite.write_videofile(
                str(captioned_path),
                codec="libx264",
                audio_codec="aac",
                logger=None,
                threads=2,
            )
            composite.close()
            base_clip.close()

            # CAPTIONED_CLIP_AUDIT: 검정 프레임 검사
            cap_check = VideoFileClip(str(captioned_path))
            cap_mean = float(cap_check.get_frame(0).mean())
            cap_non_black = cap_mean > 5.0
            cap_check.close()

            print(
                f"[CAPTIONED_CLIP_AUDIT] scene={sid} mean_pixel={cap_mean:.1f} "
                f"frame_non_black={str(cap_non_black).lower()}",
                flush=True,
            )

            rendered_count = len(caption_clips)
            coverage_pct = 100.0 * rendered_count / len(caption_segments)
            print(
                f"[CAPTION_OVERLAY_AUDIT] scene={sid} segments={len(caption_segments)} "
                f"rendered={rendered_count} coverage_pct={coverage_pct:.1f} "
                f"captioned_path={captioned_path} result=PASS",
                flush=True,
            )
            scene["captioned_path"] = str(captioned_path)
            captioned_count += 1

        except Exception as exc:
            _log(f"씬 {sid}: caption_overlay 실패({exc}) → captioned_path=render_path", "error")
            scene["captioned_path"] = render_path_str
            skipped_count += 1
            print(
                f"[CAPTION_OVERLAY_AUDIT] scene={sid} segments={len(caption_segments)} "
                f"rendered=0 coverage_pct=0.0 captioned_path={render_path_str} "
                f"result=FAIL error={exc}",
                flush=True,
            )

    # scenes.json에 captioned_path 기록
    scenes_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    coverage = 100.0 * captioned_count / total_scenes if total_scenes > 0 else 0.0
    audit_result = "PASS" if coverage >= 70.0 or total_scenes == 0 else "WARN"
    print(
        f"[CAPTION_OVERLAY_SUMMARY] total={total_scenes} captioned={captioned_count} "
        f"skipped={skipped_count} coverage_pct={coverage:.1f} result={audit_result}",
        flush=True,
    )

    _log(f"caption_overlay 완료: {captioned_count}/{total_scenes} 씬 자막 적용 ({audit_result})", "success")
    _mark_done(iter_dir, "caption_overlay")


def _run_final_concat(
    topic: str,
    scenes_json: Path,
    scenes_dir: Path,
    iter_dir: Path,
    dry_run: bool,
    force: bool,
) -> Path:
    """S7 final_concat — sceneNN.mp4 → videos/<topic>/final.mp4."""
    _rule("[S7 final_concat] 시작")

    video_path = iter_dir / "video.mp4"

    if not force and _is_done(iter_dir, "final_concat"):
        _log("stage_final_concat.done 존재 → 스킵", "warning")
        _db_record_stage("final_concat", "SKIP", 0.0)
        return video_path

    if dry_run:
        _log(f"dry-run: final_concat → {video_path}")
        _mark_done(iter_dir, "final_concat")
        return video_path

    pipelines_dir = str(Path(__file__).parent)
    if pipelines_dir not in sys.path:
        sys.path.insert(0, pipelines_dir)

    from final_concat import concat_from_scenes  # type: ignore[import]

    data = json.loads(scenes_json.read_text(encoding="utf-8"))
    scenes = data.get("scenes", [])

    iter_dir.mkdir(parents=True, exist_ok=True)
    concat_list = iter_dir / "concat_list.txt"

    t0 = time.monotonic()
    concat_from_scenes(scenes, video_path, concat_list_path=concat_list, force=force, scenes_dir=scenes_dir)
    _fc_elapsed = time.monotonic() - t0
    _log(f"final_concat 완료 ({_fc_elapsed:.1f}s): {video_path}", "success")
    _db_record_stage("final_concat", "DONE", _fc_elapsed)
    _mark_done(iter_dir, "final_concat")
    return video_path


# ── FAST_PATH minimal QA ──────────────────────────────────────────────────────

def _minimal_qa_scene_count_range(target_duration_sec: int, profile_cfg: dict) -> tuple[int, int, int]:
    from scene_budget import _SCENE_COUNT_MAX as _SCENE_MAX
    target_scene_count = max(
        profile_cfg["min_scenes"],
        min(round(target_duration_sec / 15), _SCENE_MAX),
    )
    min_allowed = max(profile_cfg["min_scenes"], int(target_scene_count * 0.5))
    max_allowed = min(_SCENE_MAX, max(profile_cfg["max_scenes"], int(target_scene_count * 1.5)))
    return target_scene_count, min_allowed, max_allowed


def _run_minimal_qa(
    scenes_json: Path,
    video_path: Path,
    iter_dir: Path,
    target_duration_sec: int,
    dry_run: bool,
    force: bool,
) -> None:
    """FAST_PATH 전용 최소 구조 검증 (LLM 호출 없음)."""
    _rule("[S8 minimal_qa (FAST_PATH)] 시작")

    if not force and _is_done(iter_dir, "qa"):
        _log("stage_qa.done 존재 → 스킵", "warning")
        _db_record_stage("qa", "SKIP", 0.0)
        return

    if dry_run:
        _log("dry-run: minimal_qa 스킵")
        _mark_done(iter_dir, "qa")
        return

    _mqa_t0 = time.monotonic()
    errors: list[str] = []

    # scenes.json 존재 확인
    if not scenes_json.exists():
        errors.append("scenes.json missing")
    else:
        import json as _json
        try:
            data = _json.loads(scenes_json.read_text(encoding="utf-8"))
            scenes = data.get("scenes", [])

            from generation_profiles import select_profile as _sel
            _, profile_cfg = _sel(target_duration_sec)

            max_total = profile_cfg["max_total_narration_chars"]
            target_scene_count, min_s, max_s = _minimal_qa_scene_count_range(
                target_duration_sec, profile_cfg
            )
            actual_scene_count = len(scenes)

            scene_status = "PASS" if min_s <= actual_scene_count <= max_s else "FAIL"
            _log(
                f"[MINIMAL_QA] target_scene_count={target_scene_count}"
                f" allowed_range=[{min_s}, {max_s}]"
                f" actual_scene_count={actual_scene_count} {scene_status}"
            )
            print(
                f"[MINIMAL_QA] target_scene_count={target_scene_count}"
                f" allowed_range=[{min_s},{max_s}]"
                f" actual_scene_count={actual_scene_count}"
                f" status={scene_status}",
                flush=True,
            )

            if scene_status == "FAIL":
                errors.append(
                    f"scene_count={actual_scene_count} not in [{min_s}, {max_s}]"
                )

            total_narration = 0
            for s in scenes:
                narration = s.get("narration", "")
                if not narration.strip():
                    errors.append(f"scene {s.get('id')}: narration empty")
                total_narration += len(narration)

                emphasis_total = sum(
                    len(b.get("emphasis", [])) for b in s.get("bullets", [])
                )
                if emphasis_total > 5:
                    errors.append(
                        f"scene {s.get('id')}: emphasis {emphasis_total} > 5"
                    )

            if total_narration > max_total:
                errors.append(f"total_narration={total_narration} > {max_total}")

        except Exception as exc:
            errors.append(f"scenes.json parse error: {exc}")

    # ── PART E: Audio gate — 오디오 파일 수 및 size 확인 ──────────────────────
    if scenes_json.exists():
        try:
            import json as _json2
            _data2 = _json2.loads(scenes_json.read_text(encoding="utf-8"))
            _scenes2 = _data2.get("scenes", [])
            _expected_audio = len(_scenes2)
            audio_dir2 = scenes_json.parent / "audio"
            _present_mp3s = [
                p for p in audio_dir2.glob("scene*.mp3") if p.stat().st_size > 0
            ] if audio_dir2.exists() else []
            if len(_present_mp3s) < _expected_audio:
                errors.append(
                    f"audio_gate: {len(_present_mp3s)}/{_expected_audio} mp3 present"
                )
                print(
                    f"[MINIMAL_QA_AUDIO_GATE] present={len(_present_mp3s)}"
                    f" expected={_expected_audio} status=FAIL",
                    flush=True,
                )
            else:
                print(
                    f"[MINIMAL_QA_AUDIO_GATE] present={len(_present_mp3s)}"
                    f" expected={_expected_audio} status=PASS",
                    flush=True,
                )

            # ── PART E: Subtitle gate — caption_segments coverage ─────────
            _with_caps = sum(1 for s in _scenes2 if s.get("caption_segments"))
            _cap_cov = _with_caps / max(_expected_audio, 1)
            if _cap_cov < 0.1:
                errors.append(
                    f"subtitle_gate: caption_coverage={_cap_cov:.0%}"
                    f" ({_with_caps}/{_expected_audio}) < 10%"
                )
                print(
                    f"[MINIMAL_QA_SUBTITLE_GATE] coverage={_cap_cov:.0%} status=FAIL",
                    flush=True,
                )
            else:
                print(
                    f"[MINIMAL_QA_SUBTITLE_GATE] coverage={_cap_cov:.0%} status=PASS",
                    flush=True,
                )
        except Exception as exc:
            _log(f"[MINIMAL_QA] audio/subtitle gate 확인 실패: {exc}", "warning")

    # final.mp4 존재 확인
    if not video_path.exists():
        errors.append(f"final.mp4 missing: {video_path}")
    else:
        try:
            import subprocess
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries",
                 "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
                 str(video_path)],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                actual_dur = float(result.stdout.strip())
                ratio = actual_dur / max(target_duration_sec, 1)
                # ±10% for long-form (≥1200s), ±30% for short tests
                _dur_lo, _dur_hi = (0.90, 1.10) if target_duration_sec >= 1200 else (0.70, 1.30)
                _dur_label = "±10%" if target_duration_sec >= 1200 else "±30%"
                if not (_dur_lo <= ratio <= _dur_hi):
                    errors.append(
                        f"video_duration={actual_dur:.1f}s target={target_duration_sec}s"
                        f" ratio={ratio:.2f} (out of {_dur_label})"
                    )
                else:
                    _log(
                        f"[MINIMAL_QA] video_duration={actual_dur:.1f}s"
                        f" target={target_duration_sec}s ratio={ratio:.2f} PASS"
                    )
                    print(
                        f"[MINIMAL_QA] actual_duration_sec={actual_dur:.1f}"
                        f" target_duration_sec={target_duration_sec}"
                        f" ratio={ratio:.2f} status=PASS",
                        flush=True,
                    )
        except Exception as exc:
            _log(f"ffprobe 실행 실패 (건너뜀): {exc}", "warning")

    if errors:
        for e in errors:
            _log(f"[MINIMAL_QA] FAIL: {e}", "warning")
        print(
            f"[MINIMAL_QA] status=WARN errors={len(errors)}",
            flush=True,
        )
    else:
        _log("[MINIMAL_QA] PASS — 모든 검증 통과", "success")

    # Visual Audit: final.mp4 픽셀 기반 검사
    pipelines_dir = str(Path(__file__).parent)
    if pipelines_dir not in sys.path:
        sys.path.insert(0, pipelines_dir)
    from qa_checks import run_visual_audit  # type: ignore[import]
    visual_result = run_visual_audit(video_path)
    visual_status = "PASS" if visual_result.get("passed") else "FAIL"
    for c in visual_result.get("checks", []):
        icon = "✅" if c["passed"] else "🔴"
        _log(f"{icon} [VISUAL_AUDIT/{c['name']}] {c['detail']}", "info" if c["passed"] else "warning")
    print(f"[VISUAL_AUDIT] status={visual_status}", flush=True)

    _mqa_elapsed = time.monotonic() - _mqa_t0
    _db_record_stage("qa", "DONE", _mqa_elapsed)
    _mark_done(iter_dir, "qa")


# ── 인라인 qa 단계 ────────────────────────────────────────────────────────────

def _run_qa(
    script_path: Path,
    scenes_json: Path,
    slides_dir: Path,
    video_path: Path,
    iter_dir: Path,
    dry_run: bool,
    force: bool,
) -> dict:
    """S8 qa — 5개 자동 QA 체크."""
    _rule("[S8 qa] 시작")

    if not force and _is_done(iter_dir, "qa"):
        _log("stage_qa.done 존재 → 스킵", "warning")
        _db_record_stage("qa", "SKIP", 0.0)
        return {}

    if dry_run:
        _log(f"dry-run: qa checks on {video_path}")
        _mark_done(iter_dir, "qa")
        return {"passed": True, "checks": [], "warnings": []}

    pipelines_dir = str(Path(__file__).parent)
    if pipelines_dir not in sys.path:
        sys.path.insert(0, pipelines_dir)

    from qa_checks import run_checks  # type: ignore[import]

    t0 = time.monotonic()
    _qa_result: dict = {}
    _qa_timed_out = False

    def _do_qa() -> None:
        nonlocal _qa_result
        _qa_result = run_checks(
            script_path=script_path,
            scenes_json_path=scenes_json,
            slides_dir=slides_dir,
            mp4_path=video_path,
            work_dir=iter_dir.parent.parent,  # _WORK_DIR_BASE: provider_audit.json 위치
        )

    with ThreadPoolExecutor(max_workers=1) as _exe:
        future = _exe.submit(_do_qa)
        try:
            future.result(timeout=_QA_TIMEOUT_SEC)
        except _FuturesTimeoutError:
            _qa_timed_out = True

    elapsed = time.monotonic() - t0
    if _qa_timed_out:
        print(
            f"[STAGE_TIMEOUT] stage=qa limit_sec={_QA_TIMEOUT_SEC}"
            f" elapsed_sec={elapsed:.0f} status=FAIL",
            flush=True,
        )
        print(f"[PROFILE] stage=qa duration_sec={elapsed:.1f} status=FAIL", flush=True)
        _db_record_stage("qa", "FAIL", elapsed, "STAGE_TIMEOUT")
        sys.exit(2)

    result = _qa_result
    report_path = iter_dir / "qa_report.json"
    report_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _log(
        f"QA {'통과 ✅' if result.get('passed') else '실패 🔴'} "
        f"— {elapsed:.1f}s | 리포트: {report_path}",
        "success" if result.get("passed") else "warning",
    )

    # Visual Audit: final.mp4 픽셀 기반 검사 (검정 프레임, 영상 스트림, concat 입력 파일)
    from qa_checks import run_visual_audit  # type: ignore[import]
    visual_result = run_visual_audit(video_path)
    visual_status = "PASS" if visual_result.get("passed") else "FAIL"
    for c in visual_result.get("checks", []):
        icon = "✅" if c["passed"] else "🔴"
        _log(f"{icon} [VISUAL_AUDIT/{c['name']}] {c['detail']}", "info" if c["passed"] else "warning")
    print(f"[VISUAL_AUDIT] status={visual_status}", flush=True)
    result["visual_audit"] = visual_result

    _db_record_stage("qa", "DONE", elapsed)
    _db_record_artifact("qa_report", str(report_path))
    _mark_done(iter_dir, "qa")
    return result


# ── MODE AUDIT ────────────────────────────────────────────────────────────────

def _write_mode_audit(
    requested_mode: str,
    selected_mode: str,
    reason: str,
    provider: str = "run_pipeline",
    result: str = "PASS",
    run_dir: Path | None = None,
) -> None:
    audit = {
        "requested_mode": requested_mode,
        "selected_mode": selected_mode,
        "reason": reason,
        "provider": provider,
        "result": result,
    }
    out_dir = run_dir or WORK_DIR
    mode_audit_path = out_dir / "mode_audit.json"
    out_dir.mkdir(parents=True, exist_ok=True)
    mode_audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"[MODE_AUDIT] requested={requested_mode} selected={selected_mode}"
        f" reason={reason} result={result}",
        flush=True,
    )


# ── AI MOTION BRANCH ──────────────────────────────────────────────────────────

def _run_ai_motion_branch(
    topic: str,
    scenes_json: Path,
    iter_dir: Path,
    run_dir: Path,
    dry_run: bool,
    force: bool,
) -> Path:
    """AI Motion 경로: scenes.json → motion_spec → primitive_tree → narration_manifest → final.mp4."""
    _rule("[AI_MOTION] AI Motion Branch 시작")

    pipelines_dir = str(Path(__file__).parent)
    if pipelines_dir not in sys.path:
        sys.path.insert(0, pipelines_dir)

    motion_dir = run_dir / "motion"
    motion_dir.mkdir(parents=True, exist_ok=True)

    motion_spec_path = motion_dir / "motion_spec.json"
    primitive_tree_path = motion_dir / "primitive_tree.json"
    narration_manifest_path = motion_dir / "narration_manifest.json"

    # ── Step 1: Motion Spec 생성 ──────────────────────────────────────────────
    _rule("[AI_MOTION S1] Motion Spec 생성")
    if not force and _is_done(iter_dir, "motion_spec"):
        _log("stage_motion_spec.done 존재 → 스킵", "warning")
    elif dry_run:
        _log("dry-run: motion_spec 생성 스킵")
        _mark_done(iter_dir, "motion_spec")
    else:
        from ai_motion_generator import generate_motion_spec  # type: ignore[import]

        if not scenes_json.exists():
            _log(f"scenes.json 없음: {scenes_json}", "error")
            sys.exit(1)

        data = json.loads(scenes_json.read_text(encoding="utf-8"))
        scene_plan = data.get("scenes", data) if isinstance(data, dict) else data

        t0 = time.monotonic()
        specs = generate_motion_spec(scene_plan, output_path=motion_spec_path)
        elapsed = time.monotonic() - t0
        _log(f"Motion Spec 생성 완료: {len(specs)}개 씬 ({elapsed:.1f}s)", "success")
        print(f"[PROFILE] stage=motion_spec duration_sec={elapsed:.1f} status=PASS", flush=True)
        _mark_done(iter_dir, "motion_spec")

    # ── Step 2: Motion Audit ──────────────────────────────────────────────────
    _rule("[AI_MOTION S2] Motion Audit")
    if not force and _is_done(iter_dir, "motion_audit"):
        _log("stage_motion_audit.done 존재 → 스킵", "warning")
    elif dry_run:
        _log("dry-run: motion_audit 스킵")
        _mark_done(iter_dir, "motion_audit")
    else:
        from motion_audit import audit_specs  # type: ignore[import]

        if not motion_spec_path.exists():
            _log(f"motion_spec.json 없음: {motion_spec_path}", "error")
            sys.exit(1)

        specs = json.loads(motion_spec_path.read_text(encoding="utf-8"))
        t0 = time.monotonic()
        report = audit_specs(specs)
        elapsed = time.monotonic() - t0

        print(
            f"[MOTION_AUDIT] passed={report.passed} total={report.total_scenes}"
            f" failed={report.failed_scenes}",
            flush=True,
        )
        if not report.passed:
            _log(f"Motion Audit FAIL — {report.failed_scenes}개 씬 실패", "error")
            print(f"[PROFILE] stage=motion_audit duration_sec={elapsed:.1f} status=FAIL", flush=True)
            sys.exit(1)

        _log(f"Motion Audit PASS ({elapsed:.1f}s)", "success")
        print(f"[PROFILE] stage=motion_audit duration_sec={elapsed:.1f} status=PASS", flush=True)
        _mark_done(iter_dir, "motion_audit")

    # ── Step 3: Primitive Renderer ────────────────────────────────────────────
    _rule("[AI_MOTION S3] Primitive Renderer")
    if not force and _is_done(iter_dir, "primitive_render"):
        _log("stage_primitive_render.done 존재 → 스킵", "warning")
    elif dry_run:
        _log("dry-run: primitive_render 스킵")
        _mark_done(iter_dir, "primitive_render")
    else:
        from primitive_renderer import render_motion_spec  # type: ignore[import]

        if not motion_spec_path.exists():
            _log(f"motion_spec.json 없음: {motion_spec_path}", "error")
            sys.exit(1)

        specs = json.loads(motion_spec_path.read_text(encoding="utf-8"))
        t0 = time.monotonic()
        render_motion_spec(specs, out_dir=motion_dir)
        elapsed = time.monotonic() - t0
        _log(f"Primitive Renderer 완료 ({elapsed:.1f}s)", "success")
        print(f"[PROFILE] stage=primitive_render duration_sec={elapsed:.1f} status=PASS", flush=True)
        _mark_done(iter_dir, "primitive_render")

    # ── Step 4: Narration Manifest (TTS + Caption) ────────────────────────────
    _rule("[AI_MOTION S4] Narration Manifest (TTS + Caption)")
    if not force and _is_done(iter_dir, "narration_manifest"):
        _log("stage_narration_manifest.done 존재 → 스킵", "warning")
    elif dry_run:
        _log("dry-run: narration_manifest 스킵")
        _mark_done(iter_dir, "narration_manifest")
    else:
        from motion_narration_adapter import run as _run_narration_adapter  # type: ignore[import]

        if not primitive_tree_path.exists():
            _log(f"primitive_tree.json 없음: {primitive_tree_path}", "error")
            sys.exit(1)

        t0 = time.monotonic()
        _run_narration_adapter(
            scenes_json=scenes_json,
            primitive_tree_json=primitive_tree_path,
            audio_dir=run_dir / "audio",
            narration_dir=run_dir / "narration",
            output_path=narration_manifest_path,
            topic=topic,
        )
        elapsed = time.monotonic() - t0
        _log(f"Narration Manifest 완료 ({elapsed:.1f}s)", "success")
        print(f"[PROFILE] stage=narration_manifest duration_sec={elapsed:.1f} status=PASS", flush=True)
        _mark_done(iter_dir, "narration_manifest")

    # ── Step 5: Primitive Scene Adapter → Final MP4 ───────────────────────────
    _rule("[AI_MOTION S5] Primitive Scene Adapter → Final MP4")
    final_mp4 = VIDEOS_DIR / topic / "final.mp4"
    if not force and _is_done(iter_dir, "primitive_scene_adapter"):
        _log("stage_primitive_scene_adapter.done 존재 → 스킵", "warning")
    elif dry_run:
        _log("dry-run: primitive_scene_adapter 스킵")
        _mark_done(iter_dir, "primitive_scene_adapter")
    else:
        from primitive_scene_adapter import PrimitiveSceneAdapter  # type: ignore[import]

        if not primitive_tree_path.exists():
            _log(f"primitive_tree.json 없음: {primitive_tree_path}", "error")
            sys.exit(1)

        t0 = time.monotonic()
        adapter = PrimitiveSceneAdapter(
            work_dir=motion_dir,
            videos_dir=VIDEOS_DIR,
            narration_manifest_path=narration_manifest_path,
        )
        render_report = adapter.run(
            primitive_tree_path=primitive_tree_path,
            topic=topic,
        )
        elapsed = time.monotonic() - t0

        if not render_report.passed:
            _log("Motion Render Audit FAIL", "error")
            print(f"[PROFILE] stage=primitive_scene_adapter duration_sec={elapsed:.1f} status=FAIL", flush=True)
            sys.exit(1)

        _log(f"Primitive Scene Adapter 완료 ({elapsed:.1f}s) → {final_mp4}", "success")
        print(f"[PROFILE] stage=primitive_scene_adapter duration_sec={elapsed:.1f} status=PASS", flush=True)
        _mark_done(iter_dir, "primitive_scene_adapter")

    _log(f"[AI_MOTION] 완료 → {final_mp4}", "success")
    return final_mp4


# ── 인라인 visual_correct 단계 ────────────────────────────────────────────────

def _run_visual_correct(
    scenes_json: Path,
    slides_dir: Path,
    iter_dir: Path,
    dry_run: bool,
    force: bool,
    use_vision: bool = False,
) -> None:
    """S6.1 visual_correct — 슬라이드 PNG 시각 검증 + 자동 수정 루프 (최대 3회). render 직후 실행."""
    _rule("[S6.1 visual_correct] 시작")

    if not force and _is_done(iter_dir, "visual_correct"):
        _log("stage_visual_correct.done 존재 → 스킵", "warning")
        return

    if dry_run:
        _log(f"dry-run: visual_correct (use_vision={use_vision})")
        _mark_done(iter_dir, "visual_correct")
        return

    if not scenes_json.exists():
        _log(f"scenes.json 없음: {scenes_json}", "error")
        sys.exit(1)

    pipelines_dir = str(Path(__file__).parent)
    if pipelines_dir not in sys.path:
        sys.path.insert(0, pipelines_dir)

    from visual_correct import correct_all  # type: ignore[import]

    data = json.loads(scenes_json.read_text(encoding="utf-8"))
    scenes = data.get("scenes", [])

    t0 = time.monotonic()
    results = correct_all(scenes, slides_dir, use_vision=use_vision, max_iter=3)

    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    elapsed = time.monotonic() - t0
    level = "success" if passed == total else "warning"
    _log(f"visual_correct 완료 — {passed}/{total} 통과 ({elapsed:.1f}s)", level)

    if passed < total:
        failed_ids = [r["scene_id"] for r in results if not r["passed"]]
        _log(f"수동 검수 필요한 씬: {failed_ids}", "warning")

    _mark_done(iter_dir, "visual_correct")


# ── 메인 실행 ─────────────────────────────────────────────────────────────────

_PIPELINE_TIMEOUT_SEC    = int(os.getenv("PIPELINE_TIMEOUT_SEC",    "900"))
_LLM_CALL_TIMEOUT_SEC   = int(os.getenv("LLM_CALL_TIMEOUT_SEC",   "300"))
# S4 씬 생성 전용 타임아웃: dynamic_llm_timeout(48씬)=720s × max_calls(2) + overhead(60s) = 1500s
# NARRATION_MIN_RETRY 포함 최대 2회 LLM 호출 허용
_SCENE_GEN_TIMEOUT_SEC  = int(os.getenv("SCENE_GEN_TIMEOUT_SEC",  "1500"))
_TTS_STAGE_TIMEOUT_SEC  = int(os.getenv("TTS_TIMEOUT_SEC",         "180"))
_RENDER_TIMEOUT_SEC     = int(os.getenv("RENDER_TIMEOUT_SEC",      "300"))
_FFMPEG_STAGE_TIMEOUT_SEC = int(os.getenv("FFMPEG_TIMEOUT_SEC",    "120"))
_QA_TIMEOUT_SEC         = int(os.getenv("QA_TIMEOUT_SEC",          "120"))


def calc_pipeline_timeout(scene_count: int) -> int:
    """30분 장편(120씬)까지 수용하는 동적 파이프라인 타임아웃.
    formula: min(max(1800, scene_count * 30), 7200)
    20sc→1800, 40sc→1800, 80sc→2400, 120sc→3600
    """
    return min(max(1800, scene_count * 30), 7200)


_pipeline_start_time: float = 0.0
_pipeline_effective_timeout: int = _PIPELINE_TIMEOUT_SEC
_pipeline_target_scene_count: int = 0


def _pipeline_timeout_handler(signum: int, frame: object) -> None:
    elapsed = time.monotonic() - _pipeline_start_time
    print(
        f"[PIPELINE_TIMEOUT] limit_sec={_pipeline_effective_timeout} elapsed_sec={elapsed:.0f}"
        f" target_scene_count={_pipeline_target_scene_count} status=FAIL",
        flush=True,
    )
    sys.exit(2)


def run(
    topic: str,
    input_path: Path | None,
    stop_after: str,
    dry_run: bool,
    force: bool,
    iteration: str = "latest",
    auto_correct: bool = False,
    target_duration_sec: int = 120,
    mode: str = "template",
    run_id: str | None = None,
    language: str = "ko",
    contents: str | None = None,
    prompt_filename: str | None = None,
    tts_provider: str = "azure",
    tts_voice: str | None = None,
    cancel_event: "threading.Event | None" = None,
) -> None:
    global _pipeline_start_time, _pipeline_effective_timeout, _pipeline_target_scene_count
    _pipeline_start_time = time.monotonic()
    _pipeline_target_scene_count = max(1, round(target_duration_sec / 15))
    _pipeline_effective_timeout = calc_pipeline_timeout(_pipeline_target_scene_count)
    _dynamic_scene_gen_timeout = max(
        _SCENE_GEN_TIMEOUT_SEC,
        max(120, min(900, _pipeline_target_scene_count * 15)) * 2 + 60,
    )
    # Local TTS providers (chatterbox/cosyvoice/f5tts/xtts) are much slower than cloud TTS.
    # Use a per-scene multiplier of 300s for local vs 5s for cloud.
    _LOCAL_TTS_PROVIDERS = {"chatterbox", "cosyvoice", "f5tts", "xtts"}
    if tts_provider in _LOCAL_TTS_PROVIDERS:
        _local_per_scene = int(os.getenv("LOCAL_TTS_PER_SCENE_SEC", "300"))
        _dynamic_tts_timeout = int(os.getenv(
            "LOCAL_TTS_TIMEOUT_SEC",
            str(_pipeline_target_scene_count * _local_per_scene + 120),
        ))
    else:
        _dynamic_tts_timeout = max(_TTS_STAGE_TIMEOUT_SEC, _pipeline_target_scene_count * 5 + 60)
    print(
        f"[PIPELINE_INIT] target_duration_sec={target_duration_sec}"
        f" target_scene_count={_pipeline_target_scene_count}"
        f" pipeline_timeout_sec={_pipeline_effective_timeout}"
        f" scene_gen_timeout_sec={_dynamic_scene_gen_timeout}"
        f" tts_timeout_sec={_dynamic_tts_timeout}",
        flush=True,
    )

    # Global pipeline timeout (Unix/macOS only; skipped in non-main threads e.g. API background tasks)
    import threading as _threading
    if hasattr(signal, "SIGALRM") and _threading.current_thread() is _threading.main_thread():
        signal.signal(signal.SIGALRM, _pipeline_timeout_handler)
        signal.alarm(_pipeline_effective_timeout)

    # ── Run ID 기반 격리 디렉토리 결정 ──────────────────────────────────────────
    # (thread-local run_id set below — no global needed)
    if run_id is None:
        _run_ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        run_id = f"{topic}_{language}_{_run_ts}"
    run_dir = _WORK_DIR_BASE / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    iter_dir = run_dir  # .done 플래그를 run_dir에 저장
    ver_num = 1  # 하위 호환용

    # submodule들이 run_dir을 WORK_DIR로 인식하도록 환경변수 업데이트
    os.environ["WORK_DIR"] = str(run_dir)

    # Contents Adapter: UI에서 전달된 raw 학습 자료를 input으로 사용
    if contents:
        _contents_path = run_dir / "user_contents.md"
        _contents_path.write_text(contents, encoding="utf-8")
        input_path = _contents_path
        _log(f"[contents] UI 전달 자료 → {_contents_path.relative_to(ROOT)} ({len(contents):,}자)")

    # ── Profile 결정 (create_run에 profile_name을 전달하기 위해 먼저 실행) ──────
    _pipelines_dir_early = str(Path(__file__).parent)
    if _pipelines_dir_early not in sys.path:
        sys.path.insert(0, _pipelines_dir_early)
    from generation_profiles import select_profile as _select_profile  # type: ignore[import]
    _profile_name, _profile_cfg = _select_profile(target_duration_sec)

    # ── DB: run 기록 시작 (실패 시 파이프라인 영향 없음) ─────────────────────
    _tls.run_id = run_id
    try:
        sys.path.insert(0, str(ROOT))
        from db import ops as _db_ops
        _db_ops.init()
        _db_ops.create_run(run_id, topic, str(input_path), str(run_dir), profile_name=_profile_name, language=language, contents=contents, target_duration_sec=target_duration_sec, mode=mode, prompt_filename=prompt_filename, tts_provider=tts_provider, tts_voice=tts_voice)
    except Exception as _db_exc:
        _log(f"[DB] 초기화 실패 (무시): {_db_exc}", "warning")

    _log(f"run_id={run_id} | run_dir={run_dir}")
    print(f"[RUN_ID] run_id={run_id} run_dir={run_dir}", flush=True)

    # artifact_manifest.json 초기화
    _input_path_str = str(input_path) if input_path else "topic_only"
    _artifact_manifest: dict = {
        "run_id": run_id,
        "topic": topic,
        "language": language,
        "started_at": datetime.datetime.utcnow().isoformat() + "Z",
        "selected_input_path": _input_path_str,
        "source_files": [_input_path_str] if input_path else [],
        "generated_files": [],
    }
    _log(f"[INPUT_SOURCE] topic={topic!r} input_path={_input_path_str!r}")
    (run_dir / "artifact_manifest.json").write_text(
        json.dumps(_artifact_manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _log(f"이터레이션: {iter_dir} (v{ver_num})")

    # ── Mode 결정 ────────────────────────────────────────────────────────────────
    pipelines_dir = str(Path(__file__).parent)
    if pipelines_dir not in sys.path:
        sys.path.insert(0, pipelines_dir)

    from motion_mode import resolve_mode as _resolve_mode  # type: ignore[import]

    requested_mode = mode if mode in _VALID_GENERATION_MODES else "template"
    effective_mode = _resolve_mode() if requested_mode == "auto" else requested_mode
    if requested_mode == "auto":
        _write_mode_audit(
            requested_mode=requested_mode,
            selected_mode=effective_mode,
            reason="auto_policy_video_style",
            run_dir=run_dir,
        )
    else:
        _write_mode_audit(
            requested_mode=requested_mode,
            selected_mode=effective_mode,
            reason="explicit_cli_flag",
            run_dir=run_dir,
        )

    _log(
        f"topic={topic}  language={language}  input={input_path}  stop_after={stop_after}  "
        f"dry_run={dry_run}  force={force}  iteration={iteration}  auto_correct={auto_correct}  "
        f"target_duration_sec={target_duration_sec}  mode={effective_mode}"
    )

    if dry_run:
        _log("=== dry-run: LLM/TTS 호출 없이 라우팅 결과만 출력 ===", "warning")
        pipelines_dir = str(Path(__file__).parent)
        if pipelines_dir not in sys.path:
            sys.path.insert(0, pipelines_dir)
        try:
            from llm_client import show_routing  # type: ignore[import]
            show_routing()
        except Exception as exc:
            _log(f"llm_client import 실패: {exc}", "warning")

    # ── Profile & FAST_PATH 결정 ────────────────────────────────────────────────
    # _profile_name / _profile_cfg already resolved above (before create_run)
    if _profile_cfg.get("fast_path") is not True:
        raise RuntimeError(
            "LONG_PATH has been removed. FAST_PATH is the only supported generation path."
        )

    _fast_path = True
    print(
        f"[FAST_PATH] enabled=true profile={_profile_name} reason=profile_policy",
        flush=True,
    )

    def _fast_skip(stage_key: str) -> None:
        print(
            f"[FAST_PATH_SKIP] stage={stage_key} reason=short_or_micro_profile",
            flush=True,
        )
        if not _is_done(iter_dir, stage_key):
            _mark_done(iter_dir, stage_key)

    # ── Removed LONG_PATH stages ───────────────────────────────────────────────
    # Product generation is FAST_PATH only. The former script/polish/critique/
    # regen stages are recorded as skipped for API progress compatibility.
    _fast_skip("script")
    if stop_after == "script":
        _log("stop_after=script 도달, 종료")
        return

    _fast_skip("polish")
    if stop_after == "polish":
        _log("stop_after=polish 도달, 종료")
        return

    _fast_skip("critique")
    if stop_after == "critique":
        _log("stop_after=critique 도달, 종료")
        return

    _fast_skip("regen")
    if stop_after == "regen":
        _log("stop_after=regen 도달, 종료")
        return

    # ── Content Adapter: input_type / content_type / scene_strategy → scene_plan.json ──
    if input_path and input_path.exists():
        # Force ROOT to position 0 — pipelines/content_adapter.py must not shadow the package
        _root_str = str(ROOT)
        if _root_str in sys.path:
            sys.path.remove(_root_str)
        sys.path.insert(0, _root_str)
        try:
            from content_adapter.adapter import adapt as _adapt
            from content_adapter.scene_strategy import build_scene_plan as _build_scene_plan
            _source_text = input_path.read_text(encoding="utf-8")
            _adapter_result = _adapt(_source_text)
            _log(
                f"[CONTENT_ADAPTER] input_type={_adapter_result['input_type']}"
                f" content_type={_adapter_result['content_type']}"
                f" scene_strategy={_adapter_result['scene_strategy']}"
                f" markdown={_adapter_result['adapter_notes']['markdown_detected']}"
            )
            print(
                f"[CONTENT_ADAPTER] input_type={_adapter_result['input_type']}"
                f" content_type={_adapter_result['content_type']}"
                f" scene_strategy={_adapter_result['scene_strategy']}",
                flush=True,
            )
            # scene_plan.json 생성 — direct_scene_gen이 자동으로 소비
            _scene_plan = _build_scene_plan(_adapter_result["scene_strategy"])
            _plan_scene_count = _scene_plan.get("scene_count", 0)
            _target_scene_count = max(1, round(target_duration_sec / 15))
            _scene_plan_path = run_dir / "content_adapter" / "scene_plan.json"
            if is_scene_plan_compatible(_plan_scene_count, _target_scene_count):
                _scene_plan_path.parent.mkdir(parents=True, exist_ok=True)
                _scene_plan_path.write_text(
                    json.dumps(_scene_plan, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                _log(
                    f"[CONTENT_ADAPTER] scene_plan.json 생성 → {_scene_plan_path.relative_to(ROOT)}"
                    f" strategy={_scene_plan['strategy']} scene_count={_scene_plan['scene_count']}"
                )
                print(
                    f"[CONTENT_ADAPTER] scene_plan_written={_scene_plan_path.relative_to(ROOT)}"
                    f" strategy={_scene_plan['strategy']}"
                    f" scene_count={_scene_plan['scene_count']}",
                    flush=True,
                )
            else:
                _log(
                    f"[CONTENT_ADAPTER] scene_plan SKIPPED — plan.scene_count={_plan_scene_count}"
                    f" < target_scene_count//2={_target_scene_count // 2}"
                    f" (target_duration={target_duration_sec}s → target_scenes={_target_scene_count});"
                    f" direct_scene_gen이 target_duration 기준으로 씬 수를 직접 계산"
                )
                print(
                    f"[CONTENT_ADAPTER] scene_plan SKIPPED"
                    f" plan_scene_count={_plan_scene_count}"
                    f" target_scene_count={_target_scene_count}",
                    flush=True,
                )
        except Exception as _exc:
            # MVP 검증 단계 — scene 생성 차단 없이 오류 노출
            _log(f"[CONTENT_ADAPTER] ERROR: {_exc}", "error")

    # ── S4: 직접 씬 생성 ─────────────────────────────────────────────────────
    scenes_json = run_dir / "scenes.json"
    _run_stage(
        stage_name="S4 직접씬생성(FAST_PATH)",
        module_name="direct_scene_gen",
        func_name="run",
        kwargs={
            "topic": topic,
            "target_duration_sec": target_duration_sec,
            "force": force,
            "input_path": input_path,
            "language": language,
        },
        dry_run=dry_run,
        iter_dir=iter_dir,
        stage_key="scenes",
        force=force,
        stage_timeout_sec=_dynamic_scene_gen_timeout,
    )
    print(
        "[FAST_PATH_SKIP] stage=summarizer_per_scene reason=fast_path_only",
        flush=True,
    )
    # direct_scene_gen re-resolves WORK_DIR at call time; this guard remains for
    # long-lived API processes with a cached module from before that fix.
    if not scenes_json.exists() and not dry_run:
        try:
            import direct_scene_gen as _dsg
            _actual = _dsg.OUTPUT_FILE
            if _actual.exists() and _actual != scenes_json:
                import shutil as _shutil
                _shutil.copy2(_actual, scenes_json)
                _log(f"[FIX] direct_scene_gen 출력 경로 재지정: {_actual} → {scenes_json}")
        except Exception as _e:
            _log(f"[FIX] direct_scene_gen 경로 수정 실패: {_e}", "warning")
    if scenes_json.exists() and not dry_run:
        try:
            from db import ops as _db_ops
            _db_ops.record_artifact(run_id, "scenes_json", str(scenes_json))
        except Exception:
            pass

    # ── Topic-Content Alignment Guardrail ─────────────────────────────────────
    if not dry_run:
        _llm_topic_guard(scenes_json, topic)

    if stop_after == "scenes":
        _log("stop_after=scenes 도달, 종료")
        return

    # ── S4.6: Scene Review — 반복/중복 나레이션 검출·제거 ─────────────────────
    if not _is_done(iter_dir, "scene_review"):
        if not dry_run:
            import scene_review as _srev
            _srev_result = _srev.run(
                scenes_json=scenes_json,
                run_dir=run_dir,
                topic=topic,
            )
            _log(
                f"S4.6 Scene Review 완료: algo={_srev_result['algo_changes']} "
                f"llm={_srev_result['llm_changes']}씬 수정"
            )
        else:
            _log("[DRY-RUN] S4.6 Scene Review 스킵")
        _mark_done(iter_dir, "scene_review")
    else:
        _log("stage_scene_review.done 존재 → 스킵", "warning")

    if stop_after == "scene_review":
        _log("stop_after=scene_review 도달, 종료")
        return

    # ── AI Motion 분기 ────────────────────────────────────────────────────────
    if effective_mode == "ai_motion":
        _rule("[MODE_ROUTER] AI Motion 경로 선택")
        _log(f"mode={effective_mode} → AI Motion Branch 진입", "info")
        ai_motion_video = _run_ai_motion_branch(
            topic=topic,
            scenes_json=scenes_json,
            iter_dir=iter_dir,
            run_dir=run_dir,
            dry_run=dry_run,
            force=force,
        )

        # latest 심볼릭 링크 갱신
        if not dry_run:
            latest = _WORK_DIR_BASE / "latest"
            target = run_dir.resolve()
            if latest.is_symlink() or latest.exists():
                latest.unlink()
            latest.symlink_to(target)
            _log(f"work/latest → {target}", "success")

        _mark_done(iter_dir, "final")

        if hasattr(signal, "SIGALRM") and _threading.current_thread() is _threading.main_thread():
            signal.alarm(0)

        elapsed_total = time.monotonic() - _pipeline_start_time
        _log(
            f"[AI_MOTION] 파이프라인 완료 — v{ver_num} | video: {ai_motion_video}"
            f" | 총 소요: {elapsed_total:.1f}s",
            "success",
        )
        print(f"[PROFILE] stage=TOTAL duration_sec={elapsed_total:.1f} status=PASS", flush=True)

        if not dry_run:
            _ai_mp4 = str(ai_motion_video) if ai_motion_video else ""
            try:
                from db import ops as _db_ops
                if _ai_mp4:
                    _db_ops.record_artifact(run_id, "final_mp4", _ai_mp4)
                _db_ops.complete_run(run_id, _ai_mp4, status="DONE")
            except Exception:
                pass
            if _ai_mp4:
                _publish_htube_output(run_id, topic, run_dir, _ai_mp4)
        return

    # ── S4.5: 씬 분류 (template_type 할당) ────────────────────────────────────
    # FAST_PATH는 direct_scene_gen이 이미 template_type+visual_data를 LLM에서 생성했으므로
    # classifier로 덮어쓰면 template_type/visual_data 불일치 발생 → SKIP
    if _fast_path:
        print(
            "[FAST_PATH_SKIP] stage=scene_classifier reason=template_type_already_assigned_by_llm",
            flush=True,
        )
    elif not dry_run:
        import json as _json
        import scene_classifier as _sc
        _scenes_data = _json.loads(scenes_json.read_text(encoding="utf-8"))
        _classified = _sc.classify(_scenes_data.get("scenes", []))
        _scenes_data["scenes"] = _classified
        scenes_json.write_text(_json.dumps(_scenes_data, ensure_ascii=False, indent=2), encoding="utf-8")
        _log(f"S4.5 씬분류 완료: {len(_classified)}개 씬 template_type 할당")
    else:
        _log("[DRY-RUN] S4.5 씬분류 스킵")

    # ── S4.7: Scene Quality Layer — 검사 + 자동 보정 ─────────────────────────
    if not _is_done(iter_dir, "scene_quality"):
        if not dry_run:
            _sq_t0 = time.monotonic()
            import scene_quality_layer as _sql
            _sql_result = _sql.run(
                scenes_json=scenes_json,
                run_dir=run_dir,
                topic=topic,
                input_path=input_path,
            )
            if _sql_result["status"] == "FAIL":
                _log(f"Scene Quality Layer FAIL — 구조 손상 감지, 파이프라인 중단", "error")
                _db_record_stage("scene_quality", "FAIL", time.monotonic() - _sq_t0, "scene structure damage detected")
                import sys as _sys
                _sys.exit(1)
            _log(
                f"S4.7 Scene Quality Layer 완료: status={_sql_result['status']} "
                f"corrections={_sql_result['corrections']}"
            )
        else:
            _log("[DRY-RUN] S4.7 Scene Quality Layer 스킵")
        _mark_done(iter_dir, "scene_quality")
    else:
        _log("stage_scene_quality.done 존재 → 스킵", "warning")

    if stop_after == "scene_quality":
        _log("stop_after=scene_quality 도달, 종료")
        return

    # ── S4.8: Content Repair Loop ─────────────────────────────────────────────
    if not _is_done(iter_dir, "content_repair"):
        if not dry_run:
            _cr_t0 = time.monotonic()
            import content_repair as _cr
            _cr_result = _cr.run(
                scenes_json=scenes_json,
                run_dir=run_dir,
                topic=topic,
            )
            _cr_status = _cr_result["status"]
            if _cr_status == "FAIL":
                _log(f"Content Repair FAIL — scenes 로드 불가, 파이프라인 중단", "error")
                _db_record_stage("content_repair", "FAIL", time.monotonic() - _cr_t0, "scenes load failed")
                import sys as _sys
                _sys.exit(1)
            _log(
                f"S4.8 Content Repair 완료: status={_cr_status} "
                f"issues={len(_cr_result['issues'])} repairs={_cr_result['repairs']}"
            )
            _db_record_stage("content_repair", _cr_status, time.monotonic() - _cr_t0)
        else:
            _log("[DRY-RUN] S4.8 Content Repair Loop 스킵")
        _mark_done(iter_dir, "content_repair")
    else:
        _log("stage_content_repair.done 존재 → 스킵", "warning")

    if stop_after == "content_repair":
        _log("stop_after=content_repair 도달, 종료")
        return

    # ── S5: TTS (synth_narration) — render 이전 ───────────────────────────────
    audio_dir = run_dir / "audio"
    narration_dir = run_dir / "narration"
    _tts_cache_used = _run_tts_synth(
        scenes_json=scenes_json,
        audio_dir=audio_dir,
        narration_dir=narration_dir,
        iter_dir=iter_dir,
        dry_run=dry_run,
        force=force,
        topic=topic,
        language=language,
        tts_timeout_sec=_dynamic_tts_timeout,
        tts_provider=tts_provider,
        tts_voice=tts_voice,
        cancel_event=cancel_event,
    )
    if cancel_event and cancel_event.is_set():
        _log("cancel_event 감지 — TTS 이후 파이프라인 중단", "warning")
        try:
            from db import ops as _db_ops_cancel
            _db_ops_cancel.cancel_run(run_id)
        except Exception:
            pass
        return
    try:
        from db import ops as _db_ops_tts
        _db_ops_tts.update_tts_metadata(
            run_id=run_id,
            tts_voice=tts_voice,
            tts_cache_used=bool(_tts_cache_used),
        )
    except Exception as _tts_db_exc:
        _log(f"[DB] TTS metadata update 실패 (무시): {_tts_db_exc}", "warning")
    if stop_after == "tts":
        _log("stop_after=tts 도달, 종료")
        return

    # ── S5.1/S5.2: Caption 생성 — CAPTION_SOURCE 기반 라우팅 ────────────────────
    # Caption source는 narration 직접 경로로 고정. STT/Whisper 경로 사용 금지.
    _run_caption_from_narration(
        scenes_json=scenes_json,
        iter_dir=iter_dir,
        dry_run=dry_run,
        force=force,
    )
    if not _is_done(iter_dir, "whisper_align"):
        _mark_done(iter_dir, "whisper_align")
    if not _is_done(iter_dir, "caption_segment"):
        _mark_done(iter_dir, "caption_segment")

    if stop_after == "whisper_align":
        _log("stop_after=whisper_align 도달, 종료")
        return
    if stop_after == "caption_segment":
        _log("stop_after=caption_segment 도달, 종료")
        return

    # ── S5.2a: Caption timing alignment — text/order 보존, timing만 선택 보정 ────
    _run_caption_timing_align(
        scenes_json=scenes_json,
        audio_dir=audio_dir,
        iter_dir=iter_dir,
        dry_run=dry_run,
        force=force,
    )
    if stop_after == "caption_timing_align":
        _log("stop_after=caption_timing_align 도달, 종료")
        return

    # ── S5.3: Caption validation 루프 ─────────────────────────────────────────
    _run_caption_validate(
        scenes_json=scenes_json,
        iter_dir=iter_dir,
        dry_run=dry_run,
        force=force,
    )
    if stop_after == "caption_validate":
        _log("stop_after=caption_validate 도달, 종료")
        return

    # ── S5.4: Motion anchor 생성 — render 이전 ────────────────────────────────
    _run_motion_anchor_gen(
        scenes_json=scenes_json,
        iter_dir=iter_dir,
        dry_run=dry_run,
        force=force,
    )
    if stop_after == "motion_anchor":
        _log("stop_after=motion_anchor 도달, 종료")
        return

    # ── S6: 슬라이드 렌더 — audio_duration/caption/motion 확보 후 ─────────────
    slides_dir = run_dir / "slides"
    if cancel_event and cancel_event.is_set():
        _log("cancel_event 감지 — render 이전 파이프라인 중단", "warning")
        try:
            from db import ops as _db_ops_cancel
            _db_ops_cancel.cancel_run(run_id)
        except Exception:
            pass
        return
    _pre_render_integrity_check(scenes_json)
    _run_render(
        scenes_json=scenes_json,
        slides_dir=slides_dir,
        iter_dir=iter_dir,
        dry_run=dry_run,
        force=force,
        cancel_event=cancel_event,
    )
    if stop_after == "render":
        _log("stop_after=render 도달, 종료")
        return

    # ── S6.1: 슬라이드 시각 검증 + 자동 수정 (--auto-correct 시에만) ──────────
    if auto_correct:
        _run_visual_correct(
            scenes_json=scenes_json,
            slides_dir=slides_dir,
            iter_dir=iter_dir,
            dry_run=dry_run,
            force=force,
            use_vision=True,
        )
    else:
        if not _is_done(iter_dir, "visual_correct"):
            _mark_done(iter_dir, "visual_correct")

    if stop_after == "visual_correct":
        _log("stop_after=visual_correct 도달, 종료")
        return

    # ── S6.2: Scene Manifest 검증 — scene/audio/slide count 정합성 ────────────
    if not dry_run:
        try:
            import scene_manifest as _smf
            _smf.validate(
                scenes_json=scenes_json,
                audio_dir=audio_dir,
                slides_dir=slides_dir,
            )
            _log("S6.2 Scene Manifest 검증: PASS")
        except RuntimeError as _me:
            _log(f"S6.2 Scene Manifest 검증 FAIL — 파이프라인 중단\n{_me}", "error")
            import sys as _sys
            _sys.exit(1)
    else:
        _log("[DRY-RUN] S6.2 Scene Manifest 검증 스킵")

    # ── S6.5: Scene 단위 MP4 렌더 ─────────────────────────────────────────────
    scenes_dir = run_dir / "scenes"
    if cancel_event and cancel_event.is_set():
        _log("cancel_event 감지 — scene_render 이전 파이프라인 중단", "warning")
        try:
            from db import ops as _db_ops_cancel
            _db_ops_cancel.cancel_run(run_id)
        except Exception:
            pass
        return
    _run_scene_render(
        scenes_json=scenes_json,
        scenes_dir=scenes_dir,
        slides_dir=slides_dir,
        iter_dir=iter_dir,
        dry_run=dry_run,
        force=force,
    )
    # Track used Video Templates in DB (non-critical — silently caught)
    if not dry_run and scenes_json.exists() and run_id:
        try:
            from render_template import _COMPOSITION_ID as _COMP_MAP  # type: ignore[import]
            from db import ops as _db_ops
            _scenes_data = json.loads(scenes_json.read_text(encoding="utf-8"))
            _used_comps: list[str] = []
            for _s in _scenes_data.get("scenes", []):
                _tt = _s.get("template_type") or "flow_steps"
                _comp = _COMP_MAP.get(_tt) or _COMP_MAP.get(_tt.upper(), _tt)
                if _comp not in _used_comps:
                    _used_comps.append(_comp)
            _db_ops.update_video_template(
                run_id,
                _used_comps[0] if _used_comps else "",
                json.dumps(_used_comps),
            )
        except Exception as _vt_exc:
            _log(f"[DB] video_template 추적 실패 (무시): {_vt_exc}", "warning")
    if stop_after == "scene_render":
        _log("stop_after=scene_render 도달, 종료")
        return

    # ── S6.8: Caption Overlay ─────────────────────────────────────────────────
    # DEPRECATED: Python caption overlay는 기본 비활성화됨.
    # Caption Owner = Remotion CaptionOverlay (render_path에 자막 포함).
    # legacy 모드 활성화: 환경변수 LEGACY_CAPTION_OVERLAY=true 설정.
    if os.getenv("LEGACY_CAPTION_OVERLAY", "false").lower() == "true":
        _run_caption_overlay(
            scenes_json=scenes_json,
            scenes_dir=scenes_dir,
            iter_dir=iter_dir,
            dry_run=dry_run,
            force=force,
        )
    else:
        _log("[S6.8] caption_overlay SKIPPED — Caption Owner = Remotion CaptionOverlay", "warning")
        _mark_done(iter_dir, "caption_overlay")
    if stop_after == "caption_overlay":
        _log("stop_after=caption_overlay 도달, 종료")
        return

    # ── S7: Final Concat ──────────────────────────────────────────────────────
    if cancel_event and cancel_event.is_set():
        _log("cancel_event 감지 — final_concat 이전 파이프라인 중단", "warning")
        try:
            from db import ops as _db_ops_cancel
            _db_ops_cancel.cancel_run(run_id)
        except Exception:
            pass
        return
    video_path = _run_final_concat(
        topic=topic,
        scenes_json=scenes_json,
        scenes_dir=scenes_dir,
        iter_dir=iter_dir,
        dry_run=dry_run,
        force=force,
    )
    if stop_after in ("compose", "final_concat"):
        _log(f"stop_after={stop_after} 도달, 종료")
        return

    # ── S8: 자동 QA ────────────────────────────────────────────────────────────
    if _fast_path:
        _run_minimal_qa(
            scenes_json=scenes_json,
            video_path=video_path,
            iter_dir=iter_dir,
            target_duration_sec=target_duration_sec,
            dry_run=dry_run,
            force=force,
        )
    else:
        qa_result = _run_qa(
            script_path=base_script,
            scenes_json=scenes_json,
            slides_dir=slides_dir,
            video_path=video_path,
            iter_dir=iter_dir,
            dry_run=dry_run,
            force=force,
        )
    if stop_after == "qa":
        _log("stop_after=qa 도달, 종료")
        if not dry_run and run_id:
            try:
                from db import ops as _db_ops
                _final_mp4 = str(run_dir / "video.mp4")
                _db_ops.record_artifact(run_id, "final_mp4", _final_mp4)
                _db_ops.complete_run(run_id, _final_mp4, status="DONE")
            except Exception:
                pass
            _publish_htube_output(run_id, topic, run_dir, str(run_dir / "video.mp4"))
        return

    # ── latest 심볼릭 링크 갱신 ────────────────────────────────────────────────
    if not dry_run:
        latest = _WORK_DIR_BASE / "latest"
        target = run_dir.resolve()
        if latest.is_symlink() or latest.exists():
            latest.unlink()
        latest.symlink_to(target)
        _log(f"work/latest → {target}", "success")

    _mark_done(iter_dir, "final")

    # Cancel global timeout on successful completion
    if hasattr(signal, "SIGALRM") and _threading.current_thread() is _threading.main_thread():
        signal.alarm(0)

    if not dry_run:
        try:
            from db import ops as _db_ops
            _final_mp4 = str(run_dir / "video.mp4")
            _db_ops.record_artifact(run_id, "final_mp4", _final_mp4)
            _db_ops.complete_run(run_id, _final_mp4, status="DONE")
        except Exception:
            pass
        _publish_htube_output(run_id, topic, run_dir, str(run_dir / "video.mp4"))

    elapsed_total = time.monotonic() - _pipeline_start_time
    _log(
        f"파이프라인 완료 — v{ver_num} | video: {video_path if not dry_run else 'dry-run'}"
        f" | 총 소요: {elapsed_total:.1f}s",
        "success",
    )
    print(f"[PROFILE] stage=TOTAL duration_sec={elapsed_total:.1f} status=PASS", flush=True)


# ── Input Resolution ───────────────────────────────────────────────────────────

def _resolve_input_path(topic: str, inputs_dir: Path) -> tuple[Path, bool]:
    """topic 기반 입력 파일 탐색. (resolved_path, is_fallback) 반환."""
    # 1. inputs/<topic>.md (직접 매칭)
    candidate = inputs_dir / f"{topic}.md"
    if candidate.exists():
        return candidate, False

    # 2. inputs/<topic-hyphens>.md (공백→하이픈)
    slug = topic.replace(" ", "-")
    candidate = inputs_dir / f"{slug}.md"
    if candidate.exists():
        return candidate, False

    # 3. 파일 첫 줄 heading 매칭 (# 제목 → topic 포함 여부)
    for md_file in sorted(inputs_dir.glob("*.md")):
        if md_file.name == "report.md":
            continue
        try:
            first_line = md_file.read_text(encoding="utf-8").split("\n")[0]
            if topic in first_line:
                return md_file, False
        except Exception:
            continue

    # 4. fallback
    return inputs_dir / "report.md", True


# ── CLI ────────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_pipeline.py",
        description=(
            "AI 영상 자동화 파이프라인 통합 러너.\n"
            "  S2(대본) → S8(QA) 전 단계를 순서대로 실행한다."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--topic", required=True, help="프로젝트 슬러그")
    p.add_argument(
        "--input", dest="input_path", default=None, metavar="FILE",
        help="입력 보고서 경로 (미지정 시 topic 기반 자동 탐색, 기본 fallback: inputs/report.md)",
    )
    p.add_argument(
        "--stop-after", dest="stop_after",
        choices=STOP_STAGES, default="final",
        help="지정 단계 완료 후 중단 (기본: final)",
    )
    p.add_argument("--dry-run", action="store_true",
                   help="LLM/TTS 호출 없이 라우팅 결과만 출력")
    p.add_argument("--force", action="store_true",
                   help=".done 플래그 무시하고 전 단계 재실행")
    p.add_argument(
        "--iteration", default="latest", metavar="new|latest|v<n>",
        help="이터레이션 버전 (new=새 버전, latest=최신 기준, v<n>=특정 버전)",
    )
    p.add_argument(
        "--auto-correct", dest="auto_correct", action="store_true",
        help="슬라이드 시각 검증 + 자동 수정 루프 활성화 (CLI-only: API vision 비활성)",
    )
    p.add_argument(
        "--target-duration", dest="target_duration_sec", type=int, default=120,
        help="목표 영상 길이(초) — scene_budget 씬 수 상한 결정에 사용됨 (기본: 120)",
    )
    p.add_argument(
        "--mode", dest="mode",
        choices=["template", "ai_motion", "auto"], default="template",
        help="생성 모드: template(기본)|ai_motion(AI Motion 경로)|auto(video_style 기반 자동 선택)",
    )
    p.add_argument(
        "--language", default="ko",
        choices=["ko", "en", "zh-CN"],
        help="출력 언어 (기본: ko)",
    )
    return p


def main() -> None:
    args = _build_parser().parse_args()

    inputs_dir = Path(os.environ.get("INPUTS_DIR", "inputs"))
    if args.input_path is not None:
        # --input 명시: 최우선 사용
        input_path = Path(args.input_path)
        _log(f"selected_input_path={input_path}  (--input 명시)")
    else:
        # --topic만 지정: topic 기반 자동 탐색
        input_path, is_fallback = _resolve_input_path(args.topic, inputs_dir)
        if is_fallback:
            _log(
                f"[WARNING] topic '{args.topic}'에 매칭되는 inputs 파일을 찾지 못했습니다. "
                f"fallback: {input_path}",
                "warning",
            )
        else:
            _log(f"selected_input_path={input_path}  (topic 기반 탐색)")

    if not input_path.exists():
        _log(f"--input 파일을 찾을 수 없습니다: {input_path}", "error")
        sys.exit(1)
    if input_path.is_dir():
        _log(f"--input 에 디렉토리가 지정되었습니다: {input_path}", "error")
        sys.exit(1)
    run(
        topic=args.topic,
        input_path=input_path,
        stop_after=args.stop_after,
        dry_run=args.dry_run,
        force=args.force,
        iteration=args.iteration,
        auto_correct=args.auto_correct,
        target_duration_sec=args.target_duration_sec,
        mode=args.mode,
        language=args.language,
    )


if __name__ == "__main__":
    main()
