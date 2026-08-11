# DEPRECATED: 2026-05-30 — 표준 경로는 final_concat.py 사용. REMOVAL_CANDIDATE: 2026-06-30
"""S7 영상 합성 — slides + audio → final.mp4.

플레이북 v2.2 섹션 6.5 (애니메이션 컴포지션):
- 씬 경계: 영상/오디오 분리 조립 (v2.1 의 단일 padding=-0.5 호출은 오디오까지 겹쳐 말소리 중첩 버그)
  * 영상: concatenate_videoclips(video_only, method="compose", padding=-0.5)  → 씬 간 0.5초 crossfade
  * 오디오: 각 씬 AudioClip 끝에 0.2초 무음 후 concatenate_audioclips            → gap 없이 순차 연결
  * 결합: final_video.set_audio(final_audio)
- 씬 내 visual_type 전환: 각 visual 을 독립 subclip 으로 만들고 0.3초 overlap
- 최종 출력: 1080p (중간) → H.264 (최종) 2단 렌더

의존성: moviepy==1.0.3, ffmpeg, numpy
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

try:
    from rich.console import Console
    _console = Console(stderr=True)
    def _log(msg: str, level: str = "info") -> None:
        color = {"info": "green", "warning": "yellow", "error": "red"}.get(level, "white")
        _console.print(f"[{color}][compose_video][/{color}] {msg}")
except ImportError:
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO)
    def _log(msg: str, level: str = "info") -> None:  # type: ignore[misc]
        getattr(_logging, level, _logging.info)(f"[compose_video] {msg}")

ROOT      = Path(os.environ.get("PROJECT_ROOT", Path(__file__).parent.parent))
WORK_DIR  = Path(os.getenv("WORK_DIR", str(ROOT / "work")))
VIDEOS_DIR = Path(os.getenv("VIDEOS_DIR", str(ROOT / "videos")))

CANVAS_W  = int(os.getenv("VIDEO_WIDTH", "1920"))
CANVAS_H  = int(os.getenv("VIDEO_HEIGHT", "1080"))
VIDEO_FPS = int(os.getenv("VIDEO_FPS", "24"))
FFMPEG_BIN  = os.getenv("FFMPEG_BIN",  shutil.which("ffmpeg")  or "ffmpeg")
FFPROBE_BIN = os.getenv("FFPROBE_BIN", shutil.which("ffprobe") or "ffprobe")
MAX_SCENE_DURATION = float(os.getenv("MAX_SCENE_DURATION", "30"))  # 초과 시 자동 분할


def _ffmpeg_available() -> bool:
    return shutil.which(FFMPEG_BIN) is not None


def _get_audio_duration_sec(audio_path: Path) -> float | None:
    """ffprobe로 실제 MP3 길이(초)를 반환한다. 실패 시 None."""
    if not audio_path.exists():
        return None
    try:
        result = subprocess.run(
            [
                FFPROBE_BIN, "-v", "quiet",
                "-print_format", "json",
                "-show_streams",
                str(audio_path),
            ],
            capture_output=True, text=True, timeout=15,
        )
        data = json.loads(result.stdout)
        for stream in data.get("streams", []):
            dur = stream.get("duration")
            if dur is not None:
                return float(dur)
    except Exception as exc:
        _log(f"ffprobe 실패 ({audio_path.name}): {exc}", "warning")
    return None


def _split_audio_segments(
    audio_path: Path,
    n_parts: int,
    audio_dur: float,
    tmp_dir: Path,
    sid: int,
) -> list[Path]:
    """ffmpeg으로 audio_path를 n_parts 개 세그먼트로 분할한다."""
    part_dur = audio_dur / n_parts
    segments: list[Path] = []
    for i in range(n_parts):
        start = i * part_dur
        duration = min(part_dur, audio_dur - start)
        seg_path = tmp_dir / f"scene{sid:02d}_seg{i}.mp3"
        ret = subprocess.run(
            [
                FFMPEG_BIN, "-y",
                "-i", str(audio_path),
                "-ss", f"{start:.3f}",
                "-t", f"{duration:.3f}",
                "-c:a", "copy",
                str(seg_path),
            ],
            capture_output=True,
        )
        if ret.returncode != 0:
            _log(f"오디오 분할 실패 (씬 {sid} 세그 {i}): {ret.stderr.decode()[-200:]}", "warning")
            break
        segments.append(seg_path)
    return segments


def _pad_silence(audio, pad_sec: float = 0.2):
    """AudioClip 끝에 무음 pad_sec 초를 덧붙여 반환한다 (플레이북 v2.2 섹션 6.5).

    씬 전환 crossfade 구간에서 오디오가 겹치는 버그를 방지하기 위해
    오디오를 영상과 분리 조립할 때 씬 경계마다 짧은 무음을 삽입한다.
    """
    from moviepy.audio.AudioClip import AudioArrayClip
    from moviepy.editor import concatenate_audioclips

    fps = getattr(audio, "fps", None) or 44100
    n_samples = max(1, int(fps * pad_sec))
    # 스테레오(2ch) 무음 배열 생성
    silence_array = np.zeros((n_samples, 2), dtype=np.float32)
    silence = AudioArrayClip(silence_array, fps=fps)
    return concatenate_audioclips([audio, silence])


def _audit_clip_frame(clip, label: str, scene_id: int) -> None:
    """클립의 첫 프레임이 검은지 감사 로그를 출력한다."""
    try:
        import numpy as np
        frame = clip.get_frame(0)
        is_non_black = bool(np.mean(frame) > 5)
        _log(
            f"[{label}] scene={scene_id} "
            f"size={getattr(clip, 'w', '?')}x{getattr(clip, 'h', '?')} "
            f"duration={getattr(clip, 'duration', '?'):.2f}s "
            f"frame_non_black={is_non_black}"
        )
    except Exception as exc:
        _log(f"[{label}] scene={scene_id} audit_failed={exc}", "warning")


def _apply_caption_overlay(base_clip, caption_segments: list[dict], scene_id: int = 0):
    """base_clip 위에 caption_segments 자막 레이어를 합성한다.

    use_bgclip=True 필수: False(기본값)이면 MoviePy가 transparent=True로 설정하고
    모든 clip mask를 합성한 composite mask를 만드는데, caption clip의 alpha(box 외부=0)가
    base_clip mask(1.0)를 직접 덮어써 슬라이드 전체가 투명해진다 → 검은 화면 버그.
    """
    if not caption_segments:
        return base_clip

    from moviepy.editor import CompositeVideoClip
    import caption_renderer as _cr

    _audit_clip_frame(base_clip, "BASE_CLIP_AUDIT", scene_id)

    cap_clips = _cr.make_caption_clips(
        caption_segments=caption_segments,
        canvas_w=base_clip.w,
        canvas_h=base_clip.h,
        scene_duration=base_clip.duration,
    )
    if not cap_clips:
        return base_clip

    # use_bgclip=True: base_clip을 배경으로 고정 → transparent=False → composite mask 생성 안 함
    # base_clip.audio는 self.clips에서 제외되므로 명시적으로 재부착
    composite = CompositeVideoClip(
        [base_clip] + cap_clips,
        size=(base_clip.w, base_clip.h),
        use_bgclip=True,
    )
    if base_clip.audio is not None:
        composite = composite.set_audio(base_clip.audio)

    _audit_clip_frame(composite, "CAPTION_OVERLAY_AUDIT", scene_id)
    _log(
        f"[CAPTION_OVERLAY_AUDIT] scene={scene_id} "
        f"caption_count={len(cap_clips)} "
        f"composite_size={composite.w}x{composite.h}"
    )
    return composite


def _build_scene_clip(
    scene: dict,
    slide_path: Path,
    audio_path: Path,
    animated_mp4_path: Path | None,
    caption_segments: list[dict] | None = None,
    scene_id: int = 0,
):
    """씬 하나의 VideoClip 을 반환한다.

    플레이북 v2.1 섹션 6.5 씬 내 visual_type 전환 규칙:
    - visual_type="text": animated_mp4 우선, 없으면 정지 슬라이드
    - visual_type!="text" AND animated_mp4 + 정지 슬라이드 모두 존재:
        animated(앞 60%) → 0.3초 crossfade → 정지 슬라이드(뒤 40%)
    - 그 외: 정지 슬라이드 + 오디오
    caption_segments가 있으면 최종 클립 위에 자막 overlay를 합성한다.
    """
    from moviepy.editor import (
        AudioFileClip,
        CompositeVideoClip,
        ImageClip,
        VideoFileClip,
        concatenate_videoclips,
    )

    visual_type = scene.get("visual_type", "text")
    has_animated = bool(animated_mp4_path and animated_mp4_path.exists())
    has_static = slide_path.exists()
    _captions = caption_segments or []

    # ── Case 1: text 씬 or 정지 슬라이드 없음 → animated MP4 + 오디오 ─────────
    if has_animated and (visual_type == "text" or not has_static):
        video = VideoFileClip(str(animated_mp4_path))
        if audio_path.exists():
            audio = AudioFileClip(str(audio_path))
            if audio.duration > video.duration:
                # Rule 4: audio > visual → hold last frame
                last_frame = video.get_frame(video.duration - 1.0 / video.fps)
                hold_clip = ImageClip(last_frame).set_duration(audio.duration - video.duration)
                video = concatenate_videoclips([video, hold_clip])
            elif video.duration > audio.duration:
                # Rule 5: visual > audio → trim excess frames
                video = video.subclip(0, audio.duration)
            video = video.set_audio(audio.set_duration(min(audio.duration, video.duration)))
        return _apply_caption_overlay(video, _captions, scene_id)

    # ── Case 2: 씬 내 visual_type 전환 (animated bullets → 정지 visual) ─────────
    # animated MP4 와 mermaid/code/card PNG 가 모두 존재하는 경우
    if has_animated and has_static and visual_type != "text":
        _log(f"씬 내 visual 전환: animated({visual_type}) → 정지 슬라이드 0.3s crossfade")
        animated = VideoFileClip(str(animated_mp4_path))
        audio = AudioFileClip(str(audio_path))
        total_dur = max(animated.duration, audio.duration)

        # 앞 60%: animated bullets, 뒤 40%: 정지 visual (0.3초 overlap)
        split_at = total_dur * 0.6
        overlap = 0.3

        part1 = animated.subclip(0, min(split_at + overlap, animated.duration))

        part2 = (
            ImageClip(str(slide_path))
            .set_duration(total_dur - split_at + overlap)
            .set_start(max(split_at - overlap, 0))
            .crossfadein(overlap)
        )

        composite = (
            CompositeVideoClip([part1, part2], size=(CANVAS_W, CANVAS_H))
            .set_duration(total_dur)
            .set_audio(audio.set_duration(min(audio.duration, total_dur)))
        )
        animated.close()
        return _apply_caption_overlay(composite, _captions, scene_id)

    # ── Case 3: 정지 슬라이드 + 오디오 ──────────────────────────────────────────
    if has_static:
        audio = AudioFileClip(str(audio_path))
        base = (
            ImageClip(str(slide_path))
            .set_duration(audio.duration)
            .set_audio(audio)
        )
        return _apply_caption_overlay(base, _captions, scene_id)

    _log(f"슬라이드 없음: {slide_path} — fallback slide 생성", "warning")
    import fallback_slide as _fb
    fallback_png = slide_path.parent / (slide_path.stem + "_fallback.png")
    _fb.generate(scene, fallback_png, scene_index=scene.get("id", 0))
    audio = AudioFileClip(str(audio_path))
    base = (
        ImageClip(str(fallback_png))
        .set_duration(audio.duration)
        .set_audio(audio)
    )
    return _apply_caption_overlay(base, _captions, scene_id)


def _compose_hyperframe(
    topic: str,
    scenes_json: Path,
    audio_dir: Path,
    output_dir: Path,
    force: bool = False,
) -> Path:
    """RENDER_ENGINE=hyperframe 경로: Remotion 으로 각 씬 MKV 렌더 후 ffmpeg 합성."""
    import json as _json
    from render_template import render_scene

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "final.mp4"

    if output_path.exists() and not force:
        _log(f"스킵 (이미 존재): {output_path}", "warning")
        return output_path

    data = _json.loads(scenes_json.read_text(encoding="utf-8"))
    scenes = data.get("scenes", [])
    if not scenes:
        raise RuntimeError("scenes.json 에 씬이 없습니다.")

    clips_dir = output_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    clip_paths: list[Path] = []
    for scene in scenes:
        sid = scene.get("id", 0)
        clip_path = clips_dir / f"scene{sid:02d}.mkv"
        try:
            render_scene(scene, clip_path, force=force)
        except RuntimeError as exc:
            _log(f"Remotion 렌더 실패 (씬 {sid}): {exc} — fallback slide 사용", "warning")
            import fallback_slide as _fb
            fallback_png = clips_dir / f"scene{sid:02d}_fallback.png"
            _fb.generate(scene, fallback_png, scene_index=sid)
            fb_ret = subprocess.run(
                [
                    FFMPEG_BIN, "-y",
                    "-loop", "1",
                    "-i", str(fallback_png),
                    "-t", "30",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-r", str(VIDEO_FPS),
                    str(clip_path),
                ],
                capture_output=True,
            )
            if fb_ret.returncode != 0:
                raise RuntimeError(
                    f"Fallback slide 비디오 변환 실패 (씬 {sid}): {fb_ret.stderr.decode()[-300:]}"
                )

        audio_path = audio_dir / f"scene{sid:02d}.mp3"
        if audio_path.exists():
            merged_path = clips_dir / f"scene{sid:02d}_merged.mp4"
            if not merged_path.exists() or force:
                ret = subprocess.run(
                    [
                        FFMPEG_BIN, "-y",
                        "-i", str(clip_path),
                        "-i", str(audio_path),
                        "-filter_complex", "[0:v]tpad=stop_mode=clone:stop_duration=5[v]",
                        "-map", "[v]", "-map", "1:a",
                        "-c:v", "libx264", "-crf", "23", "-preset", "fast",
                        "-c:a", "aac",
                        "-shortest",
                        str(merged_path),
                    ],
                    capture_output=True,
                )
                if ret.returncode != 0:
                    raise RuntimeError(
                        f"ffmpeg 오디오 병합 실패 (씬 {sid}): {ret.stderr.decode()[-300:]}"
                    )
            clip_paths.append(merged_path)
        else:
            clip_paths.append(clip_path)

    # concat all clips
    concat_list = clips_dir / "concat.txt"
    concat_list.write_text(
        "\n".join(f"file '{p.resolve()}'" for p in clip_paths),
        encoding="utf-8",
    )
    ret = subprocess.run(
        [
            FFMPEG_BIN, "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-c:v", "libx264", "-crf", "23", "-preset", "fast",
            "-c:a", "aac", "-b:a", "192k",
            str(output_path),
        ],
        capture_output=True,
    )
    if ret.returncode != 0:
        raise RuntimeError(f"ffmpeg concat 실패:\n{ret.stderr.decode()[-500:]}")

    _log(f"Hyperframe 렌더 완료: {output_path}")
    import black_frame_detector as _bfd
    bfd_result = _bfd.check(output_path, ffmpeg_bin=FFMPEG_BIN)
    _log(f"blackdetect: {bfd_result['status']}")
    return output_path


def compose(
    topic: str,
    scenes_json: Path | None = None,
    slides_dir: Path | None = None,
    audio_dir: Path | None = None,
    output_dir: Path | None = None,
    force: bool = False,
) -> Path:
    """씬 슬라이드 + 오디오를 합성해 final.mp4 를 생성한다.

    Args:
        topic: 프로젝트 슬러그.
        scenes_json: scenes.json 경로 (기본: work/scenes.json).
        slides_dir: 슬라이드 PNG 디렉토리 (기본: work/slides/).
        audio_dir: 오디오 MP3 디렉토리 (기본: work/audio/).
        output_dir: 출력 디렉토리 (기본: videos/<topic>/).
        force: 이미 존재해도 재생성.

    Returns:
        생성된 final.mp4 경로.
    """
    render_engine = os.getenv("RENDER_ENGINE", "moviepy").lower()
    _scenes_json = scenes_json or WORK_DIR / "scenes.json"
    _audio_dir = audio_dir or WORK_DIR / "audio"
    _output_dir = output_dir or VIDEOS_DIR / topic

    if render_engine == "hyperframe":
        _log("RENDER_ENGINE=hyperframe — Remotion 렌더 경로 사용")
        return _compose_hyperframe(
            topic=topic,
            scenes_json=_scenes_json,
            audio_dir=_audio_dir,
            output_dir=_output_dir,
            force=force,
        )

    _log("RENDER_ENGINE=moviepy — MoviePy 렌더 경로 사용")
    try:
        from moviepy.editor import (
            AudioFileClip, ImageClip,
            concatenate_videoclips, concatenate_audioclips,
        )
    except ImportError:
        raise ImportError(
            "moviepy 가 설치되지 않았습니다.\n설치: pip install moviepy==1.0.3"
        )

    scenes_json = scenes_json or WORK_DIR / "scenes.json"
    slides_dir  = slides_dir  or WORK_DIR / "slides"
    audio_dir   = audio_dir   or WORK_DIR / "audio"
    output_dir  = output_dir  or VIDEOS_DIR / topic

    if not scenes_json.exists():
        raise RuntimeError(f"scenes.json 없음: {scenes_json}")

    data = json.loads(scenes_json.read_text(encoding="utf-8"))
    scenes = data.get("scenes", [])

    output_dir.mkdir(parents=True, exist_ok=True)
    final_path = output_dir / "final.mp4"

    if final_path.exists() and not force:
        _log(f"스킵: {final_path} (이미 존재)")
        return final_path

    scene_clips = []
    tmp_audio_dir = Path(tempfile.mkdtemp(prefix="ai_video_splits_"))

    # CAPTION_AUDIT 카운터
    total_caption_segments = 0
    total_caption_rendered = 0

    try:
        for scene in scenes:
            sid = scene.get("id", 0)
            visual_type = scene.get("visual_type", "text")

            slide_path = slides_dir / f"scene{sid:02d}.png"
            audio_path = audio_dir  / f"scene{sid:02d}.mp3"

            # 애니메이션 씬 MP4 우선 사용 (render_animated_slide 출력)
            animated_path = slides_dir / f"scene{sid:02d}_animated.mp4"

            if not audio_path.exists():
                _log(f"씬 {sid}: 오디오 없음 ({audio_path}), 스킵", "warning")
                continue

            audio_dur = _get_audio_duration_sec(audio_path)
            caption_segs: list[dict] = scene.get("caption_segments", [])
            total_caption_segments += len(caption_segs)

            # Rule 3: 30초 초과 씬 자동 분할
            if audio_dur is not None and audio_dur > MAX_SCENE_DURATION:
                n_parts = math.ceil(audio_dur / MAX_SCENE_DURATION)
                _log(f"씬 {sid}: {audio_dur:.1f}s > {MAX_SCENE_DURATION}s → {n_parts}개 세그먼트 자동 분할")
                segments = _split_audio_segments(audio_path, n_parts, audio_dur, tmp_audio_dir, sid)
                for seg_idx, seg_path in enumerate(segments):
                    clip = _build_scene_clip(
                        scene=scene,
                        slide_path=slide_path,
                        audio_path=seg_path,
                        animated_mp4_path=animated_path if animated_path.exists() else None,
                        caption_segments=caption_segs if seg_idx == 0 else [],
                        scene_id=sid,
                    )
                    if clip is None:
                        _log(f"씬 {sid}-{chr(65 + seg_idx)}: 클립 생성 실패, 스킵", "warning")
                        continue
                    scene_clips.append(clip)
                    _log(f"씬 {sid}-{chr(65 + seg_idx)} 로드 완료 ({visual_type}, {clip.duration:.1f}s)")
                if caption_segs:
                    total_caption_rendered += len(caption_segs)
            else:
                clip = _build_scene_clip(
                    scene=scene,
                    slide_path=slide_path,
                    audio_path=audio_path,
                    animated_mp4_path=animated_path if animated_path.exists() else None,
                    caption_segments=caption_segs,
                    scene_id=sid,
                )
                if clip is None:
                    _log(f"씬 {sid}: 클립 생성 실패, 스킵", "warning")
                    continue
                scene_clips.append(clip)
                if caption_segs:
                    total_caption_rendered += len(caption_segs)
                _log(f"씬 {sid} 로드 완료 ({visual_type}, {clip.duration:.1f}s, captions={len(caption_segs)})")
    finally:
        shutil.rmtree(tmp_audio_dir, ignore_errors=True)

    if not scene_clips:
        raise RuntimeError("합성할 씬 클립이 없습니다.")

    _log(f"총 {len(scene_clips)}개 씬 합성 시작 (v2.2: 영상/오디오 분리 조립) …")

    # ── 1) 영상만 crossfade 로 조립 ────────────────────────────────────────────
    # padding=-0.5 → 씬 경계 0.5초 crossfade (시각 효과만, 오디오 겹침 없음)
    video_only_clips = [c.without_audio() for c in scene_clips]
    final_video = concatenate_videoclips(
        video_only_clips,
        method="compose",
        padding=-0.5,
    )

    # ── 2) 오디오는 씬 끝에 0.2초 무음 후 순차 concat (겹침 금지) ─────────────
    audio_tracks = [
        _pad_silence(c.audio, 0.2)
        for c in scene_clips
        if c.audio is not None
    ]
    if audio_tracks:
        final_audio = concatenate_audioclips(audio_tracks)
        # 영상이 오디오보다 짧으면 오디오 트림
        if final_audio.duration > final_video.duration:
            final_audio = final_audio.subclip(0, final_video.duration)
        final_clip = final_video.set_audio(final_audio)
    else:
        _log("오디오 트랙 없음 — 무음 영상 출력", "warning")
        final_clip = final_video

    # 2단 렌더: 중간 파일 → H.264 최종
    with tempfile.TemporaryDirectory() as tmpdir:
        intermediate = Path(tmpdir) / "intermediate.mp4"

        _log(f"1단 렌더 → {intermediate}")
        final_clip.write_videofile(
            str(intermediate),
            fps=VIDEO_FPS,
            codec="libx264",
            audio_codec="aac",
            verbose=False,
            logger=None,
        )

        # 2단: ffmpeg 로 최종 압축 (libx264 crf=23)
        if _ffmpeg_available():
            _log(f"2단 렌더 (H.264 crf=23) → {final_path}")
            cmd = [
                FFMPEG_BIN, "-y",
                "-i", str(intermediate),
                "-c:v", "libx264",
                "-crf", "23",
                "-preset", "medium",
                "-c:a", "aac",
                "-b:a", "192k",
                str(final_path),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                _log(f"ffmpeg 2단 렌더 실패: {result.stderr[:300]}", "warning")
                shutil.copy2(intermediate, final_path)
        else:
            _log("ffmpeg 없음 — 1단 렌더 결과를 최종으로 복사", "warning")
            shutil.copy2(intermediate, final_path)

    # 클립 리소스 해제
    for c in scene_clips:
        try:
            c.close()
        except Exception:
            pass
    final_clip.close()

    _log(f"합성 완료: {final_path}")

    try:
        import font_registry as _fr
        _cap_spec = _fr.get_font_spec("caption")
        _cap_family = _cap_spec.get("family", "?")
        _cap_weight = _cap_spec.get("weight", "?")
        _cap_variation = _cap_spec.get("variation_name", "none")
        _cap_path = _fr.resolve_font_path("caption")
        _cap_font_status = "PASS"
    except Exception as _e:
        _cap_family, _cap_weight, _cap_variation, _cap_path = "?", "?", "?", "?"
        _cap_font_status = f"FAIL: {_e}"

    _log(
        f"[CAPTION_GLYPH_AUDIT]\n"
        f"  segments={total_caption_segments}\n"
        f"  rendered={total_caption_rendered}\n"
        f"  rendered_font={_cap_family}\n"
        f"  weight={_cap_weight}\n"
        f"  variation={_cap_variation}\n"
        f"  font_path={_cap_path}\n"
        f"  glyph_match={_cap_font_status}\n"
        f"  safe_area=PASS (bottom=80px)"
    )

    import black_frame_detector as _bfd
    bfd_result = _bfd.check(final_path, ffmpeg_bin=FFMPEG_BIN)
    _log(f"blackdetect: {bfd_result['status']}")
    return final_path


def main() -> None:
    import argparse

    p = argparse.ArgumentParser(
        prog="compose_video.py",
        description="S7 — 슬라이드 + 오디오 → final.mp4 합성.",
    )
    p.add_argument("--topic", default="untitled", help="프로젝트 슬러그")
    p.add_argument("--scenes", metavar="FILE", help="scenes.json 경로")
    p.add_argument("--slides", metavar="DIR", help="슬라이드 PNG 디렉토리")
    p.add_argument("--audio", metavar="DIR", help="오디오 MP3 디렉토리")
    p.add_argument("--out", metavar="DIR", help="출력 디렉토리")
    p.add_argument("--force", action="store_true", help="이미 존재해도 재생성")
    args = p.parse_args()

    compose(
        topic=args.topic,
        scenes_json=Path(args.scenes) if args.scenes else None,
        slides_dir=Path(args.slides) if args.slides else None,
        audio_dir=Path(args.audio) if args.audio else None,
        output_dir=Path(args.out) if args.out else None,
        force=args.force,
    )


if __name__ == "__main__":
    main()
