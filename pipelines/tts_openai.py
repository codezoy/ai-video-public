# DEPRECATED: 2026-05-30 — 표준 경로는 synth_narration.py 사용. REMOVAL_CANDIDATE: 2026-06-30
"""S4 — TTS 음성 합성. work/scenes.json → work/audio/sceneNN.mp3."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

try:
    from cost_guard import ensure_provider_allowed
except ImportError:  # pragma: no cover - package import fallback
    from pipelines.cost_guard import ensure_provider_allowed  # type: ignore[no-redef]

try:
    from rich.console import Console
    from rich.progress import track
    _console = Console(stderr=True)
    def _log(msg: str, level: str = "info") -> None:
        color = {"info": "green", "warning": "yellow", "error": "red"}.get(level, "white")
        _console.print(f"[{color}][tts_openai][/{color}] {msg}")
    _HAS_RICH = True
except ImportError:
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO)
    def _log(msg: str, level: str = "info") -> None:  # type: ignore[misc]
        getattr(_logging, level, _logging.info)(f"[tts_openai] {msg}")
    def track(iterable, description=""):  # type: ignore[misc]
        return iterable
    _HAS_RICH = False

ROOT      = Path(os.environ.get("PROJECT_ROOT", Path(__file__).parent.parent))
WORK_DIR  = Path(os.getenv("WORK_DIR", str(ROOT / "work")))
AUDIO_DIR = WORK_DIR / "audio"

SCENES_FILE = WORK_DIR / "scenes.json"

TTS_MODEL:  str   = os.getenv("OPENAI_TTS_MODEL", "tts-1")
TTS_VOICE:  str   = os.getenv("OPENAI_TTS_VOICE", "nova")
TTS_FORMAT: str   = os.getenv("OPENAI_TTS_FORMAT", "mp3")
TTS_SPEED:  float = float(os.getenv("OPENAI_TTS_SPEED", "1.0"))
PARALLEL:   int   = int(os.getenv("PARALLEL_TTS", "1"))  # TODO(review): 현재 미구현. ThreadPool 적용 예정

_BACKOFF = (1, 2, 4)
_COST_PER_1K_CHARS_USD = 0.015
_USD_TO_KRW = 1380.0


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _audio_path(scene_id: int) -> Path:
    return AUDIO_DIR / f"scene{scene_id:02d}.mp3"


def _hash_path(scene_id: int) -> Path:
    return AUDIO_DIR / f"scene{scene_id:02d}.sha"


def _synthesize_one(scene: dict, client: object) -> bool:
    """단일 씬 합성. 스킵 시 False, 합성 시 True 반환."""
    sid: int = scene["id"]
    narration: str = scene.get("narration", "")
    if not narration:
        _log(f"scene {sid:02d}: narration 비어 있음, 스킵", "warning")
        return False

    current_hash = _sha256(narration)
    out_path  = _audio_path(sid)
    hash_path = _hash_path(sid)

    # 해시 스킵
    if out_path.exists() and hash_path.exists():
        if hash_path.read_text().strip() == current_hash:
            _log(f"scene {sid:02d}: 스킵 (해시 일치)")
            return False

    # TTS 호출 (지수 백오프 3회)
    last_exc: Exception | None = None
    for attempt, wait in enumerate(_BACKOFF, start=1):
        try:
            response = client.audio.speech.create(  # type: ignore[union-attr]
                model=TTS_MODEL,
                voice=TTS_VOICE,
                input=narration,
                response_format=TTS_FORMAT,
                speed=TTS_SPEED,
            )
            out_path.write_bytes(response.content)
            hash_path.write_text(current_hash)
            _log(f"scene {sid:02d}: 합성 완료 ({len(narration)}자 → {out_path.name})")
            return True
        except Exception as exc:
            last_exc = exc
            _log(f"scene {sid:02d}: 시도 {attempt}/3 실패 — {exc}", "warning")
            if attempt < 3:
                time.sleep(wait)

    _log(f"scene {sid:02d}: TTS 3회 모두 실패 — {last_exc}", "error")
    sys.exit(1)


def run(force: bool = False) -> None:
    ensure_provider_allowed("openai_tts", "tts")

    # 환경변수 경계 검증
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        _log("OPENAI_API_KEY 가 설정되지 않았습니다.", "error")
        sys.exit(1)

    # 입력 파일 체크 (fail-fast)
    if not SCENES_FILE.exists():
        _log(f"입력 파일 없음: {SCENES_FILE}", "error")
        sys.exit(1)

    scenes_data = json.loads(SCENES_FILE.read_text(encoding="utf-8"))
    scenes: list[dict] = scenes_data.get("scenes", [])
    voice = scenes_data.get("voice", TTS_VOICE)

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    _log(f"씬 {len(scenes)}개, voice={voice}, model={TTS_MODEL}")

    import openai  # type: ignore[import]
    client = openai.OpenAI(api_key=api_key)

    if force:
        # TODO(review): 해시 파일만 삭제, MP3 는 재합성 시 write_bytes() 로 덮어씀 — 의도적 설계
        for scene in scenes:
            _hash_path(scene["id"]).unlink(missing_ok=True)

    total_chars = 0
    synthesized = 0
    items = track(scenes, description="TTS 합성 중…") if _HAS_RICH else scenes
    for scene in items:
        total_chars += len(scene.get("narration", ""))
        if _synthesize_one(scene, client):
            synthesized += 1

    cost_usd = (total_chars / 1000) * _COST_PER_1K_CHARS_USD
    cost_krw = cost_usd * _USD_TO_KRW
    _log(
        f"완료: 합성={synthesized}개, 스킵={len(scenes)-synthesized}개 | "
        f"총 {total_chars:,}자 | 예상비용 ≈ {cost_krw:.0f}원"
    )


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tts_openai.py",
        description="S4 — work/scenes.json 의 narration 을 OpenAI TTS 로 합성하여 work/audio/sceneNN.mp3 를 생성한다.",
    )
    p.add_argument("--force", action="store_true", help="해시 일치해도 재합성")
    return p


def main() -> None:
    args = _build_parser().parse_args()
    run(force=args.force)


if __name__ == "__main__":
    main()
