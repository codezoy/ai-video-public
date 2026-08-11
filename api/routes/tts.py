"""TTS provider status, gateway proxy, and verification endpoints."""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from api.services.tts_settings import load_tts_settings, save_tts_settings

router = APIRouter(prefix="/tts", tags=["TTS"])

_PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", Path(__file__).parent.parent.parent))
load_dotenv(_PROJECT_ROOT / ".env", override=False)
_GATEWAY_URL = os.getenv("TTS_GATEWAY_URL", "http://localhost:9000")
_GATEWAY_TIMEOUT = float(os.getenv("TTS_GATEWAY_TIMEOUT", "3.0"))
_AZURE_CATALOG_TTL = float(os.getenv("AZURE_VOICE_CACHE_SEC", "300"))
_AZURE_CATALOG_CACHE: dict = {"expires_at": 0.0, "voices": None}
_AZURE_CATALOG_LOCK = threading.Lock()

# Gateway-managed local providers (all four kept for health-check purposes)
_GATEWAY_PROVIDERS = ["chatterbox", "cosyvoice", "f5tts", "xtts"]
# Production providers exposed to ai-video users
_PRODUCTION_GATEWAY_PROVIDERS = {"chatterbox"}
_GATEWAY_PROVIDER_META = {
    "chatterbox": {"name": "Chatterbox", "port": 9001},
    "cosyvoice":  {"name": "CosyVoice",  "port": 9002},
    "f5tts":      {"name": "F5-TTS",     "port": 9003},
    "xtts":       {"name": "XTTS",       "port": 9004},
}

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _azure_configured() -> bool:
    key = os.getenv("AZURE_SPEECH_KEY") or os.getenv("AZURE_TTS_KEY")
    region = os.getenv("AZURE_SPEECH_REGION") or os.getenv("AZURE_TTS_REGION")
    return bool(key and region)


def _fetch_azure_catalog() -> list[dict]:
    if not _azure_configured():
        return []
    with _AZURE_CATALOG_LOCK:
        cached = _AZURE_CATALOG_CACHE.get("voices")
        if cached is not None and time.monotonic() < _AZURE_CATALOG_CACHE["expires_at"]:
            return cached
        key = os.getenv("AZURE_SPEECH_KEY") or os.getenv("AZURE_TTS_KEY", "")
        region = os.getenv("AZURE_SPEECH_REGION") or os.getenv("AZURE_TTS_REGION", "")
        try:
            response = httpx.get(
                f"https://{region}.tts.speech.microsoft.com/cognitiveservices/voices/list",
                headers={"Ocp-Apim-Subscription-Key": key},
                timeout=20.0,
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Azure voice API is unreachable: {exc}") from exc
        if response.status_code == 429:
            raise HTTPException(status_code=503, detail="Azure voice catalogue unavailable: quota exceeded (HTTP 429).")
        if response.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Azure voice API request rejected (HTTP {response.status_code}).")
        voices = response.json()
        _AZURE_CATALOG_CACHE.update(voices=voices, expires_at=time.monotonic() + _AZURE_CATALOG_TTL)
        return voices


def _azure_health() -> tuple[bool, bool, Optional[str]]:
    """Check the real Azure voices endpoint without exposing credentials."""
    if not _azure_configured():
        return False, False, "AZURE_SPEECH_KEY or AZURE_SPEECH_REGION is not configured."
    try:
        _fetch_azure_catalog()
        return True, True, None
    except HTTPException as exc:
        return exc.status_code != 502, False, str(exc.detail)


def _gateway_online() -> bool:
    try:
        r = httpx.get(f"{_GATEWAY_URL}/health", timeout=_GATEWAY_TIMEOUT)
        return r.status_code == 200
    except Exception:
        return False


def _gateway_provider_health(provider_id: str) -> Optional[dict]:
    """Return the provider health payload, or None when it is unreachable."""
    try:
        r = httpx.get(
            f"{_GATEWAY_URL}/providers/{provider_id}/health",
            timeout=_GATEWAY_TIMEOUT,
        )
        if r.status_code == 200:
            data = r.json()
            if data.get("status") in ("ok", "online", "healthy"):
                return data
    except Exception:
        pass
    return None


def _gateway_voices(provider_id: str) -> list[dict]:
    """Proxy the provider-owned voice/capability list without inventing fallback data."""
    try:
        r = httpx.get(
            f"{_GATEWAY_URL}/providers/{provider_id}/voices",
            timeout=_GATEWAY_TIMEOUT,
        )
        if r.status_code == 200:
            data = r.json()
            if "voices" in data:
                return data["voices"]
            message = data.get("message") or data.get("detail") or "invalid voice response"
            raise HTTPException(status_code=502, detail=f"{provider_id}: {message}")
        raise HTTPException(status_code=502, detail=f"{provider_id} voice API returned HTTP {r.status_code}")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"{provider_id} voice API is unreachable: {exc}") from exc


def _chatterbox_voices() -> list[dict]:
    """Static Chatterbox voice list — no gateway call required."""
    return [
        {
            "id": "chatterbox-default",
            "name": "Default Voice",
            "language": "multi",
            "kind": "voice",
            "status_label": "ready",
            "uses_generate_language": True,
            "clone_supported": False,
            "reference_required": False,
            "meta": {"note": "Generates speech in the language selected on the Generate screen."},
        },
        {
            "id": "chatterbox-clone",
            "name": "Voice Clone",
            "language": "multi",
            "kind": "capability",
            "status_label": "coming_soon",
            "uses_generate_language": True,
            "clone_supported": True,
            "reference_required": True,
            "meta": {"note": "Upload a reference audio to clone a voice. Coming soon."},
        },
    ]


def _azure_voices() -> list[dict]:
    """Fetch the live Azure REST catalogue; never substitute a static voice list."""
    if not _azure_configured():
        return []

    try:
        return [
            {
                "id": voice["ShortName"],
                "name": voice.get("LocalName") or voice["ShortName"],
                "language": voice.get("Locale"),
                "gender": (voice.get("Gender") or "").lower() or None,
                "kind": "voice",
                "status_label": "ready",
                "uses_generate_language": False,
                "meta": {
                    "styles": voice.get("StyleList", []),
                    "voice_type": voice.get("VoiceType"),
                    "status": voice.get("Status"),
                },
            }
            for voice in _fetch_azure_catalog()
            if voice.get("ShortName")
        ]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Azure voice catalogue request failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Legacy internal-provider status helpers (kept for /verify endpoint)
# ---------------------------------------------------------------------------

_KOKORO_MODEL = os.getenv("KOKORO_MODEL_PATH", str(_PROJECT_ROOT / "models/kokoro-onnx/kokoro-v1.0.int8.onnx"))
_KOKORO_VOICES_PATH = os.getenv("KOKORO_VOICES_PATH", str(_PROJECT_ROOT / "models/kokoro-onnx/voices-v1.0.bin"))


def _kokoro_available() -> bool:
    try:
        import kokoro_onnx  # noqa: F401
    except ImportError:
        return False
    return Path(_KOKORO_MODEL).exists() and Path(_KOKORO_VOICES_PATH).exists()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ProviderEntry(BaseModel):
    id: str
    name: str
    type: str          # "cloud" | "local-gateway"
    status: str        # "configured" | "not_configured"
    configured: bool
    reachable: bool
    operational: bool = False
    languages: list[str] = Field(default_factory=list)
    source: str        # "internal" | "tts-gateway"
    port: Optional[int] = None
    detail: Optional[str] = None
    deprecated: bool = False


class ProvidersResponse(BaseModel):
    providers: list[ProviderEntry]
    gateway_online: bool


class VoiceEntry(BaseModel):
    id: str
    name: str
    language: Optional[str] = None
    gender: Optional[str] = None
    clone_supported: bool = False
    reference_required: bool = False
    kind: str = "voice"
    status_label: str = "ready"
    uses_generate_language: bool = False
    meta: Optional[dict] = None


class VoicesResponse(BaseModel):
    provider: str
    voices: list[VoiceEntry]


class TTSSettingsRequest(BaseModel):
    default_provider: str
    default_voices: dict[str, str] = Field(default_factory=dict)


class TTSSettingsResponse(TTSSettingsRequest):
    system_fallback_provider: str


class VerifyRequest(BaseModel):
    text: str = "안녕하세요. TTS 검증 테스트입니다."
    language: str = "ko"
    provider: str = "azure"
    voice: Optional[str] = None
    speed: float = 1.0


class VerifyResponse(BaseModel):
    status: str
    provider_used: str
    fallback_used: bool
    requested_language: str
    resolved_language_id: str
    model_class: str
    voice: str
    device: str
    file_path: Optional[str] = None
    duration_s: Optional[float] = None
    synthesis_time_s: Optional[float] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/settings", response_model=TTSSettingsResponse)
def get_settings() -> TTSSettingsResponse:
    return TTSSettingsResponse(**load_tts_settings())


@router.put("/settings", response_model=TTSSettingsResponse)
def put_settings(req: TTSSettingsRequest) -> TTSSettingsResponse:
    try:
        return TTSSettingsResponse(**save_tts_settings(req.default_provider, req.default_voices))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@router.get("/providers", response_model=ProvidersResponse)
def get_providers() -> ProvidersResponse:
    """Return the list of TTS providers available to this project."""
    gateway_up = _gateway_online()

    providers: list[ProviderEntry] = []

    # Azure (always listed — internal fallback)
    azure_configured = _azure_configured()
    azure_reachable, azure_operational, azure_detail = _azure_health()
    providers.append(ProviderEntry(
        id="azure",
        name="Azure Neural Voice",
        type="cloud",
        status="configured" if azure_configured else "not_configured",
        configured=azure_configured,
        reachable=azure_reachable,
        operational=azure_operational,
        detail=azure_detail,
        source="internal",
    ))

    # Gateway-managed local providers
    for pid in _GATEWAY_PROVIDERS:
        meta = _GATEWAY_PROVIDER_META[pid]
        is_research = pid not in _PRODUCTION_GATEWAY_PROVIDERS
        health = _gateway_provider_health(pid) if gateway_up else None
        reachable = health is not None
        configured = bool(reachable and health.get("synthesis_ready", False))

        providers.append(ProviderEntry(
            id=pid,
            name=meta["name"],
            type="local-gateway",
            status="configured" if configured else "not_configured",
            configured=configured,
            reachable=reachable,
            operational=configured,
            languages=list(health.get("language_support", [])) if health else [],
            source="tts-gateway",
            port=meta["port"],
            detail=(health.get("reason") or health.get("note")) if health else "Provider service is unreachable.",
            deprecated=is_research,
        ))

    # Kokoro: deprecated — kept for DB compatibility, hidden from UI
    providers.append(ProviderEntry(
        id="kokoro",
        name="Kokoro Local (Deprecated)",
        type="local",
        status="not_configured",
        configured=False,
        reachable=False,
        source="internal",
        deprecated=True,
    ))

    return ProvidersResponse(providers=providers, gateway_online=gateway_up)


@router.get("/providers/{provider_id}/voices", response_model=VoicesResponse)
def get_voices(provider_id: str) -> VoicesResponse:
    """Return voice list for a given provider."""
    if provider_id == "azure":
        voices = [VoiceEntry(**v) for v in _azure_voices()]
        return VoicesResponse(provider="azure", voices=voices)

    if provider_id in _GATEWAY_PROVIDERS:
        raw = _chatterbox_voices() if provider_id == "chatterbox" else _gateway_voices(provider_id)
        voices = [VoiceEntry(**v) for v in raw]
        return VoicesResponse(provider=provider_id, voices=voices)

    if provider_id == "kokoro":
        raise HTTPException(status_code=410, detail="Kokoro is deprecated. Use Azure or a gateway provider.")

    raise HTTPException(status_code=404, detail=f"Unknown provider: {provider_id}")


@router.get("/voices", response_model=VoicesResponse)
def get_voices_by_query(provider: str = "azure") -> VoicesResponse:
    """Alias: GET /tts/voices?provider=<id>"""
    return get_voices(provider)


@router.get("/status")
def get_status() -> dict:
    """Quick summary: azure configured + gateway reachable."""
    return {
        "azure_configured": _azure_configured(),
        "gateway_url": _GATEWAY_URL,
        "gateway_online": _gateway_online(),
    }


# ---------------------------------------------------------------------------
# Legacy /verify endpoint (debugging only, not used by UI)
# ---------------------------------------------------------------------------

@router.post("/verify", response_model=VerifyResponse)
def verify_tts(req: VerifyRequest) -> VerifyResponse:
    """Synthesize a test utterance and return debug metadata."""
    if req.provider == "azure":
        return _verify_azure(req)
    return VerifyResponse(
        status="FAIL",
        provider_used="none",
        fallback_used=False,
        requested_language=req.language,
        resolved_language_id=req.language,
        model_class=req.provider,
        voice=req.voice or "default",
        device="",
        error=f"Verification not supported for provider '{req.provider}' via this endpoint. Use tts-gateway /tts/verify.",
    )


def _verify_azure(req: VerifyRequest) -> VerifyResponse:
    if not _azure_configured():
        return VerifyResponse(
            status="FAIL",
            provider_used="none",
            fallback_used=False,
            requested_language=req.language,
            resolved_language_id=req.language,
            model_class="Azure",
            voice=req.voice or "ko-KR-InJoonNeural",
            device="cloud",
            error="AZURE_SPEECH_KEY or AZURE_SPEECH_REGION not configured.",
        )

    _voice_map = {"ko": "ko-KR-InJoonNeural", "en": "en-US-JennyNeural", "zh-CN": "zh-CN-XiaoxiaoNeural"}
    voice = req.voice or _voice_map.get(req.language, "ko-KR-InJoonNeural")
    lang_map = {"ko": "ko-KR", "en": "en-US", "zh-CN": "zh-CN"}
    xml_lang = lang_map.get(req.language, "ko-KR")

    out_dir = _PROJECT_ROOT / "work" / "tts_verify"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"azure_{req.language}_{int(time.time())}.mp3"

    try:
        import azure.cognitiveservices.speech as speechsdk  # type: ignore[import]

        key = os.getenv("AZURE_SPEECH_KEY") or os.getenv("AZURE_TTS_KEY", "")
        region = os.getenv("AZURE_SPEECH_REGION") or os.getenv("AZURE_TTS_REGION", "")
        cfg = speechsdk.SpeechConfig(subscription=key, region=region)
        cfg.set_speech_synthesis_output_format(speechsdk.SpeechSynthesisOutputFormat.Audio16Khz32KBitRateMonoMp3)
        synth = speechsdk.SpeechSynthesizer(speech_config=cfg, audio_config=None)

        ssml = (
            f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{xml_lang}">'
            f'<voice name="{voice}">{req.text}</voice></speak>'
        )
        t0 = time.time()
        result = synth.speak_ssml_async(ssml).get()
        elapsed = time.time() - t0

        if result.reason.name == "SynthesizingAudioCompleted":
            out_path.write_bytes(result.audio_data)
            duration = len(result.audio_data) / (16000 * 2)
            return VerifyResponse(
                status="SUCCESS",
                provider_used="azure",
                fallback_used=False,
                requested_language=req.language,
                resolved_language_id=xml_lang,
                model_class="Azure",
                voice=voice,
                device="cloud",
                file_path=str(out_path),
                duration_s=round(duration, 2),
                synthesis_time_s=round(elapsed, 2),
            )
        return VerifyResponse(
            status="FAIL",
            provider_used="azure",
            fallback_used=False,
            requested_language=req.language,
            resolved_language_id=xml_lang,
            model_class="Azure",
            voice=voice,
            device="cloud",
            error=f"Azure result: {result.reason.name}",
        )
    except Exception as exc:
        return VerifyResponse(
            status="FAIL",
            provider_used="azure",
            fallback_used=False,
            requested_language=req.language,
            resolved_language_id=xml_lang,
            model_class="Azure",
            voice=voice,
            device="cloud",
            error=str(exc),
        )
