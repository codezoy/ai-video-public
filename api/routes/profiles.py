from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/profiles", tags=["Profiles"])

_ALLOWED_PROFILES = {"LECTURE", "SHORTS"}


class ProfileResponse(BaseModel):
    name: str
    max_duration_sec: int
    min_scenes: int
    max_scenes: int
    max_scene_narration_chars: int
    max_total_narration_chars: int
    fast_path: bool


@router.get("", response_model=list[ProfileResponse])
def list_profiles() -> list[ProfileResponse]:
    from pipelines.generation_profiles import GENERATION_PROFILES

    return [
        ProfileResponse(
            name=name,
            max_duration_sec=cfg["max_duration_sec"],
            min_scenes=cfg["min_scenes"],
            max_scenes=cfg["max_scenes"],
            max_scene_narration_chars=cfg["max_scene_narration_chars"],
            max_total_narration_chars=cfg["max_total_narration_chars"],
            fast_path=cfg.get("fast_path", False),
        )
        for name, cfg in GENERATION_PROFILES.items()
        if name in _ALLOWED_PROFILES
    ]
