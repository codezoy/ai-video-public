"""S2.5 — 대본 다듬기. work/scripts/script_draft.md → work/scripts/script.md."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

try:
    from rich.console import Console
    _console = Console(stderr=True)
    def _log(msg: str, level: str = "info") -> None:
        color = {"info": "cyan", "warning": "yellow", "error": "red", "success": "green"}.get(level, "white")
        _console.print(f"[{color}][polish_script][/{color}] {msg}")
except ImportError:
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO)
    def _log(msg: str, level: str = "info") -> None:  # type: ignore[misc]
        getattr(_logging, level, _logging.info)(f"[polish_script] {msg}")

ROOT        = Path(os.environ.get("PROJECT_ROOT", Path(__file__).parent.parent))
WORK_DIR    = Path(os.getenv("WORK_DIR", str(ROOT / "work")))
SCRIPTS_DIR = WORK_DIR / "scripts"

DRAFT_FILE  = SCRIPTS_DIR / "script_draft.md"
OUTPUT_FILE = SCRIPTS_DIR / "script.md"

LLM_POLISH  = os.getenv("LLM_POLISH", "claude-haiku")

POLISH_SYSTEM = (
    "당신은 한국어 영상 대본 편집 전문가입니다. "
    "이운규 공부법 기준으로 아래 대본 초안을 다듬어 완성된 대본을 출력하세요.\n"
    "1. 이운규식 7단 구조(선언→개념→확장→사례→흐름→적용→정리)가 명확히 드러나게 한다.\n"
    "   - 선언 단계에 전체 구조(목차)가 없으면 핵심 3~5개 항목을 짧게 추가한다.\n"
    "2. 각 본문 섹션에 6블록이 존재하는지 확인하고 빠진 블록을 보완한다:\n"
    "   [WHY-동기] [정의] [원리-메커니즘] [실제 사례] [해보기] [연결]\n"
    "   - [WHY-동기] 없거나 약하면 추가: '이것을 모르면 어떤 문제가 생기는가' 1~2문장 문제 제기\n"
    "   - [정의] 나열만 있으면 원인 → 동작원리 → 결과 흐름으로 재구성한다\n"
    "   - [실제 사례] 없으면 실무 예시(이름·명령어·수치 포함) 1개를 추가한다\n"
    "   - [해보기] 없으면 추가: '직접 해보기:' 레이블 + 즉시 실행 가능한 것 1가지\n"
    "     (현업 적용 포인트도 허용. '해볼 수 있다' 수준의 모호한 권유 금지)\n"
    "3. 정리 단계에 '핵심 N가지' 목록(3~5개)이 없으면 추가한다.\n"
    "4. 각 씬의 나레이션은 자연스럽고 구어체로 작성한다.\n"
    "5. 불필요한 반복·중복 문장을 제거한다. 단, 서로 다른 개념을 다루는 문장은 '중복'으로 보지 않는다.\n"
    "6. 원본의 핵심 내용과 사실은 그대로 유지한다. 구체 개념(버전 번호·명령어·알고리즘명·수치·고유명사)을 추상 표현으로 대체 금지. 서로 다른 개념을 하나의 문장·bullet으로 통합 금지.\n"
    "7. 반드시 한국어로만 출력한다.\n"
    "8. 과도한 장문화 금지 — 각 블록은 지정 문장 수 이내로 유지한다.\n"
    "9. 주제 드리프트 금지 — 원본 주제를 상위 범주나 인접 주제로 대체하지 마라.\n"
    "초안 원문을 그대로 돌려주지 말고, 실제로 개선된 내용을 출력하세요."
)


def run(force: bool = False) -> None:
    if not DRAFT_FILE.exists():
        _log(f"초안 파일 없음: {DRAFT_FILE}", "error")
        sys.exit(1)

    if OUTPUT_FILE.exists() and not force:
        _log(f"이미 존재: {OUTPUT_FILE}  (재생성하려면 --force 사용)", "warning")
        return

    draft_text = DRAFT_FILE.read_text(encoding="utf-8")
    _log(f"초안 로드 완료: {DRAFT_FILE.name} ({len(draft_text):,}자)")

    if LLM_POLISH == "none":
        _log("LLM_POLISH=none → 초안을 그대로 복사", "warning")
        SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
        OUTPUT_FILE.write_text(draft_text, encoding="utf-8")
        _log(f"저장 완료 (복사): {OUTPUT_FILE}")
        return

    from llm_client import generate

    _log(f"LLM 호출 시작 (role=polisher, model={LLM_POLISH}) …")
    result = generate(draft_text, role="polisher", system=POLISH_SYSTEM)

    if len(result) < 500:
        _log(f"출력이 너무 짧습니다 ({len(result)}자). 초안을 그대로 사용합니다.", "warning")
        result = draft_text

    SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(result, encoding="utf-8")
    _log(f"저장 완료: {OUTPUT_FILE} ({len(result):,}자)", "success")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="polish_script.py",
        description="S2.5 — work/scripts/script_draft.md 를 다듬어 work/scripts/script.md 를 생성한다.",
    )
    p.add_argument("--force", action="store_true", help="기존 script.md 를 무시하고 재생성")
    return p


def main() -> None:
    args = _build_parser().parse_args()
    run(force=args.force)


if __name__ == "__main__":
    main()
