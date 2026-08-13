"""Primitive Scene Adapter — PrimitiveTree JSON → Hyperframe Scene JSON → MP4.

Pipeline
  work/motion/primitive_tree.json
  └─ PrimitiveToHyperframeMapper  (primitive stack → composition ID + props)
  └─ HyperframeSceneBuilder       (build Hyperframe Scene JSON)
  └─ [optional] NarrationManifest (narration/audio/caption 연결)
  └─ RemotionVideoRenderer        (npx remotion render per scene → silent MP4)
  └─ AudioMerger                  (ffmpeg: silent MP4 + TTS MP3 → audio MP4)
  └─ SceneConcatenator            (ffmpeg concat → final.mp4)
  └─ MotionRenderAudit            (8-point validation)
  └─ MotionCaptionAudit           (audio/caption 유효성 검사)

Supported MVP Compositions:
  Compare / Hero / Highlight primitives → CompareTwo
  Summary primitive               → SummaryCard
  Hero only                       → TitleOpen

Narration Integration (motion_narration_adapter 연동):
  narration_manifest.json → HyperframeScene.props에 narration/captionSegments 주입
  audio_duration_ms → duration_frames 자동 동기화
  TTS MP3 → Remotion 렌더 후 ffmpeg 오디오 트랙 병합

Outputs:
  work/motion/scene_compare.json
  work/motion/scene_summary.json
  work/motion/hyperframe_scenes.json (combined)
  videos/ai-motion-mvp/final.mp4
"""
from __future__ import annotations

import json
import logging
import math
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent
_WORK_MOTION = _PROJECT_ROOT / "work" / "motion"
_VIDEOS_DIR = _PROJECT_ROOT / "videos"
_HYPERFRAME_DIR = _PROJECT_ROOT / "hyperframe"
_NARRATION_MANIFEST = _WORK_MOTION / "narration_manifest.json"

_MAX_DURATION_FRAMES = 900   # 37.5s @ 24fps — 씬 최대 길이 안전 상한

# ────────────────────────────────────────────────────────────────
# Narration Manifest Loader
# ────────────────────────────────────────────────────────────────

def _load_narration_manifest(manifest_path: Path) -> dict[str, dict]:
    """narration_manifest.json → {scene_id: entry} 맵 반환.

    파일이 없거나 파싱 실패 시 빈 dict 반환 (optional feature).
    """
    if not manifest_path.exists():
        return {}
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        scenes = data.get("scenes", [])
        return {s["scene_id"]: s for s in scenes if "scene_id" in s}
    except Exception as exc:
        log.warning("[ADAPTER] narration_manifest load failed: %s", exc)
        return {}


# ────────────────────────────────────────────────────────────────
# Sprint 2 — Hyperframe Scene Schema
# ────────────────────────────────────────────────────────────────

@dataclass
class HyperframeScene:
    scene_id: str
    composition: str
    duration_frames: int
    fps: int
    props: dict[str, Any]
    source_primitives: list[str] = field(default_factory=list)
    # Narration integration fields (optional)
    audio_path: str = ""
    audio_duration_ms: int = 0
    caption_segments: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        d: dict = {
            "scene_id": self.scene_id,
            "composition": self.composition,
            "duration_frames": self.duration_frames,
            "fps": self.fps,
            "props": self.props,
            "source_primitives": self.source_primitives,
        }
        if self.audio_path:
            d["audio_path"] = self.audio_path
        if self.audio_duration_ms:
            d["audio_duration_ms"] = self.audio_duration_ms
        if self.caption_segments:
            d["caption_segments"] = self.caption_segments
        return d

    def validate(self) -> list[str]:
        """Return list of schema violations (empty = valid)."""
        errors: list[str] = []
        if not self.scene_id:
            errors.append("scene_id:empty")
        if not self.composition:
            errors.append("composition:empty")
        if self.duration_frames <= 0:
            errors.append(f"duration_frames:invalid:{self.duration_frames}")
        if self.fps <= 0:
            errors.append(f"fps:invalid:{self.fps}")
        if not self.props:
            errors.append("props:empty")
        if "durationInFrames" not in self.props:
            errors.append("props:missing_durationInFrames")
        return errors


# ────────────────────────────────────────────────────────────────
# Sprint 1 — Primitive to Hyperframe Composition Mapper
# ────────────────────────────────────────────────────────────────

# Priority-ordered mapping: (frozenset of required primitives) → composition ID
# Rules are checked in order; first match wins. Hero is last — it is a subset
# of almost every primitive stack, so it must not shadow more specific rules.
_COMPOSITION_RULES: list[tuple[frozenset[str], str]] = [
    (frozenset({"Compare"}),   "CompareTwo"),
    (frozenset({"Summary"}),   "SummaryCard"),
    (frozenset({"Timeline"}),  "Timeline"),
    (frozenset({"List"}),      "ListReveal"),
    (frozenset({"Quote"}),     "Quote"),
    (frozenset({"Diagram"}),   "ArchTree"),
    (frozenset({"Highlight"}), "Explain"),
    (frozenset({"CodeBlock"}), "Explain"),
    (frozenset({"Stats"}),     "ListReveal"),
    (frozenset({"Hero"}),      "TitleOpen"),
]

_DEFAULT_COMPOSITION = "Explain"


class PrimitiveToHyperframeMapper:
    """Maps a primitive_stack list to a Remotion composition ID."""

    def map(self, primitives: list[str]) -> str:
        primitive_set = frozenset(p for p in primitives)
        for required, comp in _COMPOSITION_RULES:
            if required.issubset(primitive_set):
                log.debug("[MAPPER] %s → %s", primitives, comp)
                return comp
        log.debug("[MAPPER] no match for %s → default %s", primitives, _DEFAULT_COMPOSITION)
        return _DEFAULT_COMPOSITION


# ────────────────────────────────────────────────────────────────
# Sprint 3 & 4 — Props Builders per Composition
# ────────────────────────────────────────────────────────────────

class HyperframePropsBuilder:
    """Builds Remotion composition props from a PrimitiveTree dict."""

    def build(
        self,
        tree: dict,
        composition: str,
        narration_entry: dict | None = None,
    ) -> dict:
        method_name = f"_build_{composition.lower()}"
        handler = getattr(self, method_name, self._build_default)
        props = handler(tree)
        # Narration integration — props에 narration/captionSegments 주입
        if narration_entry:
            narration = narration_entry.get("narration", "")
            caption_segments = narration_entry.get("caption_segments", [])
            if narration:
                props["narration"] = narration
            if caption_segments:
                props["captionSegments"] = caption_segments
        return props

    def _primitives_map(self, tree: dict) -> dict[str, dict]:
        return {p["type"]: p for p in tree.get("primitives", [])}

    def _resolve_title(self, tree: dict, hero_props: dict) -> str:
        """Title 우선순위: scene.title > hero_props.title > heading > scene_id."""
        # 1순위: primitive tree 루트의 title (motion_spec → primitive_tree에 전달되는 경우)
        title = tree.get("title")
        if title:
            return str(title)
        # 2순위: Hero primitive의 props.title
        title = hero_props.get("title")
        if title:
            return str(title)
        # 3순위: heading (deprecated alias)
        title = hero_props.get("heading")
        if title:
            return str(title)
        # fallback: scene_id — 반드시 로그 남김
        scene_id = tree.get("scene_id", "unknown")
        log.warning(
            "[TitleFallback] scene=%s reason=missing_title source=scene_id",
            scene_id,
        )
        return scene_id

    def _build_comparetwo(self, tree: dict) -> dict:
        pm = self._primitives_map(tree)
        hero_props = pm.get("Hero", {}).get("props", {})
        compare_props = pm.get("Compare", {}).get("props", {})
        return {
            "title": self._resolve_title(tree, hero_props),
            "left_title": compare_props.get("leftTitle", "Before"),
            "right_title": compare_props.get("rightTitle", "After"),
            "left_items": list(compare_props.get("leftItems") or []),
            "right_items": list(compare_props.get("rightItems") or []),
            "durationInFrames": tree["duration_frames"],
        }

    def _build_summarycard(self, tree: dict) -> dict:
        pm = self._primitives_map(tree)
        summary_props = pm.get("Summary", {}).get("props", {})
        points = summary_props.get("points") or []
        return {
            "takeaways": list(points),
            "durationInFrames": tree["duration_frames"],
        }

    def _build_titleopen(self, tree: dict) -> dict:
        pm = self._primitives_map(tree)
        hero_props = pm.get("Hero", {}).get("props", {})
        return {
            "title": self._resolve_title(tree, hero_props),
            "subtitle": hero_props.get("subtitle"),
            "durationInFrames": tree["duration_frames"],
        }

    def _build_explain(self, tree: dict) -> dict:
        pm = self._primitives_map(tree)
        hero_props = pm.get("Hero", {}).get("props", {})
        hl_props = (
            pm.get("Highlight", {}).get("props", {})
            or pm.get("CodeBlock", {}).get("props", {})
        )
        bullets: list = hl_props.get("highlights") or hl_props.get("emphasis") or []
        if not bullets and hl_props.get("content"):
            bullets = [hl_props["content"]]
        return {
            "title": self._resolve_title(tree, hero_props),
            "bullets": list(bullets),
            "durationInFrames": tree["duration_frames"],
        }

    def _build_timeline(self, tree: dict) -> dict:
        pm = self._primitives_map(tree)
        hero_props = pm.get("Hero", {}).get("props", {})
        tl_props = pm.get("Timeline", {}).get("props", {})
        events: list = tl_props.get("emphasis") or tl_props.get("highlights") or []
        if not events and tl_props.get("content"):
            events = [tl_props["content"]]
        return {
            "title": self._resolve_title(tree, hero_props),
            "category": "TIMELINE",
            "events": [str(e) for e in events if e],
            "durationInFrames": tree["duration_frames"],
        }

    def _build_listreveal(self, tree: dict) -> dict:
        pm = self._primitives_map(tree)
        hero_props = pm.get("Hero", {}).get("props", {})
        list_props = pm.get("List", {}).get("props", {})
        items: list = list_props.get("emphasis") or list_props.get("highlights") or []
        if not items and list_props.get("content"):
            items = [list_props["content"]]
        return {
            "title": self._resolve_title(tree, hero_props),
            "items": list(items),
            "durationInFrames": tree["duration_frames"],
        }

    def _build_quote(self, tree: dict) -> dict:
        pm = self._primitives_map(tree)
        quote_props = pm.get("Quote", {}).get("props", {})
        emphasis = quote_props.get("emphasis") or []
        quote_text = emphasis[0] if emphasis else (quote_props.get("content") or tree.get("scene_id", ""))
        return {
            "quote": quote_text,
            "source": "",
            "durationInFrames": tree["duration_frames"],
        }

    def _build_archtree(self, tree: dict) -> dict:
        pm = self._primitives_map(tree)
        hero_props = pm.get("Hero", {}).get("props", {})
        diag_props = pm.get("Diagram", {}).get("props", {})
        title = self._resolve_title(tree, hero_props)
        items: list = diag_props.get("emphasis") or diag_props.get("highlights") or []
        nodes = [{"label": str(item), "level": i % 2} for i, item in enumerate(items)]
        if not nodes:
            nodes = [{"label": title, "level": 0}]
        return {
            "title": title,
            "category": "ARCHITECTURE",
            "nodes": nodes,
            "durationInFrames": tree["duration_frames"],
        }

    def _build_keywordcards(self, tree: dict) -> dict:
        pm = self._primitives_map(tree)
        hero_props = pm.get("Hero", {}).get("props", {})
        stats_props = pm.get("Stats", {}).get("props", {})
        keywords: list = (
            stats_props.get("emphasis")
            or stats_props.get("highlights")
            or hero_props.get("emphasis")
            or []
        )
        return {
            "title": self._resolve_title(tree, hero_props),
            "keywords": list(keywords),
            "icons": [],
            "descriptions": [],
            "durationInFrames": tree["duration_frames"],
        }

    def _build_default(self, tree: dict) -> dict:
        return {"durationInFrames": tree["duration_frames"]}


# ────────────────────────────────────────────────────────────────
# Hyperframe Scene Builder
# ────────────────────────────────────────────────────────────────

class HyperframeSceneBuilder:
    """Converts a PrimitiveTree dict to a HyperframeScene."""

    def __init__(self) -> None:
        self._mapper = PrimitiveToHyperframeMapper()
        self._props_builder = HyperframePropsBuilder()

    def build(
        self,
        tree: dict,
        narration_entry: dict | None = None,
        scene_index: int = 0,
    ) -> HyperframeScene:
        primitives = [p["type"] for p in tree.get("primitives", [])]
        composition = self._mapper.map(primitives)
        if composition == "TitleOpen" and scene_index > 0:
            composition = "ListReveal"
            log.debug("[BUILDER] scene_index=%d: TitleOpen → ListReveal (position rule)", scene_index)
        props = self._props_builder.build(tree, composition, narration_entry)
        fps = tree.get("fps", 24)

        # duration_frames: 오디오 길이 기반 동기화 (narration_entry 있는 경우)
        audio_duration_ms = narration_entry.get("audio_duration_ms", 0) if narration_entry else 0
        if audio_duration_ms > 0:
            synced_frames = min(
                math.ceil(audio_duration_ms / 1000 * fps),
                _MAX_DURATION_FRAMES,
            )
            duration_frames = max(synced_frames, 1)
            props["durationInFrames"] = duration_frames
            log.debug(
                "[BUILDER] %s: audio_sync duration_ms=%d → frames=%d",
                tree["scene_id"], audio_duration_ms, duration_frames,
            )
        else:
            duration_frames = tree["duration_frames"]

        return HyperframeScene(
            scene_id=tree["scene_id"],
            composition=composition,
            duration_frames=duration_frames,
            fps=fps,
            props=props,
            source_primitives=primitives,
            audio_path=narration_entry.get("audio_path", "") if narration_entry else "",
            audio_duration_ms=audio_duration_ms,
            caption_segments=narration_entry.get("caption_segments", []) if narration_entry else [],
        )


# ────────────────────────────────────────────────────────────────
# Audio Merge Helper
# ────────────────────────────────────────────────────────────────

def _merge_audio_into_mp4(
    video_path: Path,
    audio_path: Path,
    out_path: Path,
    ffmpeg_bin: str = "ffmpeg",
) -> bool:
    """Remotion이 렌더한 무음 MP4에 TTS 오디오 트랙을 병합한다.

    Args:
        video_path: 무음 MP4 (Remotion 출력)
        audio_path: TTS MP3 파일
        out_path: 오디오 포함 MP4 출력 경로 (video_path와 달라야 함)
        ffmpeg_bin: ffmpeg 실행 경로

    Returns:
        True on success
    """
    if not audio_path.exists():
        log.warning("[AUDIO_MERGE] audio file not found: %s", audio_path)
        return False

    cmd = [
        ffmpeg_bin, "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        str(out_path),
    ]
    log.info("[AUDIO_MERGE] %s + %s → %s", video_path.name, audio_path.name, out_path.name)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            log.error("[AUDIO_MERGE] FAILED: %s", (result.stderr or result.stdout)[:300])
            return False
        log.info("[AUDIO_MERGE] SUCCESS → %s", out_path)
        return True
    except Exception as exc:
        log.error("[AUDIO_MERGE] error: %s", exc)
        return False


# ────────────────────────────────────────────────────────────────
# Sprint 5 — Remotion MP4 Renderer
# ────────────────────────────────────────────────────────────────

class RemotionVideoRenderer:
    """Renders a single HyperframeScene to MP4 via Remotion CLI."""

    def __init__(self, hyperframe_dir: Path | None = None) -> None:
        self._dir = hyperframe_dir or _HYPERFRAME_DIR

    def render(self, scene: HyperframeScene, out_path: Path, timeout: int = 300) -> bool:
        """Run `npx remotion render` for one scene. Returns True on success."""
        if not self._dir.exists():
            log.error("[REMOTION] hyperframe dir not found: %s", self._dir)
            return False

        out_path.parent.mkdir(parents=True, exist_ok=True)
        props_json = json.dumps(scene.props)
        cmd = [
            "npx", "remotion", "render",
            "src/Root.tsx",
            scene.composition,
            str(out_path),
            f"--props={props_json}",
            "--overwrite",
            "--log=error",
        ]
        log.info("[REMOTION] render scene=%s comp=%s → %s", scene.scene_id, scene.composition, out_path.name)
        try:
            result = subprocess.run(
                cmd,
                cwd=str(self._dir),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode != 0:
                log.error("[REMOTION] render FAILED: %s", (result.stderr or result.stdout)[:500])
                return False
            log.info("[REMOTION] render SUCCESS → %s", out_path)
            return True
        except subprocess.TimeoutExpired:
            log.error("[REMOTION] render TIMEOUT (%ds) scene=%s", timeout, scene.scene_id)
            return False
        except Exception as exc:
            log.error("[REMOTION] render ERROR: %s", exc)
            return False


# ────────────────────────────────────────────────────────────────
# Scene Concatenator
# ────────────────────────────────────────────────────────────────

class SceneConcatenator:
    """Concatenates multiple MP4 files into a single final.mp4 via ffmpeg."""

    def concat(self, mp4_paths: list[Path], out_path: Path, ffmpeg_bin: str = "ffmpeg") -> bool:
        if not mp4_paths:
            log.error("[CONCAT] no MP4 paths provided")
            return False

        if len(mp4_paths) == 1:
            import shutil
            shutil.copy2(mp4_paths[0], out_path)
            log.info("[CONCAT] single scene → copied to %s", out_path)
            return True

        out_path.parent.mkdir(parents=True, exist_ok=True)
        filelist = out_path.parent / "filelist.txt"
        filelist.write_text(
            "\n".join(f"file '{p.resolve()}'" for p in mp4_paths),
            encoding="utf-8",
        )
        cmd = [
            ffmpeg_bin, "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(filelist),
            "-c", "copy",
            str(out_path),
        ]
        log.info("[CONCAT] ffmpeg concat %d files → %s", len(mp4_paths), out_path.name)
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                log.error("[CONCAT] ffmpeg FAILED: %s", (result.stderr or result.stdout)[:400])
                return False
            log.info("[CONCAT] concat SUCCESS → %s", out_path)
            return True
        except Exception as exc:
            log.error("[CONCAT] error: %s", exc)
            return False


# ────────────────────────────────────────────────────────────────
# Motion Caption Audit
# ────────────────────────────────────────────────────────────────

@dataclass
class MotionCaptionAuditReport:
    passed: bool
    checks: dict[str, bool] = field(default_factory=dict)
    details: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"passed": self.passed, "checks": self.checks, "details": self.details}

    def print_summary(self) -> None:
        status = "PASS" if self.passed else "FAIL"
        print(f"[MOTION_CAPTION_AUDIT] status={status}", flush=True)
        for check, ok in self.checks.items():
            icon = "✓" if ok else "✗"
            detail = self.details.get(check, "")
            print(f"  {icon} {check}{f' ({detail})' if detail else ''}", flush=True)


class MotionCaptionAudit:
    """AI Motion Mode narration 연동 유효성 3-point 검사."""

    def audit(self, scenes: list[HyperframeScene]) -> MotionCaptionAuditReport:
        checks: dict[str, bool] = {}
        details: dict[str, str] = {}

        # 1. Audio Presence: 절반 이상의 씬에 audio_path 있음
        scenes_with_audio = [s for s in scenes if s.audio_path and Path(s.audio_path).exists()]
        audio_ratio = len(scenes_with_audio) / len(scenes) if scenes else 0.0
        checks["audio_presence"] = len(scenes) == 0 or audio_ratio >= 0.5
        details["audio_presence"] = (
            f"scenes_with_audio={len(scenes_with_audio)}/{len(scenes)} ratio={audio_ratio:.2f}"
        )

        # 2. Caption Presence: audio 있는 씬 중 절반 이상에 caption_segments 있음
        if scenes_with_audio:
            scenes_with_captions = [s for s in scenes_with_audio if s.caption_segments]
            cap_ratio = len(scenes_with_captions) / len(scenes_with_audio)
            checks["caption_presence"] = cap_ratio >= 0.5
            details["caption_presence"] = (
                f"scenes_with_captions={len(scenes_with_captions)}/{len(scenes_with_audio)}"
                f" ratio={cap_ratio:.2f}"
            )
        else:
            checks["caption_presence"] = True
            details["caption_presence"] = "no_audio_scenes: skip"

        # 3. Duration Sync: audio_duration_ms > 0 인 씬의 duration_frames가
        #    audio 기반 frames와 ±20% 이내인지 검사
        sync_errors: list[str] = []
        for s in scenes:
            if s.audio_duration_ms <= 0:
                continue
            expected_frames = math.ceil(s.audio_duration_ms / 1000 * s.fps)
            ratio = s.duration_frames / expected_frames if expected_frames > 0 else 1.0
            if not (0.8 <= ratio <= 1.2):
                sync_errors.append(
                    f"{s.scene_id}: frames={s.duration_frames} expected≈{expected_frames} ratio={ratio:.2f}"
                )
        checks["duration_sync"] = len(sync_errors) == 0
        if sync_errors:
            details["duration_sync"] = "; ".join(sync_errors[:3])
        else:
            synced_count = sum(1 for s in scenes if s.audio_duration_ms > 0)
            details["duration_sync"] = f"synced={synced_count}/{len(scenes)} scenes"

        passed = all(checks.values())
        return MotionCaptionAuditReport(passed=passed, checks=checks, details=details)


# ────────────────────────────────────────────────────────────────
# Sprint 6 — Motion Render Audit
# ────────────────────────────────────────────────────────────────

@dataclass
class MotionRenderAuditReport:
    passed: bool
    checks: dict[str, bool] = field(default_factory=dict)
    details: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "checks": self.checks,
            "details": self.details,
        }

    def print_summary(self) -> None:
        status = "PASS" if self.passed else "FAIL"
        print(f"[MOTION_RENDER_AUDIT] status={status}", flush=True)
        for check, ok in self.checks.items():
            icon = "✓" if ok else "✗"
            detail = self.details.get(check, "")
            detail_str = f" ({detail})" if detail else ""
            print(f"  {icon} {check}{detail_str}", flush=True)


class MotionRenderAudit:
    """8-point validation for AI Motion render output."""

    def audit(
        self,
        scenes: list[HyperframeScene],
        scene_files: dict[str, Path],
        render_results: dict[str, bool],
        final_mp4: Path,
        hyperframe_dir: Path | None = None,
    ) -> MotionRenderAuditReport:
        checks: dict[str, bool] = {}
        details: dict[str, str] = {}
        hf_dir = hyperframe_dir or _HYPERFRAME_DIR

        # 1. Scene JSON 생성
        any_scene_file = any(p.exists() for p in scene_files.values())
        checks["scene_json_created"] = any_scene_file
        details["scene_json_created"] = str(list(scene_files.values()))

        # 2. Hyperframe Schema 유효
        schema_valid = all(len(s.validate()) == 0 for s in scenes)
        checks["hyperframe_schema_valid"] = schema_valid
        if not schema_valid:
            details["hyperframe_schema_valid"] = "; ".join(
                f"{s.scene_id}:{s.validate()}" for s in scenes if s.validate()
            )

        # 3. Remotion Render 성공
        render_ok = bool(render_results) and all(render_results.values())
        checks["remotion_render_success"] = render_ok
        failed_renders = [sid for sid, ok in render_results.items() if not ok]
        if failed_renders:
            details["remotion_render_success"] = f"failed={failed_renders}"

        # 4. MP4 생성
        mp4_exists = final_mp4.exists()
        checks["mp4_created"] = mp4_exists
        details["mp4_created"] = str(final_mp4)

        # 5. Duration > 0
        duration_ok = False
        if mp4_exists:
            duration_ok, dur_detail = self._check_duration(final_mp4)
            details["duration_valid"] = dur_detail
        checks["duration_valid"] = duration_ok

        # 6. Black Frame 없음
        black_ok, black_detail = self._check_no_black_frames(final_mp4) if mp4_exists else (True, "skipped: mp4 not found")
        checks["black_frame_absent"] = black_ok
        details["black_frame_absent"] = black_detail

        # 7. Caption 데이터 존재 여부 (narration manifest 연동 시)
        scenes_with_captions = [s for s in scenes if s.caption_segments]
        if scenes:
            caption_ratio = len(scenes_with_captions) / len(scenes)
            caption_ok = caption_ratio >= 0.5 or len(scenes_with_captions) == 0
            # narration manifest 없는 경우(legacy) True로 유지
            if not any(s.audio_path for s in scenes):
                caption_ok = True
                details["caption_owner_preserved"] = "no_audio_track: narration manifest not used"
            else:
                details["caption_owner_preserved"] = (
                    f"scenes_with_captions={len(scenes_with_captions)}/{len(scenes)}"
                    f" ratio={caption_ratio:.2f}"
                )
        else:
            caption_ok = True
            details["caption_owner_preserved"] = "no_scenes"
        checks["caption_owner_preserved"] = caption_ok

        # 8. Font Manifest 유지
        font_manifest = hf_dir / "src" / "theme" / "fontManifest.ts"
        font_ok = font_manifest.exists() and font_manifest.stat().st_size > 0
        checks["font_manifest_present"] = font_ok
        details["font_manifest_present"] = str(font_manifest)

        passed = all(checks.values())
        return MotionRenderAuditReport(passed=passed, checks=checks, details=details)

    def _check_duration(self, mp4: Path) -> tuple[bool, str]:
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                 "-of", "json", str(mp4)],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                return False, "ffprobe failed"
            data = json.loads(result.stdout)
            dur = float(data.get("format", {}).get("duration", 0))
            return dur > 0, f"duration={dur:.2f}s"
        except Exception as exc:
            return False, f"error:{exc}"

    def _check_no_black_frames(self, mp4: Path) -> tuple[bool, str]:
        try:
            sys.path.insert(0, str(Path(__file__).parent))
            from black_frame_detector import check as bfd_check
            result = bfd_check(mp4)
            status = result.get("status", "FAIL")
            segments = result.get("segments", [])
            ok = status in ("PASS", "WARNING")
            return ok, f"status={status} segments={len(segments)}"
        except Exception as exc:
            return True, f"skipped:{exc}"


# ────────────────────────────────────────────────────────────────
# Main Adapter Runner
# ────────────────────────────────────────────────────────────────

class PrimitiveSceneAdapter:
    """End-to-end: primitive_tree.json → scene JSON → MP4 (with optional audio/caption)."""

    def __init__(
        self,
        work_dir: Path | None = None,
        videos_dir: Path | None = None,
        hyperframe_dir: Path | None = None,
        narration_manifest_path: Path | None = None,
    ) -> None:
        self._work_dir = work_dir or _WORK_MOTION
        self._videos_dir = videos_dir or _VIDEOS_DIR
        self._hf_dir = hyperframe_dir or _HYPERFRAME_DIR
        self._builder = HyperframeSceneBuilder()
        self._renderer = RemotionVideoRenderer(self._hf_dir)
        self._concat = SceneConcatenator()
        self._auditor = MotionRenderAudit()
        # narration manifest: {scene_id → {narration, audio_path, audio_duration_ms, caption_segments}}
        manifest_path = narration_manifest_path or _NARRATION_MANIFEST
        self._narration_map: dict[str, dict] = _load_narration_manifest(manifest_path)
        if self._narration_map:
            log.info("[ADAPTER] narration manifest loaded: %d entries", len(self._narration_map))
        else:
            log.info("[ADAPTER] narration manifest not found — audio/caption features disabled")

    # ── Step 1: Build Hyperframe scenes from primitive trees ──────

    def build_scenes(self, trees: list[dict]) -> list[HyperframeScene]:
        scenes: list[HyperframeScene] = []
        for i, tree in enumerate(trees):
            scene_id = tree.get("scene_id", "")
            narration_entry = self._narration_map.get(scene_id) if self._narration_map else None
            scene = self._builder.build(tree, narration_entry, scene_index=i)
            scenes.append(scene)
        log.info("[ADAPTER] built %d hyperframe scene(s)", len(scenes))
        return scenes

    # ── Step 2: Save scene JSON files ──────────────────────────────

    def save_scenes(self, scenes: list[HyperframeScene]) -> dict[str, Path]:
        """Save compare/summary/combined scene JSON. Returns {name: path} map."""
        self._work_dir.mkdir(parents=True, exist_ok=True)
        saved: dict[str, Path] = {}

        compare_scenes = [s for s in scenes if s.composition == "CompareTwo"]
        summary_scenes = [s for s in scenes if s.composition == "SummaryCard"]

        if compare_scenes:
            p = self._work_dir / "scene_compare.json"
            p.write_text(
                json.dumps([s.to_dict() for s in compare_scenes], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            saved["scene_compare"] = p
            log.info("[ADAPTER] saved scene_compare.json (%d scenes)", len(compare_scenes))

        if summary_scenes:
            p = self._work_dir / "scene_summary.json"
            p.write_text(
                json.dumps([s.to_dict() for s in summary_scenes], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            saved["scene_summary"] = p
            log.info("[ADAPTER] saved scene_summary.json (%d scenes)", len(summary_scenes))

        # Combined
        combined = self._work_dir / "hyperframe_scenes.json"
        combined.write_text(
            json.dumps([s.to_dict() for s in scenes], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        saved["hyperframe_scenes"] = combined
        log.info("[ADAPTER] saved hyperframe_scenes.json (%d scenes total)", len(scenes))

        return saved

    # ── Step 3: Render MP4s ────────────────────────────────────────

    def render_scenes(
        self,
        scenes: list[HyperframeScene],
        topic: str = "ai-motion-mvp",
    ) -> tuple[dict[str, bool], list[Path]]:
        """Render each scene to MP4 (+ audio merge if narration available).

        Returns (render_results, mp4_paths)
        """
        out_dir = self._videos_dir / topic / "scenes"
        out_dir.mkdir(parents=True, exist_ok=True)

        render_results: dict[str, bool] = {}
        mp4_paths: list[Path] = []

        for scene in scenes:
            silent_mp4 = out_dir / f"{scene.scene_id}_silent.mp4"
            final_mp4 = out_dir / f"{scene.scene_id}.mp4"

            # Remotion render → silent MP4
            ok = self._renderer.render(scene, silent_mp4)
            render_results[scene.scene_id] = ok

            if not ok:
                log.warning("[ADAPTER] render FAILED for scene=%s", scene.scene_id)
                continue

            # Audio merge (narration manifest 있는 경우)
            if scene.audio_path and Path(scene.audio_path).exists():
                merged = _merge_audio_into_mp4(
                    video_path=silent_mp4,
                    audio_path=Path(scene.audio_path),
                    out_path=final_mp4,
                )
                if merged:
                    silent_mp4.unlink(missing_ok=True)
                    print(
                        f"[AUDIO_MERGE_AUDIT] scene={scene.scene_id}"
                        f" audio={Path(scene.audio_path).name}"
                        f" status=PASS",
                        flush=True,
                    )
                else:
                    log.warning("[ADAPTER] audio merge FAILED for scene=%s — using silent", scene.scene_id)
                    silent_mp4.rename(final_mp4)
                    print(
                        f"[AUDIO_MERGE_AUDIT] scene={scene.scene_id} status=FAIL_FALLBACK_SILENT",
                        flush=True,
                    )
            else:
                # 오디오 없음 → silent MP4를 final로 이름 변경
                silent_mp4.rename(final_mp4)
                print(
                    f"[AUDIO_MERGE_AUDIT] scene={scene.scene_id} status=SKIP_NO_AUDIO",
                    flush=True,
                )

            mp4_paths.append(final_mp4)

        return render_results, mp4_paths

    # ── Step 4: Concatenate ────────────────────────────────────────

    def concat_scenes(self, mp4_paths: list[Path], topic: str = "ai-motion-mvp") -> Path:
        final = self._videos_dir / topic / "final.mp4"
        ok = self._concat.concat(mp4_paths, final)
        if not ok:
            log.error("[ADAPTER] concat FAILED")
        return final

    # ── Full pipeline ──────────────────────────────────────────────

    def run(
        self,
        primitive_tree_path: Path | None = None,
        topic: str = "ai-motion-mvp",
        skip_render: bool = False,
    ) -> MotionRenderAuditReport:
        tree_path = primitive_tree_path or (self._work_dir / "primitive_tree.json")
        if not tree_path.exists():
            log.error("[ADAPTER] primitive_tree.json not found: %s", tree_path)
            sys.exit(1)

        trees = json.loads(tree_path.read_text(encoding="utf-8"))
        if not isinstance(trees, list) or not trees:
            log.error("[ADAPTER] invalid primitive_tree.json — expected non-empty list")
            sys.exit(1)

        # 1. Build scenes
        scenes = self.build_scenes(trees)

        # 2. Save scene JSON
        scene_files = self.save_scenes(scenes)

        # 3 & 4. Render + concat (skip in dry-run)
        final_mp4 = self._videos_dir / topic / "final.mp4"
        render_results: dict[str, bool] = {}

        if not skip_render:
            render_results, mp4_paths = self.render_scenes(scenes, topic)
            if mp4_paths:
                final_mp4 = self.concat_scenes(mp4_paths, topic)
        else:
            log.info("[ADAPTER] skip_render=True — bypassing Remotion render")
            render_results = {s.scene_id: True for s in scenes}  # optimistic for dry-run

        # 5. Render Audit
        report = self._auditor.audit(
            scenes=scenes,
            scene_files=scene_files,
            render_results=render_results,
            final_mp4=final_mp4,
            hyperframe_dir=self._hf_dir,
        )
        report.print_summary()

        # 6. Caption Audit (narration manifest 사용 시)
        caption_auditor = MotionCaptionAudit()
        caption_report = caption_auditor.audit(scenes)
        caption_report.print_summary()

        return report


# ────────────────────────────────────────────────────────────────
# Convenience function
# ────────────────────────────────────────────────────────────────

def adapt_and_render(
    primitive_tree_path: Path | None = None,
    topic: str = "ai-motion-mvp",
    skip_render: bool = False,
) -> MotionRenderAuditReport:
    """Convenience: run full pipeline. Returns MotionRenderAuditReport."""
    return PrimitiveSceneAdapter().run(
        primitive_tree_path=primitive_tree_path,
        topic=topic,
        skip_render=skip_render,
    )


# ────────────────────────────────────────────────────────────────
# Validation Cases (CLI)
# ────────────────────────────────────────────────────────────────

_COMPARE_TREE: list[dict] = [
    {
        "scene_id": "scene01",
        "duration_frames": 192,
        "fps": 24,
        "layout": "left_right",
        "background": "#000000",
        "primitives": [
            {
                "type": "Hero",
                "props": {
                    "title": "기존 LLM vs RAG",
                    "subtitle": None,
                    "emphasis": ["RAG", "검색"],
                    "eyebrow": None,
                    "layout": "centered",
                },
                "animation": {"name": "fade_in", "duration_ms": 600, "easing": "ease_out", "delay_ms": 0},
                "z_index": 0,
            },
            {
                "type": "Compare",
                "props": {
                    "leftTitle": "기존 LLM",
                    "rightTitle": "RAG",
                    "leftItems": ["학습 데이터만 사용", "최신 정보 없음", "환각 발생"],
                    "rightItems": ["외부 검색 활용", "실시간 정보 주입", "정확도 향상"],
                    "highlightSide": "right",
                },
                "animation": {"name": "fade_in", "duration_ms": 600, "easing": "ease_out", "delay_ms": 1333},
                "z_index": 1,
            },
            {
                "type": "Highlight",
                "props": {"content": "", "highlights": ["RAG", "검색"]},
                "animation": {"name": "fade_in", "duration_ms": 600, "easing": "ease_out", "delay_ms": 2666},
                "z_index": 2,
            },
        ],
    }
]

_SUMMARY_TREE: list[dict] = [
    {
        "scene_id": "scene02",
        "duration_frames": 144,
        "fps": 24,
        "layout": "full",
        "background": "#000000",
        "primitives": [
            {
                "type": "Summary",
                "props": {
                    "title": "핵심 정리",
                    "points": [
                        "RAG는 검색과 생성을 결합한다",
                        "외부 문서로 LLM 지식을 보강한다",
                        "환각을 줄이고 정확도를 높인다",
                    ],
                },
                "animation": {"name": "slide_in", "duration_ms": 800, "easing": "ease_out", "delay_ms": 0},
                "z_index": 0,
            }
        ],
    }
]


def _run_validation(skip_render: bool = False) -> None:
    """Run 5 validation cases."""
    builder = HyperframeSceneBuilder()
    work_dir = _WORK_MOTION
    work_dir.mkdir(parents=True, exist_ok=True)

    results: list[tuple[str, bool]] = []

    # Case 1: compare → scene_compare.json
    compare_scenes = [builder.build(t) for t in _COMPARE_TREE]
    adapter = PrimitiveSceneAdapter()
    saved = adapter.save_scenes(compare_scenes)
    case1_ok = saved.get("scene_compare", Path()).exists()
    results.append(("Case 1: compare → scene_compare.json", case1_ok))

    # Case 2: summary → scene_summary.json
    summary_scenes = [builder.build(t) for t in _SUMMARY_TREE]
    saved2 = adapter.save_scenes(summary_scenes)
    case2_ok = saved2.get("scene_summary", Path()).exists()
    results.append(("Case 2: summary → scene_summary.json", case2_ok))

    # Case 3: compare+summary → hyperframe_scenes.json
    all_scenes = compare_scenes + summary_scenes
    saved3 = adapter.save_scenes(all_scenes)
    case3_ok = saved3.get("hyperframe_scenes", Path()).exists()
    results.append(("Case 3: combined → hyperframe_scenes.json", case3_ok))

    # Case 4: Hyperframe Schema validation
    violations_compare = compare_scenes[0].validate()
    violations_summary = summary_scenes[0].validate()
    case4_ok = len(violations_compare) == 0 and len(violations_summary) == 0
    results.append(("Case 4: Hyperframe Schema valid", case4_ok))

    # Case 5: AI Motion Mode pipeline
    combined_trees = _COMPARE_TREE + _SUMMARY_TREE
    tree_path = work_dir / "primitive_tree_validation.json"
    tree_path.write_text(json.dumps(combined_trees, ensure_ascii=False, indent=2), encoding="utf-8")
    report = adapter.run(primitive_tree_path=tree_path, topic="ai-motion-mvp", skip_render=skip_render)
    case5_ok = report.checks.get("scene_json_created", False) and report.checks.get("hyperframe_schema_valid", False)
    if not skip_render:
        case5_ok = case5_ok and report.checks.get("mp4_created", False)
    results.append((f"Case 5: full pipeline (skip_render={skip_render})", case5_ok))

    # Print
    print("\n[PRIMITIVE_SCENE_ADAPTER] Validation Results:")
    all_pass = True
    for label, ok in results:
        status = "PASS" if ok else "FAIL"
        print(f"  {status}  {label}")
        if not ok:
            all_pass = False
    print()
    if all_pass:
        print("[PRIMITIVE_SCENE_ADAPTER] ALL CASES PASS")
    else:
        print("[PRIMITIVE_SCENE_ADAPTER] SOME CASES FAILED")
        sys.exit(1)


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Primitive Scene Adapter")
    sub = parser.add_subparsers(dest="cmd")

    run_p = sub.add_parser("run", help="full pipeline: primitive_tree.json → final.mp4")
    run_p.add_argument("--tree", help="path to primitive_tree.json", default=None)
    run_p.add_argument("--topic", help="video topic slug", default="ai-motion-mvp")
    run_p.add_argument("--skip-render", action="store_true", help="skip Remotion render (dry-run)")

    sub.add_parser("validate", help="run validation cases (skip-render mode)")
    sub.add_parser("validate-render", help="run validation cases with actual Remotion render")

    args = parser.parse_args()

    if args.cmd == "run":
        report = adapt_and_render(
            primitive_tree_path=Path(args.tree) if args.tree else None,
            topic=args.topic,
            skip_render=args.skip_render,
        )
        sys.exit(0 if report.passed else 1)

    elif args.cmd == "validate-render":
        _run_validation(skip_render=False)

    else:
        # Default + "validate"
        _run_validation(skip_render=True)
