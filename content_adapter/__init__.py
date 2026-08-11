"""
Content Adapter — 3-layer pipeline for converting raw input into a scene-ready plan.

Layers:
    1. InputDetector    → detect_input_type()      → "TEXT"
    2. ContentClassifier → classify_content_type() → "LECTURE"
    3. SceneStrategy    → select_scene_strategy()  → "lecture_v1"

MVP scope: TEXT input only, LECTURE content type, lecture_v1 strategy.
"""

from .input_detector import detect_input_type
from .content_classifier import classify_content_type
from .scene_strategy import select_scene_strategy
from .adapter import adapt

__all__ = [
    "adapt",
    "detect_input_type",
    "classify_content_type",
    "select_scene_strategy",
]
