"""RunService — shared service layer for CLI and API.

Both the CLI (pipelines/run_pipeline.py main()) and the FastAPI routes
call through this service to guarantee a single execution path.

Architecture:
    CLI  →  run_pipeline.main()  →  run_pipeline.run()
    API  →  RunService           →  run_pipeline.run()
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

logger = logging.getLogger(__name__)


def _resolve_input_for_topic(topic: str) -> Path | None:
    """Try to find inputs/<topic>.md or inputs/<slug>.md in the project root.

    Returns the resolved path if found, None otherwise.
    """
    root = Path(os.getenv("PROJECT_ROOT", str(Path(__file__).parent.parent)))
    inputs_dir = root / "inputs"
    slug = topic.replace(" ", "-").lower()
    for candidate in [inputs_dir / f"{topic}.md", inputs_dir / f"{slug}.md"]:
        if candidate.exists():
            return candidate.resolve()
    return None


class RunService:
    """Thin wrapper around run_pipeline.run() for API consumption."""

    def run_video_pipeline(
        self,
        topic: str,
        input_path: str | None,
        stop_after: str = "qa",
        dry_run: bool = False,
        force: bool = False,
        iteration: str = "latest",
        auto_correct: bool = False,
        target_duration_sec: int = 120,
        mode: str = "template",
        run_id: str | None = None,
        language: str = "ko",
        contents: str | None = None,
        prompt_filename: str | None = None,
        tts_provider: str = "azure",
        tts_voice: str | None = None,
        cancel_event: threading.Event | None = None,
    ) -> None:
        """Invoke the video pipeline service function directly.

        Input priority (highest to lowest):
          1. contents — UI-provided raw study material
          2. input_path (explicit) — caller-specified file path
          3. topic-based file — inputs/<topic>.md or inputs/<slug>.md
          4. topic-only — no input file; LLM generates purely from topic

        Raises RuntimeError if the pipeline fails; callers are
        responsible for translating this into appropriate API errors.
        """
        from pipelines.run_pipeline import run

        resolved: Path | None = None
        if contents:
            source_desc = "contents (UI-provided)"
        elif input_path:
            resolved = Path(input_path).resolve()
            _project_root = Path(os.getenv("PROJECT_ROOT", str(Path(__file__).parent.parent))).resolve()
            if not resolved.is_relative_to(_project_root):
                raise ValueError(f"input_path must be within project root ({_project_root}): {resolved}")
            if not resolved.exists():
                raise FileNotFoundError(f"Input file not found: {resolved}")
            source_desc = f"explicit_file:{resolved.name}"
        else:
            resolved = _resolve_input_for_topic(topic)
            source_desc = f"topic_file:{resolved.name}" if resolved else "topic_only (no input file)"

        logger.info(
            "[RunService] INPUT SOURCE: topic=%s source=%s language=%s",
            topic, source_desc, language,
        )
        print(
            f"[INPUT_SOURCE] topic={topic!r} source={source_desc!r} language={language}",
            flush=True,
        )

        run(
            topic=topic,
            input_path=resolved,
            stop_after=stop_after,
            dry_run=dry_run,
            force=force,
            iteration=iteration,
            auto_correct=auto_correct,
            target_duration_sec=target_duration_sec,
            mode=mode,
            run_id=run_id,
            language=language,
            contents=contents,
            prompt_filename=prompt_filename,
            tts_provider=tts_provider,
            tts_voice=tts_voice,
            cancel_event=cancel_event,
        )
        logger.info("[RunService] Pipeline completed: topic=%s", topic)
