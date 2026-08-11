"""S4.5 — 씬 나레이션을 문장별 WAV 로 합성 (다중 엔진 지원).

엔진 우선순위 (플레이북 v2.2 섹션 6.6):
  azure    → Azure Neural TTS (ko-KR-SunHiNeural, SSML)  ★기본
  openai   → OpenAI TTS-1-HD (nova)
  say      → macOS say (0원, smoke 테스트 전용)
  gtts     → Google TTS (0원, 비상용)
  recorded → 사전 녹음 MP3 직접 사용 (TTS 스킵)

라우팅 규칙:
  1. scene["narration_source"] == "recorded" → recorded 엔진 (TTS 스킵)
  2. smoke-* 토픽 → 항상 say (비용 절감)
  3. TTS_ENGINE 환경변수 명시 시 그대로 사용
  4. 자동 선택: Azure 키 존재 → azure, OpenAI 키 존재 → openai, else → say
"""

from __future__ import annotations

import argparse
import concurrent.futures as _cf
import dataclasses
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path

import requests
from dotenv import load_dotenv
load_dotenv()

try:
    from cost_guard import (
        ensure_provider_allowed,
        is_provider_allowed,
        log_blocked,
        log_provider_usage,
    )
except ImportError:  # pragma: no cover - package import fallback
    from pipelines.cost_guard import (  # type: ignore[no-redef]
        ensure_provider_allowed,
        is_provider_allowed,
        log_blocked,
        log_provider_usage,
    )

try:
    from rich.console import Console
    _console = Console(stderr=True)

    def _log(msg: str, level: str = "info") -> None:
        color = {"info": "green", "warning": "yellow", "error": "red"}.get(level, "white")
        _console.print(f"[{color}][synth_narration][/{color}] {msg}")
except ImportError:
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO)

    def _log(msg: str, level: str = "info") -> None:  # type: ignore[misc]
        getattr(_logging, level, _logging.info)(f"[synth_narration] {msg}")

# ── 환경변수 ──────────────────────────────────────────────────────────────────
_TTS_ENGINE       = os.getenv("TTS_ENGINE", "")                # azure|openai|say|gtts
_AZURE_KEY        = os.getenv("AZURE_SPEECH_KEY", "")
_AZURE_REGION     = os.getenv("AZURE_SPEECH_REGION", "koreacentral")
_AZURE_VOICE      = os.getenv("AZURE_TTS_VOICE", "ko-KR-InJoonNeural")
_OPENAI_KEY       = os.getenv("OPENAI_API_KEY", "")
_OPENAI_MODEL     = os.getenv("OPENAI_TTS_MODEL", "tts-1-hd")
_OPENAI_VOICE     = os.getenv("OPENAI_TTS_VOICE", "nova")
_TTS_GATEWAY_URL  = os.getenv("TTS_GATEWAY_URL", "http://localhost:9000").rstrip("/")

_INPUTS_DIR           = Path(os.environ.get("INPUTS_DIR", Path(__file__).parent.parent / "inputs"))
_TTS_TIMEOUT_SEC      = int(os.getenv("TTS_TIMEOUT_SEC", "180"))
_SAY_RATE_BASE        = 190   # 기본 WPM (rate=1.0 기준)
_KO_VOICE_ORDER       = ["Yuna", "Eddy", "Flo", "Sandy", "Shelley", "Reed"]
_GATEWAY_ENGINES      = {"chatterbox", "cosyvoice", "f5tts", "xtts"}
_cache_usage = threading.local()


def reset_cache_usage() -> None:
    _cache_usage.hit = False


def get_cache_usage() -> bool:
    return bool(getattr(_cache_usage, "hit", False))

# Azure 429 대응 — 동시성 제한, Retry, 호출 간 Cooldown
_AZURE_MAX_CONCURRENCY = int(os.getenv("AZURE_TTS_MAX_CONCURRENCY", "1"))
_AZURE_RETRY_MAX       = int(os.getenv("AZURE_TTS_RETRY_MAX", "5"))
_AZURE_RETRY_BASE_SEC  = float(os.getenv("AZURE_TTS_RETRY_BASE_SEC", "2"))
_AZURE_CALL_DELAY_SEC  = float(os.getenv("AZURE_TTS_CALL_DELAY_SEC", "1.0"))

_azure_semaphore: threading.Semaphore = threading.Semaphore(_AZURE_MAX_CONCURRENCY)

# Azure 씬 유형별 voice 프로파일 (플레이북 섹션 6.6 표)
_AZURE_PROFILES: dict[str, dict] = {
    "definition": {"voice": "ko-KR-InJoonNeural", "style": "general",           "rate": 1.0},
    "example":    {"voice": "ko-KR-InJoonNeural", "style": "narration-relaxed", "rate": 1.05},
    "warning":    {"voice": "ko-KR-InJoonNeural", "style": "serious",           "rate": 0.95},
    "summary":    {"voice": "ko-KR-InJoonNeural", "style": "chat",              "rate": 1.0},
    "default":    {"voice": "ko-KR-InJoonNeural", "style": "general",           "rate": 1.0},
}

# Language-specific TTS voice and locale mappings
TTS_VOICE_BY_LANGUAGE: dict[str, str] = {
    "ko": "ko-KR-InJoonNeural",
    "en": "en-US-GuyNeural",
    "zh-CN": "zh-CN-YunxiNeural",
}

_GTTS_LANG_BY_LANGUAGE: dict[str, str] = {
    "ko": "ko",
    "en": "en",
    "zh-CN": "zh-CN",
}

_AZURE_XML_LANG_BY_LANGUAGE: dict[str, str] = {
    "ko": "ko-KR",
    "en": "en-US",
    "zh-CN": "zh-CN",
}


# ── TTS Provider result dataclass ─────────────────────────────────────────────

@dataclasses.dataclass
class TTSResult:
    """TTS 합성 결과 메타데이터."""
    provider: str
    voice: str
    output_path: Path | None
    duration_sec: float = 0.0
    fallback_used: bool = False
    error_message: str = ""


# ── 엔진 선택 라우터 ──────────────────────────────────────────────────────────

def _provider_for_engine(engine: str) -> str:
    return {
        "azure": "azure_tts",
        "openai": "openai_tts",
        "gtts": "gtts",
    }.get(engine, engine)


def _select_engine(topic: str | None = None, tts_provider: str | None = None) -> str:
    """환경변수·topic·tts_provider 조건에 따라 TTS 엔진 이름을 반환한다.

    우선순위:
      1. tts_provider 명시 (API/UI 선택) → 그대로 사용
      2. smoke-* 토픽 → say (provider 미지정 smoke 테스트 전용)
      3. TTS_ENGINE 환경변수 명시 → 그대로 사용
      4. 자동 선택: Azure 키 → azure, OpenAI 키 → openai, else → say
    """
    # 1) API/UI에서 명시한 provider는 다른 엔진으로 대체하지 않는다.
    if tts_provider and tts_provider.lower() not in ("", "auto"):
        engine = tts_provider.lower()
        if engine != "say":
            ensure_provider_allowed(_provider_for_engine(engine), "tts")
        return engine
    # 2) provider 미지정 smoke 테스트만 macOS say를 사용한다.
    if topic and re.match(r"smoke[-_]", topic):
        return "say"
    # 3) 명시적 지정 (런타임 os.environ 우선)
    engine_env = os.getenv("TTS_ENGINE", "") or _TTS_ENGINE
    if engine_env:
        engine = engine_env.lower()
        if engine != "say":
            ensure_provider_allowed(_provider_for_engine(engine), "tts")
        return engine
    # 4) 자동 선택: azure → openai → say
    azure_key = os.getenv("AZURE_SPEECH_KEY", "") or _AZURE_KEY
    openai_key = os.getenv("OPENAI_API_KEY", "") or _OPENAI_KEY
    if azure_key and is_provider_allowed("azure_tts"):
        return "azure"
    if azure_key:
        log_blocked("azure_tts", "tts")
    if openai_key and is_provider_allowed("openai_tts"):
        return "openai"
    if openai_key:
        log_blocked("openai_tts", "tts")
    _log("AZURE_SPEECH_KEY / OPENAI_API_KEY 미설정 → macOS say 폴백", "warning")
    return "say"


# ── 유틸리티 ──────────────────────────────────────────────────────────────────

_SSML_ESCAPE_TABLE = str.maketrans({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "'": "&apos;",
    '"': "&quot;",
})


def _ssml_escape(text: str) -> str:
    """SSML XML 삽입 전 특수문자를 이스케이프한다."""
    return text.translate(_SSML_ESCAPE_TABLE)


def _split_sentences(text: str) -> list[str]:
    """나레이션을 문장 단위로 분할한다 (한국어 종결어미·문장 부호 기준)."""
    parts = re.split(r"(?<=[.?!다])\s+", text.strip())
    sentences: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if sentences and len(part) < 10:
            sentences[-1] += " " + part
        else:
            sentences.append(part)
    return sentences or [text.strip()]


def _wav_duration_ms(wav_path: Path) -> int:
    """WAV 파일 재생 시간(ms)을 반환한다."""
    with wave.open(str(wav_path), "r") as wf:
        return int(wf.getnframes() / wf.getframerate() * 1000)


def _aiff_to_wav(aiff_path: Path, wav_path: Path) -> None:
    """AIFF → WAV 변환 (afconvert 우선, 없으면 ffmpeg)."""
    cmd = ["afconvert", "-f", "WAVE", "-d", "LEI16@22050", str(aiff_path), str(wav_path)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=_TTS_TIMEOUT_SEC)
    if r.returncode == 0 and wav_path.exists():
        return
    cmd2 = ["ffmpeg", "-y", "-i", str(aiff_path), str(wav_path)]
    r2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=_TTS_TIMEOUT_SEC)
    if r2.returncode != 0 or not wav_path.exists():
        raise RuntimeError(f"AIFF→WAV 변환 실패: {r2.stderr[:200]}")


def _mp3_to_wav(mp3_path: Path, wav_path: Path) -> None:
    """MP3 → WAV 변환 (ffmpeg)."""
    cmd = ["ffmpeg", "-y", "-i", str(mp3_path), "-ar", "22050", "-ac", "1", str(wav_path)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=_TTS_TIMEOUT_SEC)
    if r.returncode != 0 or not wav_path.exists():
        raise RuntimeError(f"MP3→WAV 변환 실패: {r.stderr[:200]}")


def _mp3_duration_ms(mp3_path: Path) -> int:
    """ffprobe로 MP3/오디오 파일 재생 시간(ms)을 반환한다."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(mp3_path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if r.returncode == 0 and r.stdout.strip():
        try:
            return int(float(r.stdout.strip()) * 1000)
        except ValueError:
            pass
    return 0


def _concat_wavs_to_mp3(wav_paths: list[Path], out_mp3: Path) -> None:
    """여러 WAV 를 하나의 MP3 로 연결한다 (ffmpeg)."""
    if not wav_paths:
        return
    if len(wav_paths) == 1:
        cmd = ["ffmpeg", "-y", "-i", str(wav_paths[0]),
               "-c:a", "libmp3lame", "-q:a", "4", str(out_mp3)]
    else:
        inputs: list[str] = []
        for p in wav_paths:
            inputs += ["-i", str(p)]
        filt = "".join(f"[{i}:0]" for i in range(len(wav_paths)))
        filt += f"concat=n={len(wav_paths)}:v=0:a=1[out]"
        cmd = (["ffmpeg", "-y"] + inputs
               + ["-filter_complex", filt, "-map", "[out]",
                  "-c:a", "libmp3lame", "-q:a", "4", str(out_mp3)])
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=_TTS_TIMEOUT_SEC)
    if r.returncode != 0:
        raise RuntimeError(f"WAV→MP3 변환 실패: {r.stderr[:300]}")


# ── 엔진 구현 ─────────────────────────────────────────────────────────────────

def _is_azure_429(error_details: str) -> bool:
    """Azure cancellation error_details 문자열에서 429 여부를 판별한다."""
    low = error_details.lower()
    return "429" in low or "too many requests" in low or "websocket upgrade failed" in low


def _engine_azure(
    text: str,
    out_path: Path,
    voice: str | None,
    rate: float,
    scene_type: str = "default",
    language: str = "ko",
    scene_index: int = 0,
) -> Path:
    """Azure Neural TTS → WAV (429 Exponential Backoff Retry 포함).

    Args:
        text: 합성할 텍스트.
        out_path: 출력 WAV 경로.
        voice: Azure 음성 이름 (None 이면 AZURE_TTS_VOICE 사용).
        rate: 속도 배율 (1.0 = 보통).
        scene_type: 씬 유형 (definition/example/warning/summary/default).
        scene_index: 씬 번호 (429 로그용).
    """
    try:
        import azure.cognitiveservices.speech as speechsdk  # type: ignore[import]
    except ImportError:
        raise ImportError(
            "azure-cognitiveservices-speech 미설치.\n"
            "설치: pip install azure-cognitiveservices-speech"
        )

    profile = _AZURE_PROFILES.get(scene_type, _AZURE_PROFILES["default"])
    use_voice = voice or profile["voice"] or TTS_VOICE_BY_LANGUAGE.get(language, _AZURE_VOICE)
    effective_rate = rate * profile["rate"]

    # 속도를 SSML prosody 형식으로 변환 (+5%, -10% 등)
    rate_pct = int((effective_rate - 1.0) * 100)
    rate_str = f"+{rate_pct}%" if rate_pct >= 0 else f"{rate_pct}%"

    xml_lang = _AZURE_XML_LANG_BY_LANGUAGE.get(language, "ko-KR")
    ssml = (
        f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
        f'xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="{xml_lang}">'
        f'<voice name="{use_voice}">'
        f'<mstts:express-as style="{profile["style"]}">'
        f'<prosody rate="{rate_str}">{_ssml_escape(text)}</prosody>'
        f'</mstts:express-as>'
        f'</voice>'
        f'</speak>'
    )

    last_exc: Exception = RuntimeError("Azure TTS: 알 수 없는 오류")
    with _azure_semaphore:
        for attempt in range(_AZURE_RETRY_MAX + 1):
            out_path.unlink(missing_ok=True)  # 이전 시도 잔여 파일 제거

            _log(f"[tts][azure] request | scene={scene_index} attempt={attempt} text={text[:40]!r}")

            speech_config = speechsdk.SpeechConfig(
                subscription=_AZURE_KEY, region=_AZURE_REGION
            )
            speech_config.set_speech_synthesis_output_format(
                speechsdk.SpeechSynthesisOutputFormat.Riff22050Hz16BitMonoPcm
            )
            audio_config = speechsdk.audio.AudioOutputConfig(filename=str(out_path))
            synthesizer = speechsdk.SpeechSynthesizer(
                speech_config=speech_config, audio_config=audio_config
            )

            try:
                with _cf.ThreadPoolExecutor(max_workers=1) as _exe:
                    try:
                        result = _exe.submit(
                            lambda s=synthesizer: s.speak_ssml_async(ssml).get()
                        ).result(timeout=_TTS_TIMEOUT_SEC)
                    except _cf.TimeoutError:
                        out_path.unlink(missing_ok=True)
                        raise RuntimeError(f"Azure TTS timeout ({_TTS_TIMEOUT_SEC}s)")
            except RuntimeError:
                raise
            except Exception as sdk_exc:
                # SDK 자체 예외(WebSocket 등) — 429 가능성으로 retry
                error_str = str(sdk_exc)
                if _is_azure_429(error_str) and attempt < _AZURE_RETRY_MAX:
                    wait_sec = _AZURE_RETRY_BASE_SEC * (2 ** attempt)
                    _log(
                        f"[tts][azure] 429(sdk_exc) | scene={scene_index} attempt={attempt}"
                        f" error={error_str[:120]} → {wait_sec:.0f}s 대기",
                        "warning",
                    )
                    last_exc = RuntimeError(f"Azure TTS 429(sdk): {error_str[:200]}")
                    time.sleep(wait_sec)
                    continue
                _log(f"[tts][azure] fail(sdk_exc) | scene={scene_index} error={error_str[:200]}", "error")
                raise RuntimeError(f"Azure TTS SDK 예외: {error_str}") from sdk_exc

            if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                _log(f"[tts][azure] success | scene={scene_index} attempt={attempt}")
                if _AZURE_CALL_DELAY_SEC > 0:
                    time.sleep(_AZURE_CALL_DELAY_SEC)
                return out_path

            # 실패 — 0 byte 파일 제거
            out_path.unlink(missing_ok=True)
            cancellation = result.cancellation_details
            error_msg = cancellation.error_details or str(cancellation.reason)

            if _is_azure_429(error_msg) and attempt < _AZURE_RETRY_MAX:
                wait_sec = _AZURE_RETRY_BASE_SEC * (2 ** attempt)
                _log(
                    f"[tts][azure] 429 | scene={scene_index} retry={attempt + 1}/{_AZURE_RETRY_MAX}"
                    f" voice={use_voice} error={error_msg[:120]} → {wait_sec:.0f}s 대기",
                    "warning",
                )
                last_exc = RuntimeError(f"Azure TTS 429: {error_msg[:200]}")
                time.sleep(wait_sec)
                continue

            _log(f"[tts][azure] fail | scene={scene_index} reason={cancellation.reason} error={error_msg[:120]}", "error")
            raise RuntimeError(
                f"Azure TTS 실패: {cancellation.reason} — {error_msg}"
            )

    raise last_exc


def _engine_openai(
    text: str,
    out_path: Path,
    voice: str | None,
    rate: float,
) -> Path:
    """OpenAI TTS-1-HD → WAV."""
    try:
        from openai import OpenAI  # type: ignore[import]
    except ImportError:
        raise ImportError("openai 미설치. 설치: pip install openai")

    client = OpenAI(api_key=_OPENAI_KEY)
    use_voice = voice or _OPENAI_VOICE

    # OpenAI TTS 는 MP3 로 출력 → WAV 변환
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp_mp3 = Path(tmp.name)

    def _do_openai() -> None:
        response = client.audio.speech.create(
            model=_OPENAI_MODEL,
            voice=use_voice,    # type: ignore[arg-type]
            input=text,
            speed=round(rate, 2),
        )
        response.stream_to_file(str(tmp_mp3))

    with _cf.ThreadPoolExecutor(max_workers=1) as _exe:
        try:
            _exe.submit(_do_openai).result(timeout=_TTS_TIMEOUT_SEC)
        except _cf.TimeoutError:
            tmp_mp3.unlink(missing_ok=True)
            raise RuntimeError(f"OpenAI TTS timeout ({_TTS_TIMEOUT_SEC}s)")

    _mp3_to_wav(tmp_mp3, out_path)
    tmp_mp3.unlink(missing_ok=True)
    return out_path


def _engine_say(
    text: str,
    out_path: Path,
    voice: str | None,
    rate: float,
) -> Path:
    """macOS say → WAV."""
    # 음성 선택
    if voice is None:
        result = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, timeout=10)
        available = result.stdout
        voice = next((v for v in _KO_VOICE_ORDER if v in available), "Yuna")

    wpm = max(80, int(_SAY_RATE_BASE * rate))

    aiff_path = out_path.with_suffix(".aiff")
    cmd = ["say", "-v", voice, "-r", str(wpm), "-o", str(aiff_path), text]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=_TTS_TIMEOUT_SEC)
    if r.returncode != 0:
        raise RuntimeError(f"say 실패: {r.stderr[:200]}")
    if not aiff_path.exists():
        raise RuntimeError(f"say 출력 파일 없음: {aiff_path}")

    _aiff_to_wav(aiff_path, out_path)
    aiff_path.unlink(missing_ok=True)
    return out_path


def _engine_gtts(
    text: str,
    out_path: Path,
    voice: str | None,  # gTTS 는 voice 개념 없음
    rate: float,        # gTTS 는 속도 미지원 (slow=False 고정)
    language: str = "ko",
) -> Path:
    """Google TTS (gTTS) → WAV (비상 폴백)."""
    try:
        from gtts import gTTS  # type: ignore[import]
    except ImportError:
        raise ImportError("gtts 미설치. 설치: pip install gtts")

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp_mp3 = Path(tmp.name)

    gtts_lang = _GTTS_LANG_BY_LANGUAGE.get(language, "ko")
    tts = gTTS(text=text, lang=gtts_lang, slow=False)
    tts.save(str(tmp_mp3))
    _mp3_to_wav(tmp_mp3, out_path)
    tmp_mp3.unlink(missing_ok=True)
    return out_path


def _engine_kokoro(
    text: str,
    out_path: Path,
    voice: str | None,
    rate: float,
    language: str = "ko",
    azure_fallback: bool = True,
    scene_type: str = "default",
    scene_index: int = 0,
) -> Path:
    """Kokoro 로컬 TTS (kokoro-onnx) → WAV (experimental).

    kokoro_onnx 미설치 또는 모델 파일 없을 시 azure_fallback=True이면 Azure로 자동 폴백한다.
    """
    try:
        import kokoro_onnx  # type: ignore[import]
        import soundfile as _sf  # type: ignore[import]
    except ImportError:
        _log("kokoro_onnx 미설치 (pip install kokoro-onnx) → Azure 폴백", "warning")
        if azure_fallback:
            return _engine_azure(text, out_path, voice, rate, scene_type, language, scene_index)
        raise ImportError("kokoro_onnx 미설치. 설치: pip install kokoro-onnx")

    project_root = Path(os.getenv("PROJECT_ROOT", Path(__file__).parent.parent))
    model_path = os.getenv("KOKORO_MODEL_PATH", str(project_root / "models/kokoro-onnx/kokoro-v1.0.int8.onnx"))
    voices_path = os.getenv("KOKORO_VOICES_PATH", str(project_root / "models/kokoro-onnx/voices-v1.0.bin"))

    if not Path(model_path).exists() or not Path(voices_path).exists():
        _log(f"Kokoro 모델 파일 없음: {model_path}", "warning")
        if azure_fallback:
            return _engine_azure(text, out_path, voice, rate, scene_type, language, scene_index)
        raise FileNotFoundError(f"Kokoro 모델 없음: {model_path}")

    kokoro_voice = voice or os.getenv("KOKORO_VOICE", "af_heart")
    # kokoro-onnx lang codes: "ko", "en-us", "cmn" (zh-CN)
    _LANG_MAP = {"zh": "cmn", "zh-cn": "cmn", "zh-CN": "cmn", "en": "en-us"}
    raw_lang = os.getenv("KOKORO_LANG", language)
    kokoro_lang = _LANG_MAP.get(raw_lang, _LANG_MAP.get(raw_lang.lower(), raw_lang))

    try:
        k = kokoro_onnx.Kokoro(model_path, voices_path)
        samples, sample_rate = k.create(text, voice=kokoro_voice, speed=float(rate), lang=kokoro_lang)
        wav_path = out_path.with_suffix(".wav")
        _sf.write(str(wav_path), samples, sample_rate)
        if not wav_path.exists():
            raise RuntimeError("Kokoro WAV 출력 없음")
        if out_path.suffix != ".wav":
            wav_path.rename(out_path)
        _log(f"Kokoro 합성 완료: voice={kokoro_voice} lang={kokoro_lang} → {out_path.name}")
        return out_path
    except Exception as exc:
        _log(f"Kokoro 합성 실패: {exc}", "warning")
        if azure_fallback:
            _log("Azure 폴백으로 전환", "warning")
            return _engine_azure(text, out_path, voice, rate, scene_type, language, scene_index)
        raise


def _engine_gateway(
    provider: str,
    text: str,
    out_path: Path,
    voice: str | None,
    rate: float,
    language: str,
) -> Path:
    """Synthesize through tts-lab and copy its real WAV output into the run."""
    extra: dict[str, str] = {}
    if voice == "clone":
        prefix = provider.upper().replace("-", "_")
        reference_audio = os.getenv(f"{prefix}_REFERENCE_AUDIO") or os.getenv("TTS_REFERENCE_AUDIO")
        reference_text = os.getenv(f"{prefix}_REFERENCE_TEXT") or os.getenv("TTS_REFERENCE_TEXT")
        if reference_audio:
            extra["reference_audio"] = reference_audio
        if reference_text:
            extra["reference_text"] = reference_text

    response = requests.post(
        f"{_TTS_GATEWAY_URL}/tts/{provider}",
        json={
            "text": text,
            "language": language,
            "voice": voice,
            "speed": rate,
            "output_format": "wav",
            "extra": extra,
        },
        timeout=_TTS_TIMEOUT_SEC,
    )
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"{provider} returned invalid JSON (HTTP {response.status_code})") from exc
    if response.status_code != 200 or not payload.get("ok"):
        message = payload.get("message") or payload.get("detail") or f"HTTP {response.status_code}"
        raise RuntimeError(f"{provider} synthesis failed: {message}")
    source = Path(payload.get("output_path") or "")
    if not source.is_file():
        raise RuntimeError(f"{provider} synthesis returned a missing output: {source}")
    shutil.copy2(source, out_path)
    return out_path


# ── Public API ────────────────────────────────────────────────────────────────

def synth_sentence(
    text: str,
    out_path: Path,
    voice: str | None = None,
    rate: float = 1.0,
    topic: str | None = None,
    scene_type: str = "default",
    language: str = "ko",
    scene_index: int = 0,
    tts_provider: str | None = None,
) -> Path:
    """단일 문장 → WAV. 엔진은 라우터가 선택.

    Args:
        text: 합성할 텍스트.
        out_path: 출력 WAV 경로.
        voice: 음성 이름 (None 이면 엔진 기본값).
        rate: 속도 배율 (1.0 = 보통).
        topic: 프로젝트 슬러그 (smoke-* 판별용).
        scene_type: 씬 유형 (Azure 프로파일 선택용).
        tts_provider: API/UI에서 전달된 provider 명시.

    Returns:
        생성된 WAV 경로.
    """
    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    engine = _select_engine(topic, tts_provider)

    # ── TTS Cache (SHA256 키 기반) ─────────────────────────────────────────────
    _cache_key = hashlib.sha256(
        f"{engine}|{voice or ''}|{language}|{text}".encode("utf-8")
    ).hexdigest()
    _project_root = Path(os.getenv("PROJECT_ROOT", Path(__file__).parent.parent))
    _cache_dir = _project_root / "work" / "tts_cache"
    _cache_file = _cache_dir / f"{_cache_key}.wav"
    if _cache_file.exists():
        shutil.copy2(_cache_file, out_path)
        _cache_usage.hit = True
        _log(f"[TTS Cache HIT] {_cache_key[:12]}… → {out_path.name}")
        return out_path

    if engine != "say":
        provider = _provider_for_engine(engine)
        log_provider_usage("tts", provider, is_provider_allowed(provider))
    _log(f"엔진={engine} | {text[:50]}...")

    if engine == "azure":
        result = _engine_azure(text, out_path, voice, rate, scene_type, language, scene_index)
    elif engine == "openai":
        result = _engine_openai(text, out_path, voice, rate)
    elif engine == "gtts":
        result = _engine_gtts(text, out_path, voice, rate, language)
    elif engine == "kokoro":
        result = _engine_kokoro(text, out_path, voice, rate, language, azure_fallback=True, scene_type=scene_type, scene_index=scene_index)
    elif engine in _GATEWAY_ENGINES:
        result = _engine_gateway(engine, text, out_path, voice, rate, language)
    elif engine == "say":
        result = _engine_say(text, out_path, voice, rate)
    else:
        raise ValueError(f"Unsupported TTS engine: {engine}")

    # Cache the generated WAV for future reuse
    if result and result.exists() and engine not in ("say",):
        try:
            _cache_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(result, _cache_file)
        except Exception as _cache_exc:
            _log(f"[TTS Cache WRITE] 실패 (무시): {_cache_exc}", "warning")

    return result


def synth_narration(
    scene: dict,
    out_dir: Path,
    voice: str | None = None,
    rate: float = 1.0,
    topic: str | None = None,
    language: str = "ko",
    tts_provider: str | None = None,
) -> list[Path]:
    """씬 나레이션을 문장별 WAV 로 합성하고 bullet appear_at_ms 를 자동 갱신한다.

    Args:
        scene: 씬 dict (id, narration, bullets 포함).
        out_dir: 문장별 WAV 저장 디렉토리.
        voice: 음성 이름 (None 이면 엔진 기본값).
        rate: 속도 배율 (1.0 = 보통).
        topic: 프로젝트 슬러그 (엔진 자동 선택용).
        tts_provider: API/UI에서 전달된 provider 명시 (azure|kokoro|auto).

    Returns:
        문장별 WAV 경로 리스트.
    """
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    scene_id = scene.get("id", 0)
    narration = scene.get("narration", "").strip()

    if not narration:
        _log(f"씬 {scene_id}: 나레이션 없음, 스킵", "warning")
        return []

    engine = _select_engine(topic, tts_provider)
    sentences = _split_sentences(narration)
    _log(
        f"씬 {scene_id}: {len(sentences)}개 문장 합성 "
        f"(engine={engine}, voice={voice or 'default'}, rate={rate})"
    )

    wav_paths: list[Path] = []
    cumulative_ms = 0

    for i, sentence in enumerate(sentences):
        wav_path = out_dir / f"scene{scene_id:02d}_s{i:02d}.wav"

        synth_sentence(sentence, wav_path, voice=voice, rate=rate, topic=topic, language=language, scene_index=scene_id, tts_provider=tts_provider)

        duration_ms = _wav_duration_ms(wav_path)

        # sentence_idx 매칭 불릿의 appear_at_ms 갱신
        for bullet in scene.get("bullets", []):
            if isinstance(bullet, dict) and bullet.get("sentence_idx") == i:
                bullet["appear_at_ms"] = cumulative_ms

        cumulative_ms += duration_ms
        wav_paths.append(wav_path)
        _log(f"  문장 {i}: {duration_ms}ms | {sentence[:40]}...")

    # 실제 오디오 길이를 scene dict에 저장 (Audio Driven Architecture v2)
    scene["audio_duration_ms"] = cumulative_ms
    scene["audio_duration_sec"] = round(cumulative_ms / 1000, 3)
    _log(f"씬 {scene_id}: audio_duration={cumulative_ms}ms ({scene['audio_duration_sec']}s)")

    return wav_paths


# ── 내부 헬퍼 (run_pipeline.py 용) ───────────────────────────────────────────

def _engine_recorded(
    scene: dict,
    audio_dir: Path,
    topic: str | None = None,
) -> Path | None:
    """사전 녹음 MP3 를 그대로 복사한다 (TTS 스킵).

    탐색 순서:
      1. scene["audio_path"] 명시 → 직접 사용
      2. inputs/audio/recorded_{topic}_scene{id}.mp3
      3. inputs/audio/recorded_{topic}.mp3 (전체 오디오, 씬 단위 분리 미지원)
    """
    scene_id = scene.get("id", 0)
    out_mp3 = audio_dir / f"scene{scene_id:02d}.mp3"

    # 1) scene["audio_path"] 명시
    explicit = scene.get("audio_path")
    if explicit:
        src = Path(explicit)
        if src.exists():
            shutil.copy2(src, out_mp3)
            _log(f"씬 {scene_id}: recorded → {src} 복사")
            return out_mp3
        _log(f"씬 {scene_id}: audio_path={explicit} 파일 없음", "warning")

    # 2) inputs/audio/recorded_{topic}_scene{scene_id:02d}.mp3
    if topic:
        candidate = _INPUTS_DIR / "audio" / f"recorded_{topic}_scene{scene_id:02d}.mp3"
        if candidate.exists():
            shutil.copy2(candidate, out_mp3)
            _log(f"씬 {scene_id}: recorded → {candidate} 복사")
            return out_mp3

        # 3) 전체 오디오 (씬 단위 분리 미지원, 경고)
        whole = _INPUTS_DIR / "audio" / f"recorded_{topic}.mp3"
        if whole.exists():
            _log(
                f"씬 {scene_id}: 전체 오디오({whole}) 발견 — 씬 단위 분리는 미지원. "
                "inputs/audio/recorded_{topic}_scene{id:02d}.mp3 형식 권장",
                "warning",
            )

    _log(f"씬 {scene_id}: narration_source=recorded 이지만 파일 없음 → TTS 폴백", "warning")
    return None


def synth_scene_to_mp3(
    scene: dict,
    sentence_wav_dir: Path,
    audio_dir: Path,
    voice: str | None = None,
    rate: float = 1.0,
    topic: str | None = None,
    language: str = "ko",
    tts_provider: str | None = None,
    tts_voice: str | None = None,
) -> Path:
    """씬 나레이션을 MP3 로 완성한다. compose_video.py 용.

    narration_source="recorded" 이면 사전 녹음 파일을 직접 사용한다.
    그 외 1) synth_narration 으로 문장별 WAV 생성 + appear_at_ms 갱신
          2) WAV 를 하나의 MP3 로 연결
    """
    audio_dir = audio_dir.resolve()
    audio_dir.mkdir(parents=True, exist_ok=True)

    scene_id = scene.get("id", 0)
    out_mp3 = audio_dir / f"scene{scene_id:02d}.mp3"

    # recorded 소스 처리
    if scene.get("narration_source") == "recorded":
        result = _engine_recorded(scene, audio_dir, topic)
        if result:
            dur_ms = _mp3_duration_ms(result)
            scene["audio_duration_ms"] = dur_ms
            scene["audio_duration_sec"] = round(dur_ms / 1000, 3)
            _log(f"씬 {scene_id}: recorded audio_duration={dur_ms}ms")
            return result
        # 파일 없으면 TTS 폴백 (아래로 계속)

    if out_mp3.exists() and out_mp3.stat().st_size > 0:
        _log(f"씬 {scene_id}: MP3 이미 존재 ({out_mp3.name}, {out_mp3.stat().st_size}B) → 스킵")
        return out_mp3

    effective_voice = tts_voice or voice
    wav_paths = synth_narration(scene, sentence_wav_dir, effective_voice, rate, topic, language, tts_provider)

    if not wav_paths:
        _log(f"씬 {scene_id}: WAV 없음 → MP3 생성 스킵", "warning")
        scene.setdefault("audio_duration_ms", 0)
        scene.setdefault("audio_duration_sec", 0.0)
        return out_mp3

    _concat_wavs_to_mp3(wav_paths, out_mp3)
    try:
        import audio_silence_guard as _asg
        _asg.trim_silence(out_mp3)
    except Exception as _sg_exc:
        _log(f"씬 {scene_id} silence guard 실패 (무시): {_sg_exc}", "warning")
    _log(f"씬 {scene_id} MP3 완료: {out_mp3}")
    return out_mp3


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(
        prog="synth_narration.py",
        description="씬 나레이션을 문장별 WAV 합성 (다중 엔진).",
    )
    p.add_argument("--scene-json", required=True,
                   help="씬 dict JSON 문자열 또는 파일 경로")
    p.add_argument("--out-dir", required=True,
                   help="문장별 WAV 저장 디렉토리")
    p.add_argument("--audio-dir",
                   help="합성 MP3 저장 디렉토리 (지정 시 MP3 생성)")
    p.add_argument("--voice", default=None, help="음성 이름 (기본: 엔진 기본값)")
    p.add_argument("--rate", type=float, default=1.0, help="속도 배율 (기본: 1.0)")
    p.add_argument("--topic", default=None, help="프로젝트 슬러그 (smoke-* 판별용)")
    p.add_argument("--engine", default=None,
                   help="엔진 강제 지정 (azure|openai|say|gtts)")
    args = p.parse_args()

    if args.engine:
        os.environ["TTS_ENGINE"] = args.engine

    scene_arg = args.scene_json
    if Path(scene_arg).exists():
        scene = json.loads(Path(scene_arg).read_text(encoding="utf-8"))
    else:
        scene = json.loads(scene_arg)

    out_dir = Path(args.out_dir)

    if args.audio_dir:
        mp3 = synth_scene_to_mp3(
            scene, out_dir, Path(args.audio_dir), args.voice, args.rate, args.topic
        )
        print(f"MP3: {mp3}")
    else:
        wavs = synth_narration(scene, out_dir, args.voice, args.rate, args.topic)
        for w in wavs:
            print(f"WAV: {w}")


if __name__ == "__main__":
    main()
