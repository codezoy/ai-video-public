from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator

from api.services.tts_settings import SUPPORTED_TTS_PROVIDERS

_ALLOWED_LANGUAGES = {"ko", "en", "zh-CN"}
class RunCreateRequest(BaseModel):
    topic: str = Field(..., description="Short slug identifying the video topic")
    input_path: Optional[str] = Field(None, description="Path to input markdown/PDF file; omit to use topic-based generation")
    stop_after: str = Field("qa", description="Pipeline stage to stop after")
    dry_run: bool = Field(False, description="Validate config without executing")
    force: bool = Field(False, description="Overwrite existing run artifacts")
    iteration: str = Field("latest", description="Run iteration label")
    auto_correct: bool = Field(False, description="Auto-correct script issues")
    target_duration_sec: int = Field(120, ge=10, description="Target video duration in seconds")
    mode: str = Field("template", description="Pipeline mode: template | direct")
    language: str = Field("ko", description="Target language: ko | en | zh-CN")
    contents: Optional[str] = Field(None, description="Raw study material for Contents Adapter; omit to use topic-based generation")
    prompt_filename: Optional[str] = Field(None, description="Prompt template filename to use (e.g. writer_system.md)")
    run_type: str = Field("TEST", description="Run type: TEST | PRODUCTION")
    tts_provider: Optional[str] = Field(None, description="Per-run TTS provider override; omit to use Settings default")
    tts_voice: Optional[str] = Field(None, description="TTS voice ID (e.g. ko-KR-SunHiNeural, default)")

    @field_validator("tts_provider")
    @classmethod
    def validate_tts_provider(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        normalized = v.lower().strip()
        if normalized not in SUPPORTED_TTS_PROVIDERS:
            raise ValueError(
                f"Unsupported TTS provider '{normalized}'. Allowed: {sorted(SUPPORTED_TTS_PROVIDERS)}"
            )
        return normalized

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        if v not in _ALLOWED_LANGUAGES:
            raise ValueError(f"Unsupported language '{v}'. Allowed: {sorted(_ALLOWED_LANGUAGES)}")
        return v

    @field_validator("run_type")
    @classmethod
    def validate_run_type(cls, v: str) -> str:
        normalized = v.upper().strip()
        if normalized not in {"TEST", "PRODUCTION"}:
            raise ValueError("run_type must be TEST or PRODUCTION")
        return normalized
