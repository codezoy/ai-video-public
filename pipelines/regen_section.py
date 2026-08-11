"""S3.5 — 섹션별 재생성 루프. regen_tasks.json에 따라 개별 섹션을 재생성하고 채점 기반으로 수용/거절한다.

산출물: work/iterations/v{n+1}/script.md
참조: 플레이북 v2 섹션 5 (S3.5 섹션별 재생성 루프), 섹션 8 (이터레이션 버전 관리)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Callable

from dotenv import load_dotenv

load_dotenv()

try:
    from rich.console import Console
    _console = Console(stderr=True)
    def _log(msg: str, level: str = "info") -> None:
        color = {"info": "green", "warning": "yellow", "error": "red", "success": "cyan"}.get(level, "white")
        _console.print(f"[{color}][regen_section][/{color}] {msg}")
except ImportError:
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO)
    def _log(msg: str, level: str = "info") -> None:  # type: ignore[misc]
        getattr(_logging, level, _logging.info)(f"[regen_section] {msg}")

ROOT = Path(os.environ.get("PROJECT_ROOT", Path(__file__).parent.parent))
WORK_DIR = Path(os.getenv("WORK_DIR", str(ROOT / "work")))

# mode별 재생성 지시문
_MODE_PROMPTS: dict[str, str] = {
    "full": (
        "다음 섹션을 완전히 재작성하라. 반드시 4블록 구조를 모두 포함해야 한다:\n"
        "[정의] — 핵심 개념을 추상어 없이 30초 내 이해 가능하게 정의\n"
        "[구성요소 분해] — 2~4개로 나누고 각각 왜 별도인지 설명\n"
        "[실제 사례] — 이름·숫자·버전·명령어·실패 경험 중 2개 이상\n"
        "[흐름 연결] — '~이 해결되지 않으면 ~가 필요하다' 형태로 이전/다음 섹션과 연결"
    ),
    "deep": (
        "다음 섹션을 심화 재작성하라. 4블록 구조와 반례 1개를 반드시 포함해야 한다:\n"
        "[정의] — 추상어 없이 30초 내 이해 가능하게 정의\n"
        "[구성요소 분해] — 2~4개로 나누고 각각 왜 별도인지 설명\n"
        "[실제 사례] — 이름·숫자·버전·명령어·실패 경험 중 2개 이상\n"
        "[반례/비교] — '~라고 오해할 수 있지만 실제로는...' 형태 반례 또는 비교 1개\n"
        "[흐름 연결] — '~이 해결되지 않으면 ~가 필요하다' 형태 이음말"
    ),
    "shrink": (
        "다음 섹션을 현재 분량의 1/3로 압축하라. "
        "핵심 정의만 남기고 나머지 삭제. 출력은 요약된 섹션 전문만."
    ),
    "example_only": (
        "다음 섹션의 기존 구조를 그대로 유지하고, 섹션 끝에 [실제 사례] 블록만 추가하라.\n"
        "기존 내용은 한 글자도 바꾸지 말고, 아래 형식을 섹션 끝에 붙여 전체 섹션을 출력하라:\n\n"
        "[실제 사례]\n"
        "(명령어·버전·실패 경험 중 1개 이상 포함한 구체적 사례 2~3문장)"
    ),
    "rewrite": (
        "다음 섹션을 전면 재작성하라. 아래 금지 비유는 절대 사용하지 마라:\n"
        "금지어: 건물, 건축, 층, 기초, 벽돌, 설계도, 공사, 시공\n\n"
        "4블록 구조를 모두 포함해야 한다:\n"
        "[정의] — 추상어 없이 30초 내 이해 가능하게 정의\n"
        "[구성요소 분해] — 2~4개로 나누고 각각 왜 별도인지 설명\n"
        "[실제 사례] — 이름·숫자·버전·명령어·실패 경험 중 2개 이상\n"
        "[흐름 연결] — 이전/다음 섹션과 연결"
    ),
}


def _parse_sections(script_text: str) -> list[dict]:
    """## 또는 ### 헤더 기준으로 섹션을 분리한다. # 단일 제목은 제외."""
    parts = re.split(r"\n(?=#{2,3} )", script_text.strip())
    sections: list[dict] = []
    idx = 1
    for part in parts:
        part = part.strip()
        if not re.match(r"^#{2,3} ", part):
            continue
        lines = part.split("\n")
        title = re.sub(r"^#{2,3} ", "", lines[0]).strip()
        sections.append({"id": idx, "title": title, "text": part})
        idx += 1
    return sections


def _strip_trailing_separator(text: str) -> str:
    """섹션 텍스트 끝의 --- 구분자를 제거한다."""
    return re.sub(r"\n*\n---\s*$", "", text.rstrip())


def _body_only(section_text: str) -> str:
    """섹션 텍스트에서 헤더(## / ###)를 제거하고 본문만 반환한다.
    LLM이 다중 섹션을 출력했을 때는 첫 번째 섹션의 본문만 추출한다."""
    text = section_text.strip()
    parts = re.split(r"\n(?=#{2,3} )", text)
    first = parts[0].strip()
    lines = first.split("\n")
    if lines and re.match(r"^#{2,3} ", lines[0]):
        lines = lines[1:]
    return "\n".join(lines).strip()


def _reconstruct_script(original: str, sections: list[dict], overrides: dict[int, str | None]) -> str:
    """섹션 overrides를 적용해 스크립트를 재구성한다.

    overrides: {section_id: new_text | None(삭제)}
    """
    first_match = re.search(r"^#{2,3} ", original, re.MULTILINE)
    preamble = original[: first_match.start()].rstrip() if first_match else ""

    section_parts: list[str] = []
    for sec in sorted(sections, key=lambda s: s["id"]):
        sid = sec["id"]
        if sid in overrides:
            new_text = overrides[sid]
            if new_text is None:
                _log(f"섹션 {sid} 제외 (삭제 모드)")
                continue
            section_parts.append(_strip_trailing_separator(new_text.strip()))
        else:
            section_parts.append(_strip_trailing_separator(sec["text"]))

    body = "\n\n---\n\n".join(section_parts)
    if preamble:
        return preamble + "\n\n" + body + "\n"
    return body + "\n"


def _score_sum(section_text: str, section_id: int) -> float:
    """섹션을 LLM-as-Judge로 채점하고 5축 점수 합을 반환한다."""
    try:
        from llm_judge import score_section  # type: ignore[import]
    except ImportError:
        from pipelines.llm_judge import score_section  # type: ignore[import]
    result = score_section(section_text, section_id)
    return float(sum(result["scores"].values()))


def regenerate(
    section_id: int,
    mode: str,
    context_prev: str,
    context_next: str,
    source_excerpt: str,
    current_section: str,
    user_instructions: str,
) -> str:
    """단일 섹션을 LLM(role='writer_high')으로 재생성한다.

    Args:
        section_id: 재생성 대상 섹션 순번 (1-indexed).
        mode: 재생성 방식.
            "full"         — 4블록 전체 재작성.
            "deep"         — 4블록 + 반례 1개 추가.
            "shrink"       — 1/3 분량으로 압축.
            "example_only" — 기존 섹션 유지 + [실제 사례] 블록만 추가.
            "rewrite"      — 전면 재작성, 비유 금지어 추가.
            "delete"        — 빈 문자열 반환 (섹션 삭제 표시).
        context_prev: 이전 섹션 전문 (이음말 맥락).
        context_next: 다음 섹션 전문 (흐름 연결 힌트).
        source_excerpt: 원본 보고서 전체 내용 (LLM 근거 자료).
        current_section: 현재 섹션의 기존 출력 (개선 대상).
        user_instructions: 추가 지시 사항.

    Returns:
        재생성된 섹션 텍스트. mode="delete" 이면 빈 문자열.
    """
    if mode == "delete":
        return ""

    try:
        from llm_client import generate  # type: ignore[import]
    except ImportError:
        from pipelines.llm_client import generate  # type: ignore[import]

    mode_instruction = _MODE_PROMPTS.get(mode, _MODE_PROMPTS["full"])

    prompt = (
        f"[재생성 지시 — mode={mode}]\n"
        f"{mode_instruction}\n\n"
        + (f"[추가 지시]\n{user_instructions}\n\n" if user_instructions else "")
        + (
            f"[참고 원문]\n{source_excerpt}\n\n"
            if source_excerpt
            else ""
        )
        + (
            f"[이전 섹션 — 이음말 맥락]\n{_strip_trailing_separator(context_prev)}\n\n"
            if context_prev
            else ""
        )
        + (
            f"[다음 섹션 — 흐름 연결 힌트]\n{_strip_trailing_separator(context_next)}\n\n"
            if context_next
            else ""
        )
        + (
            f"[개선 대상 섹션]\n{_strip_trailing_separator(current_section)}\n\n"
            if current_section
            else ""
        )
        + "[출력 규칙]\n"
        "- 반드시 한국어로만 작성\n"
        "- 섹션 본문만 출력. 헤더(## 또는 ###로 시작하는 줄)는 절대 출력하지 마라.\n"
        "- 첫 줄은 본문 첫 문장으로 시작하라. '##'로 시작하는 줄을 포함하지 마라.\n"
        "- 앞뒤 부연 설명 없이 본문 내용만 출력"
    )

    est_tokens = len(prompt) // 3  # 한국어 평균 ~3chars/token 기준 추정
    _log(f"섹션 {section_id} 재생성 중 (mode={mode}, ~{est_tokens} input tokens, role=writer_high) …")

    if os.getenv("RAG_ENABLED", "1") == "1":
        try:
            from rag_inject import inject_into_writer_prompt  # type: ignore[import]
        except ImportError:
            from pipelines.rag_inject import inject_into_writer_prompt  # type: ignore[import]
        _section_title = current_section.split("\n")[0] if current_section else ""
        _section_lead = current_section.split("\n\n")[0] if current_section else ""
        _rag_query = f"{_section_title}\n{_section_lead}"
        prompt = inject_into_writer_prompt(prompt, _rag_query, k=5)

    return generate(prompt, role="writer_high")


def accept_or_reject(
    old_text: str,
    new_text: str,
    section_id: int,
    regen_fn: Callable[[], str] | None = None,
) -> str:
    """재생성 결과를 LLM-as-Judge 점수 기반으로 수용 또는 거절한다.

    Args:
        old_text: 원본 섹션 텍스트.
        new_text: 재생성된 섹션 텍스트 (1번째 시도).
        section_id: 섹션 순번 (로깅 용도).
        regen_fn: 재시도 시 호출할 재생성 콜백 (None이면 재시도 없음).

    Returns:
        채택된 섹션 텍스트 (new 또는 old).

    Notes:
        new_text 점수 합 > old_text 점수 합 이면 new_text 채택.
        낮으면 최대 2회 추가 재생성 (총 3회 시도).
        3회 모두 실패하면 old_text 유지 + WARN 로그.
    """
    old_sum = _score_sum(old_text, section_id)
    _log(f"섹션 {section_id} 원본 점수 합: {old_sum:.1f}")

    candidate = new_text
    for attempt in range(3):
        new_sum = _score_sum(candidate, section_id)
        _log(f"섹션 {section_id} 시도 {attempt + 1}/3: new_sum={new_sum:.1f}, old_sum={old_sum:.1f}")

        new_length = len(candidate)
        old_length = len(old_text)
        if new_sum >= old_sum and new_length >= old_length * 0.8:
            _log(
                f"섹션 {section_id} 채택 ✓ (new={new_sum:.1f} >= old={old_sum:.1f}, len={new_length}/{old_length})",
                "success",
            )
            return candidate

        if attempt < 2 and regen_fn is not None:
            _log(
                f"섹션 {section_id} 거절 (new={new_sum:.1f}, len={new_length}/{old_length}) → 재시도 {attempt + 2}/3",
                "warning",
            )
            candidate = regen_fn()
        else:
            break

    _log(
        f"섹션 {section_id}: 3회 시도 모두 원본보다 낮음 → 원본 유지 (best ≤ old={old_sum:.1f})",
        "warning",
    )
    return old_text


def run_tasks(
    tasks_path: Path,
    script_path: Path,
    out_path: Path,
    source_report: str = "",
) -> Path:
    """regen_tasks.json에 따라 섹션을 재생성하고 새 script.md를 저장한다.

    Args:
        tasks_path: regen_tasks.json 경로.
        script_path: 기준 script.md 경로.
        out_path: 출력 script.md 경로 (예: work/iterations/v2/script.md).
        source_report: 원본 보고서 전체 내용 (LLM 근거 자료로 전달).

    Returns:
        저장된 출력 파일 경로.
    """
    tasks_data = json.loads(tasks_path.read_text(encoding="utf-8"))
    tasks: list[dict] = tasks_data.get("regen_tasks", [])

    script_text = script_path.read_text(encoding="utf-8")
    sections = _parse_sections(script_text)
    sec_map: dict[int, dict] = {s["id"]: s for s in sections}

    _log(f"태스크 {len(tasks)}개, 섹션 {len(sections)}개 로드")

    overrides: dict[int, str | None] = {}

    for task in tasks:
        sid: int = task["section_id"]
        mode: str = task.get("mode", "full")
        extra: str = task.get("extra_instructions", "")

        sec = sec_map.get(sid)
        if sec is None:
            _log(f"섹션 {sid} 없음, 스킵", "warning")
            continue

        old_text: str = sec["text"]

        if mode == "delete":
            _log(f"섹션 {sid} 삭제 표시")
            overrides[sid] = None
            continue

        # 원본 헤더 보존 (재부착용), 비교/채점은 본문만 사용
        old_header: str = old_text.split("\n")[0]
        old_body: str = _body_only(old_text)

        prev_sec = sec_map.get(sid - 1)
        next_sec = sec_map.get(sid + 1)
        ctx_prev = prev_sec["text"] if prev_sec else ""
        ctx_next = next_sec["text"] if next_sec else ""

        regen_kwargs: dict = dict(
            section_id=sid,
            mode=mode,
            context_prev=ctx_prev,
            context_next=ctx_next,
            source_excerpt=source_report,  # 원본 보고서 전체 내용 (근거 자료)
            current_section=old_text,       # 현재 섹션 기존 출력 (개선 대상)
            user_instructions=extra,
        )

        # LLM 출력에서 헤더 제거 → 본문만 추출
        first_attempt = _body_only(regenerate(**regen_kwargs))

        # accept_or_reject: 본문끼리 비교 (길이·점수 모두 본문 기준)
        regen_fn: Callable[[], str] = lambda kw=regen_kwargs: _body_only(regenerate(**kw))
        accepted_body = accept_or_reject(old_body, first_attempt, sid, regen_fn=regen_fn)

        # 원본 헤더 재부착 → 헤더 무결성 보장
        overrides[sid] = old_header + "\n\n" + accepted_body

    result_text = _reconstruct_script(script_text, sections, overrides)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(result_text, encoding="utf-8")
    _log(f"저장 완료: {out_path} ({len(overrides)}개 섹션 처리)")
    return out_path


def _next_version(iterations_dir: Path) -> int:
    """work/iterations/ 내 최대 버전 번호 + 1을 반환한다."""
    if not iterations_dir.exists():
        return 2
    versions = []
    for d in iterations_dir.iterdir():
        m = re.match(r"^v(\d+)$", d.name)
        if m and d.is_dir():
            versions.append(int(m.group(1)))
    return max(versions) + 1 if versions else 2


def main() -> None:
    p = argparse.ArgumentParser(
        prog="regen_section.py",
        description="S3.5 — regen_tasks.json 에 따라 섹션을 재생성하고 채점 기반으로 수용/거절한다.",
    )
    p.add_argument(
        "--tasks",
        default=str(WORK_DIR / "regen_tasks.json"),
        metavar="FILE",
        help="regen_tasks.json 경로",
    )
    p.add_argument(
        "--script",
        default=str(WORK_DIR / "scripts" / "script.md"),
        metavar="FILE",
        help="기준 script.md 경로",
    )
    p.add_argument(
        "--out",
        default=None,
        metavar="FILE",
        help="출력 script.md 경로 (기본: work/iterations/v{n+1}/script.md)",
    )
    p.add_argument(
        "--no-symlink",
        action="store_true",
        help="work/latest 심볼릭 링크 갱신 안 함",
    )
    args = p.parse_args()

    tasks_path = Path(args.tasks)
    if not tasks_path.exists():
        _log(f"regen_tasks.json 없음: {tasks_path}", "error")
        sys.exit(1)

    script_path = Path(args.script)
    if not script_path.exists():
        _log(f"script.md 없음: {script_path}", "error")
        sys.exit(1)

    # v1 에 원본 script.md 가 없으면 복사
    iter_base = WORK_DIR / "iterations"
    v1_dir = iter_base / "v1"
    v1_script = v1_dir / "script.md"
    if not v1_script.exists():
        v1_dir.mkdir(parents=True, exist_ok=True)
        v1_script.write_text(script_path.read_text(encoding="utf-8"), encoding="utf-8")
        _log(f"원본 script.md → {v1_script}")

    # 출력 경로 결정
    if args.out:
        out_path = Path(args.out)
    else:
        ver = _next_version(iter_base)
        out_path = iter_base / f"v{ver}" / "script.md"

    run_tasks(tasks_path=tasks_path, script_path=script_path, out_path=out_path)

    # work/latest 심볼릭 링크 갱신
    if not args.no_symlink:
        latest = WORK_DIR / "latest"
        target = out_path.parent.resolve()
        if latest.is_symlink() or latest.exists():
            latest.unlink()
        latest.symlink_to(target)
        _log(f"work/latest → {target}")


if __name__ == "__main__":
    main()
