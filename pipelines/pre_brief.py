"""S1.5 — Pre-Brief Q&A. 보고서에서 핵심 개념을 추출하고 사용자 사전 지식을 수집한다.

산출물: work/brief.json
참조: 플레이북 v2 섹션 3 (S1.5 Pre-Brief Q&A)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── 로깅 / UI ─────────────────────────────────────────────────────────────────
try:
    from rich.console import Console
    from rich.prompt import Prompt as _RichPrompt

    _log_console = Console(stderr=True)
    _ui_console  = Console()

    def _log(msg: str, level: str = "info") -> None:
        color = {"info": "green", "warning": "yellow", "error": "red"}.get(level, "white")
        _log_console.print(f"[{color}][pre_brief][/{color}] {msg}")

    def _ui(msg: str = "") -> None:
        _ui_console.print(msg)

    def _ask(prompt: str) -> str:
        return _RichPrompt.ask(prompt)

except ImportError:
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO)

    def _log(msg: str, level: str = "info") -> None:  # type: ignore[misc]
        getattr(_logging, level, _logging.info)(f"[pre_brief] {msg}")

    def _ui(msg: str = "") -> None:  # type: ignore[misc]
        print(re.sub(r"\[/?[^\]]*\]", "", msg))

    def _ask(prompt: str) -> str:  # type: ignore[misc]
        clean = re.sub(r"\[/?[^\]]*\]", "", prompt)
        return input(f"{clean}: ")


# ── 상수 ──────────────────────────────────────────────────────────────────────
_PURPOSE_DURATION: dict[str, int] = {
    "overview":   9,
    "understand": 12,
    "apply":      17,
    "decide":     11,
}

_CONCEPT_SYSTEM = (
    "당신은 기술 문서에서 학습 핵심 개념을 추출하는 전문가입니다. "
    "JSON 이외의 텍스트를 절대 출력하지 마세요."
)

_CONCEPT_PROMPT_TMPL = """\
아래 기술 보고서에서 학습자가 반드시 이해해야 할 핵심 개념/용어 8~12개를 선정하라.
각 개념은 고유명사·기술용어·약어·시스템 이름 중에서 뽑고, 일반적 한국어 단어는 제외.
JSON 출력만: {{"concepts":[{{"name":string, "hint":string(20자 이내)}}]}}

보고서:
{report_text}"""


def _strip_fence(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```[a-z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return text.strip()


# ── 공개 함수 ─────────────────────────────────────────────────────────────────

def extract_concepts(report_path: Path) -> list[dict]:
    """보고서에서 학습 핵심 개념 8~12개를 LLM(role='light')으로 추출한다.

    Args:
        report_path: 원본 보고서 파일 경로.

    Returns:
        [{"name": str, "hint": str(20자 이내)}, ...] 형식의 개념 리스트.

    Raises:
        FileNotFoundError: report_path 가 존재하지 않음.
        ValueError: 3회 시도 모두 JSON 파싱 실패.
    """
    if not report_path.exists():
        raise FileNotFoundError(f"보고서 파일 없음: {report_path}")

    report_text = report_path.read_text(encoding="utf-8")
    _log(f"보고서 로드: {report_path.name} ({len(report_text):,}자)")

    from llm_client import generate

    prompt = _CONCEPT_PROMPT_TMPL.format(report_text=report_text)
    last_exc: Exception | None = None

    for attempt in range(1, 4):
        _log(f"개념 추출 LLM 호출 {attempt}/3 (role=light) …")
        raw = generate(prompt, role="light", system=_CONCEPT_SYSTEM)
        try:
            data = json.loads(_strip_fence(raw))
            concepts: list[dict] = data["concepts"]
            _log(f"개념 {len(concepts)}개 추출 완료")
            return concepts
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            last_exc = exc
            _log(f"JSON 파싱 실패 (시도 {attempt}): {exc}", "warning")

    raise ValueError(f"개념 추출 JSON 파싱 3회 모두 실패: {last_exc}") from last_exc


def collect_brief(concepts: list[dict]) -> dict:
    """CLI interactive 로 사용자 사전 지식(K/H/U), 학습 목적, 관심 지점을 수집한다.

    Args:
        concepts: extract_concepts() 가 반환한 개념 리스트.

    Returns:
        {
          "concepts": [{"name": str, "level": "K"|"H"|"U", "note": str}, ...],
          "purpose": "overview"|"understand"|"apply"|"decide",
          "interests": str,
          "target_duration_min": int,
        }
    """
    # ── 사전 지식 수집 ───────────────────────────────────────────────────────
    _ui()
    _ui("[bold cyan]━━━ Pre-Brief Q&A (1/3) — 사전 지식 ━━━[/bold cyan]")
    _ui()
    _ui(
        "각 개념에 대해 사전 지식 수준을 입력하세요:\n"
        "  [green]K[/green] = 이미 안다   "
        "[yellow]H[/yellow] = 들어봤지만 설명 못 한다   "
        "[red]U[/red] = 처음 듣는다"
    )
    _ui()

    enriched: list[dict] = []
    for concept in concepts:
        name: str = concept.get("name", "")
        hint: str = concept.get("hint", "")
        while True:
            raw_level = _ask(
                f"  [bold]{name}[/bold]  [dim]{hint}[/dim]  [cyan](K/H/U)[/cyan]"
            ).strip().upper()
            if raw_level in ("K", "H", "U"):
                break
            _ui("    [red]K, H, U 중 하나만 입력하세요.[/red]")
        enriched.append({"name": name, "level": raw_level, "note": ""})

    # ── 학습 목적 수집 ───────────────────────────────────────────────────────
    _ui()
    _ui("[bold cyan]━━━ Pre-Brief Q&A (2/3) — 학습 목적 ━━━[/bold cyan]")
    _ui()
    _ui(
        "  [bold]overview[/bold]   = 전체 그림만     (영상 ~9분,  얕고 넓게)\n"
        "  [bold]understand[/bold] = 제대로 이해      (영상 ~12분, 개념마다 사례)\n"
        "  [bold]apply[/bold]     = 실제 사용         (영상 ~17분, 명령어·설정 중심)\n"
        "  [bold]decide[/bold]    = 도입 여부 판단    (영상 ~11분, 장단점·대안 중심)"
    )
    _ui()

    purpose = ""
    while True:
        raw_purpose = _ask(
            "  학습 목적 선택 [cyan](overview/understand/apply/decide)[/cyan]"
        ).strip().lower()
        if raw_purpose in _PURPOSE_DURATION:
            purpose = raw_purpose
            break
        _ui("    [red]overview, understand, apply, decide 중 하나만 입력하세요.[/red]")

    target_duration_min = _PURPOSE_DURATION[purpose]

    # ── 관심 지점 수집 ───────────────────────────────────────────────────────
    _ui()
    _ui("[bold cyan]━━━ Pre-Brief Q&A (3/3) — 관심 지점 ━━━[/bold cyan]")
    _ui()
    _ui(
        "특히 궁금한 점, 실패 경험, 비교 대상 등을 자유롭게 입력하세요.\n"
        "[dim](빈 줄 2회 연속으로 입력을 종료합니다)[/dim]"
    )
    _ui()

    lines: list[str] = []
    consecutive_blanks = 0
    while True:
        line = input()
        if line == "":
            consecutive_blanks += 1
            if consecutive_blanks >= 2:
                interests = "\n".join(lines).strip()
                if interests:
                    break
                _ui("[red]최소 1문장 이상 입력해야 합니다. 계속 입력하세요.[/red]")
                consecutive_blanks = 0
            else:
                lines.append(line)
        else:
            consecutive_blanks = 0
            lines.append(line)

    interests = "\n".join(lines).strip()

    return {
        "concepts":           enriched,
        "purpose":            purpose,
        "interests":          interests,
        "target_duration_min": target_duration_min,
    }


def save_brief(brief: dict, out_path: Path) -> None:
    """brief 딕셔너리에 created_at(ISO 8601)을 추가하고 JSON으로 저장한다.

    Args:
        brief: collect_brief() 반환값.
        out_path: 저장 경로 (work/brief.json).

    Notes:
        out_path 가 이미 존재하면 덮어쓰기 전에 사용자 확인을 요청한다.
    """
    if out_path.exists():
        _ui()
        answer = _ask(
            f"[yellow]{out_path} 이 이미 존재합니다. 덮어쓸까요? (y/N)[/yellow]"
        ).strip().lower()
        if answer not in ("y", "yes"):
            _log("저장 취소 — 기존 파일 유지.", "warning")
            return

    out_data = {**brief, "created_at": datetime.now().isoformat(timespec="seconds")}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out_data, ensure_ascii=False, indent=2), encoding="utf-8")
    _log(f"저장 완료: {out_path}  ({len(brief.get('concepts', []))}개 개념)")


# ── CLI ───────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pre_brief.py",
        description=(
            "S1.5 — 보고서에서 핵심 개념을 추출하고 사용자 사전 지식을 수집해\n"
            "work/brief.json 을 생성한다."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--input", required=True, metavar="FILE", help="입력 보고서 경로")
    p.add_argument(
        "--out",
        default="work/brief.json",
        metavar="FILE",
        help="출력 brief.json 경로 (기본: work/brief.json)",
    )
    return p


def main() -> None:
    args = _build_parser().parse_args()

    report_path = Path(args.input)
    if not report_path.exists():
        _log(f"입력 파일 없음: {report_path}", "error")
        sys.exit(1)
    if report_path.is_dir():
        _log(f"디렉토리가 지정되었습니다 (파일 경로를 지정하세요): {report_path}", "error")
        sys.exit(1)

    try:
        concepts = extract_concepts(report_path)
    except (FileNotFoundError, ValueError) as exc:
        _log(str(exc), "error")
        sys.exit(1)

    brief = collect_brief(concepts)
    save_brief(brief, Path(args.out))


if __name__ == "__main__":
    main()
