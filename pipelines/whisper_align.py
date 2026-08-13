"""whisper_align.py — audio 파일에서 word-level timestamp 추출.

openai-whisper 패키지 사용. whisper.cpp subprocess 대체.
출력: List[WordTimestamp] (word, start_ms, end_ms)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
from pathlib import Path
from typing import TypedDict

log = logging.getLogger(__name__)

try:
    from cost_guard import ensure_provider_allowed
except ImportError:  # pragma: no cover - package import fallback
    from pipelines.cost_guard import ensure_provider_allowed  # type: ignore[no-redef]

PROJECT_ROOT = Path(os.environ.get("PROJECT_ROOT", Path(__file__).parent.parent))
WORK_DIR = Path(os.environ.get("WORK_DIR", PROJECT_ROOT / "work"))
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "base")
WHISPER_LANGUAGE = os.environ.get("WHISPER_LANGUAGE", "ko")
# Mirrors whisper.load_model()'s own default resolution exactly (including
# XDG_CACHE_HOME support) so cache-hit detection here never disagrees with
# where whisper itself will actually look/write.
_WHISPER_DEFAULT_CACHE_BASE = os.path.join(os.path.expanduser("~"), ".cache")
WHISPER_DOWNLOAD_ROOT = os.environ.get(
    "WHISPER_DOWNLOAD_ROOT",
    os.path.join(os.getenv("XDG_CACHE_HOME", _WHISPER_DEFAULT_CACHE_BASE), "whisper"),
)


class WordTimestamp(TypedDict):
    word: str
    start_ms: int
    end_ms: int


def _cache_path(audio_path: Path) -> Path:
    h = hashlib.sha256(audio_path.read_bytes()).hexdigest()[:12]
    return WORK_DIR / "whisper" / f"{audio_path.stem}_{h}.json"


def _model_is_cached(model_name: str) -> bool:
    """Return True if the whisper model weights are already cached AND valid.

    ``whisper.load_model()`` transparently downloads model weights over the
    network on first use when they are not cached (or re-downloads them when
    the cached file's checksum doesn't match). That download is a separate
    cost/network concern from running an already-cached model locally, so it
    must be gated by ``allow_external_web`` rather than ``allow_local_whisper``
    (see align()). This mirrors whisper's own ``_download()`` cache-validity
    check (file exists + sha256 matches the hash embedded in the model URL)
    so a corrupt/truncated cache file is correctly treated as "not cached"
    instead of silently permitting a bypass of the network guard.
    """
    try:
        import whisper  # type: ignore
    except ImportError:
        return False
    url = getattr(whisper, "_MODELS", {}).get(model_name)
    if not url:
        # Unknown model name (e.g. a local path) — let whisper handle it;
        # treat as "cached" so we don't block a legitimate local file.
        return True
    target = Path(WHISPER_DOWNLOAD_ROOT) / os.path.basename(url)
    if not target.is_file():
        return False
    expected_sha256 = url.split("/")[-2]
    try:
        actual_sha256 = hashlib.sha256(target.read_bytes()).hexdigest()
    except OSError:
        return False
    return actual_sha256 == expected_sha256


def align(audio_path: Path | str, expected_text: str = "") -> list[WordTimestamp]:
    """audio_path 를 Whisper 로 분석해 word-level timestamp 목록을 반환.

    Args:
        audio_path: MP3/WAV 파일 경로
        expected_text: 예상 대본 텍스트 (정확도 검증용, 현재는 로깅만)

    Returns:
        [{"word": str, "start_ms": int, "end_ms": int}, ...]
    """
    audio_path = Path(audio_path)
    if not audio_path.exists():
        log.error("Audio file not found: %s", audio_path)
        sys.exit(1)

    cache = _cache_path(audio_path)
    if cache.exists():
        log.info("Whisper cache hit: %s", cache)
        return json.loads(cache.read_text())

    # Local openai-whisper model execution (.venv) — not an external/paid
    # API call, so it is gated by allow_local_whisper (default true), not
    # allow_whisper_api (reserved for a hosted Whisper API, default false).
    ensure_provider_allowed("whisper_local", "whisper_align")

    try:
        import whisper  # type: ignore
    except ImportError:
        log.error("openai-whisper not installed. Run: pip install openai-whisper")
        sys.exit(1)

    if not _model_is_cached(WHISPER_MODEL):
        # First-time use of this model would download weights over the
        # network — that is an external-web concern, independent of the
        # allow_local_whisper flag which only covers already-cached,
        # offline inference.
        ensure_provider_allowed("external_web", "whisper_align_model_download")

    log.info("Loading Whisper model '%s'...", WHISPER_MODEL)
    model = whisper.load_model(WHISPER_MODEL, download_root=WHISPER_DOWNLOAD_ROOT)

    log.info("Transcribing %s ...", audio_path)
    result = model.transcribe(
        str(audio_path),
        language=WHISPER_LANGUAGE,
        word_timestamps=True,
        verbose=False,
    )

    words: list[WordTimestamp] = []
    for segment in result.get("segments", []):
        for w in segment.get("words", []):
            words.append(
                WordTimestamp(
                    word=w["word"].strip(),
                    start_ms=round(w["start"] * 1000),
                    end_ms=round(w["end"] * 1000),
                )
            )

    if not words and result.get("text"):
        # word_timestamps 미지원 모델 fallback — segment 단위로 균등 분배
        log.warning("word_timestamps unavailable, falling back to segment-level split")
        words = _segment_fallback(result["segments"])

    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(words, ensure_ascii=False, indent=2))
    log.info("Whisper aligned %d words → %s", len(words), cache)

    _log_accuracy(words, expected_text)
    return words


def _segment_fallback(segments: list[dict]) -> list[WordTimestamp]:
    """segment 텍스트를 단어 수로 균등 분배해 word timestamp 생성."""
    words: list[WordTimestamp] = []
    for seg in segments:
        text = seg.get("text", "").strip()
        tokens = text.split()
        if not tokens:
            continue
        start = seg["start"]
        end = seg["end"]
        dur = (end - start) / len(tokens)
        for i, tok in enumerate(tokens):
            words.append(
                WordTimestamp(
                    word=tok,
                    start_ms=round((start + i * dur) * 1000),
                    end_ms=round((start + (i + 1) * dur) * 1000),
                )
            )
    return words


def _log_accuracy(words: list[WordTimestamp], expected: str) -> None:
    if not expected or not words:
        return
    recognized = " ".join(w["word"] for w in words)
    recognized_tokens = set(recognized.lower().split())
    expected_tokens = set(expected.lower().split())
    if not expected_tokens:
        return
    overlap = recognized_tokens & expected_tokens
    accuracy = len(overlap) / len(expected_tokens) * 100
    log.info("Word accuracy estimate: %.1f%% (%d/%d tokens matched)", accuracy, len(overlap), len(expected_tokens))


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Extract word-level timestamps from audio.")
    parser.add_argument("audio", type=Path)
    parser.add_argument("--text", default="", help="Expected narration text for accuracy logging")
    parser.add_argument("--output", type=Path, help="Output JSON path (default: stdout)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = align(args.audio, args.text)

    if args.output:
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(f"Saved {len(result)} words → {args.output}")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
