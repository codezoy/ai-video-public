from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/templates", tags=["Templates"])

_PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"
_HYPERFRAME_DIR = Path(__file__).parent.parent.parent / "hyperframe" / "src" / "templates"


class TemplateResponse(BaseModel):
    name: str
    filename: str
    size_bytes: int
    content: str = ""


class VideoTemplateResponse(BaseModel):
    name: str
    filename: str


@router.get("", response_model=list[TemplateResponse])
def list_templates() -> list[TemplateResponse]:
    templates = []
    for p in sorted(_PROMPTS_DIR.glob("*.md")):
        templates.append(
            TemplateResponse(
                name=p.stem,
                filename=p.name,
                size_bytes=p.stat().st_size,
                content=p.read_text(encoding="utf-8"),
            )
        )
    return templates


@router.get("/video-templates", response_model=list[VideoTemplateResponse])
def list_video_templates() -> list[VideoTemplateResponse]:
    if not _HYPERFRAME_DIR.exists():
        return []
    templates = []
    for p in sorted(_HYPERFRAME_DIR.glob("*.tsx")):
        templates.append(VideoTemplateResponse(name=p.stem, filename=p.name))
    return templates
