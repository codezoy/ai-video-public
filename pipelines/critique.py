"""S3 Critique — 자동 채점 결과에 사용자 섹션 피드백을 병합해 regen_tasks를 구성한다.

산출물: work/regen_tasks.json
참조: 플레이북 v2 섹션 4.2 (사용자 피드백), 섹션 4.3 (판정 종합)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

try:
    from rich.console import Console
    _console = Console()
    _err = Console(stderr=True)
    def _log(msg: str, level: str = "info") -> None:
        color = {"info": "green", "warning": "yellow", "error": "red"}.get(level, "white")
        _err.print(f"[{color}][critique][/{color}] {msg}")
    def _print(msg: str) -> None:
        _console.print(msg)
except ImportError:
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO)
    def _log(msg: str, level: str = "info") -> None:  # type: ignore[misc]
        getattr(_logging, level, _logging.info)(f"[critique] {msg}")
    def _print(msg: str) -> None:  # type: ignore[misc]
        print(msg)

ROOT = Path(os.environ.get("PROJECT_ROOT", Path(__file__).parent.parent))
WORK_DIR = Path(os.getenv("WORK_DIR", str(ROOT / "work")))
DEFAULT_REGEN_FILE = WORK_DIR / "regen_tasks.json"

# 키 입력 → 피드백 코드 매핑 (플레이북 4.2)
_KEY_MAP: dict[str, str] = {
    "O": "OK",
    "D": "DEEP",
    "S": "SHRINK",
    "K": "SKIP",
    "E": "EXAMPLE",
    "R": "REWRITE",
}

# 피드백 코드 → 재생성 mode 매핑
_MODE_MAP: dict[str, str] = {
    "DEEP": "deep",
    "SHRINK": "shrink",
    "SKIP": "delete",
    "EXAMPLE": "example_only",
    "REWRITE": "rewrite",
}

# 피드백 코드별 extra_instructions
_EXTRA: dict[str, str] = {
    "DEEP": (
        "4블록 모두 포함 (정의·왜 나뉘는가·실제 사례·연결). "
        "비교·반례·흔한 오해 1개 추가. 실제 사례 2개 이상."
    ),
    "SHRINK": "현재 분량의 1/3로 압축. 핵심 정의만 남기고 나머지 삭제.",
    "EXAMPLE": (
        "기존 섹션 구조 유지. [실제 사례] 블록만 추가: "
        "명령어·버전·실패 경험 중 1개 이상 포함."
    ),
    "REWRITE": (
        "전면 재작성. 건물/건축/층/기초 비유 사용 금지. "
        "실제 사례 2개 이상 포함."
    ),
}

_AUTO_EXTRA = (
    "4블록 모두 포함 (정의·구성요소 분해·실제 사례·흐름 연결). "
    "실제 사례 2개 이상."
)


def collect_user_feedback(critique: dict) -> dict:
    """CLI interactive 로 섹션별 6종 단축 피드백(O/D/S/K/E/R)을 수집한다.

    Args:
        critique: llm_judge.score_script() 가 반환(또는 저장)한 critique 딕셔너리.
                  {"overall": float, "sections": [...]} 형식.

    Returns:
        {section_id(int): "OK"|"DEEP"|"SHRINK"|"SKIP"|"EXAMPLE"|"REWRITE"}

    Notes:
        각 섹션에 대해 자동 점수(5축)와 issues를 표시한 뒤 키 입력을 받는다.
        키 매핑:
          O → OK, D → DEEP, S → SHRINK, K → SKIP, E → EXAMPLE, R → REWRITE
        잘못된 키 입력 시 재질의한다.
    """
    sections = critique.get("sections", [])
    result: dict[int, str] = {}

    _print("\n[S3 Critique — 섹션별 피드백 수집]")
    _print("O=OK  D=DEEP  S=SHRINK  K=SKIP  E=EXAMPLE  R=REWRITE\n")

    for sec in sections:
        sid: int = sec["id"]
        title: str = sec.get("title", f"섹션 {sid}")
        scores: dict = sec.get("scores", {})
        issues: list = sec.get("issues", [])
        needs: bool = sec.get("needs_regen", False)

        _print(f"{'─' * 60}")
        _print(f"섹션 {sid}: {title}")
        score_str = "  ".join(f"{k}={v}" for k, v in scores.items())
        _print(f"  점수: {score_str}")
        if needs:
            _print("  ⚠️  자동 재생성 대상 (avg<3.0 또는 concrete<2)")
        for issue in issues:
            _print(f"  · {issue}")

        while True:
            try:
                raw = input("  피드백 [O/D/S/K/E/R]: ").strip().upper()
            except (EOFError, KeyboardInterrupt):
                print()
                _log("입력 중단. 종료합니다.", "warning")
                sys.exit(0)
            if raw in _KEY_MAP:
                result[sid] = _KEY_MAP[raw]
                break
            _print(f"  잘못된 입력 '{raw}'. O/D/S/K/E/R 중 하나를 입력하세요.")

    return result


def merge_with_auto(auto: dict, user: dict, out_path: Path | None = None) -> list[dict]:
    """자동 채점 결과(auto)와 사용자 피드백(user)을 병합해 regen_tasks 리스트를 반환하고 저장한다.

    Args:
        auto: llm_judge.score_script() 반환값 (critique 딕셔너리).
        user: collect_user_feedback() 반환값 ({section_id: feedback_code}).
        out_path: 출력 경로 (기본: work/regen_tasks.json).

    Returns:
        플레이북 4.3 의 regen_tasks 포맷:
        [
          {
            "section_id": int,
            "reason": str,
            "mode": str,           # "full"|"deep"|"shrink"|"delete"|"example_only"|"rewrite"
            "extra_instructions": str,
          },
          ...
        ]

    Notes:
        결과는 work/regen_tasks.json 에 {"regen_tasks": [...]} 포맷으로 저장된다.
        user 피드백 "OK" 이고 auto needs_regen=False 이면 해당 섹션은 제외.
        user 피드백 "SKIP" 이면 mode="delete".
    """
    out_file = out_path or DEFAULT_REGEN_FILE
    sections = auto.get("sections", [])
    tasks: list[dict] = []

    for sec in sections:
        sid: int = sec["id"]
        auto_needs: bool = sec.get("needs_regen", False)
        scores: dict = sec.get("scores", {})

        # auto 재생성 이유 조각
        auto_reason = ""
        if auto_needs:
            bad = [f"{k}={v}" for k, v in scores.items() if v < 3]
            auto_reason = f"auto:{','.join(bad)}" if bad else "auto:low_avg"

        # user dict 키가 str일 수도 있음 (JSON 로드 시 대비)
        user_code: str = user.get(sid) or user.get(str(sid)) or "OK"

        # SKIP 은 무조건 우선 (auto 무관)
        if user_code == "SKIP":
            tasks.append({
                "section_id": sid,
                "reason": "user:SKIP",
                "mode": "delete",
                "extra_instructions": "",
            })
            continue

        # 아무 작업 없음: OK이고 자동 재생성도 불필요
        if user_code == "OK" and not auto_needs:
            continue

        # reason 구성
        reason_parts = [p for p in [
            auto_reason,
            f"user:{user_code}" if user_code != "OK" else "",
        ] if p]
        reason = " + ".join(reason_parts)

        # mode 결정 — 플레이북 4.3 예시 기반
        if user_code == "OK":
            # auto needs_regen만 해당 → full
            mode = "full"
            extra = _AUTO_EXTRA
        elif user_code == "DEEP":
            # auto도 필요하면 full로 업그레이드, 아니면 deep
            mode = "full" if auto_needs else "deep"
            extra = _EXTRA["DEEP"]
            if auto_needs:
                extra = f"{extra} {_AUTO_EXTRA}".strip()
        else:
            mode = _MODE_MAP[user_code]
            extra = _EXTRA.get(user_code, "")
            # REWRITE는 auto extra 중복 불필요, 나머지는 추가
            if auto_needs and user_code != "REWRITE":
                extra = f"{extra} {_AUTO_EXTRA}".strip()

        tasks.append({
            "section_id": sid,
            "reason": reason,
            "mode": mode,
            "extra_instructions": extra,
        })

    out_data = {"regen_tasks": tasks}
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(out_data, ensure_ascii=False, indent=2), encoding="utf-8")
    _log(f"저장 완료: {out_file} ({len(tasks)}개 태스크)")
    return tasks


def main() -> None:
    p = argparse.ArgumentParser(
        prog="critique.py",
        description="S3 Critique — critique.json + 사용자 피드백 → work/regen_tasks.json 생성.",
    )
    p.add_argument("--critique", required=True, metavar="FILE", help="입력 critique.json 경로")
    p.add_argument("--out", default=str(DEFAULT_REGEN_FILE), metavar="FILE", help="출력 regen_tasks.json 경로")
    p.add_argument("--skip-user", action="store_true", help="사용자 피드백 수집 건너뜀 (자동 판정만 사용)")
    args = p.parse_args()

    critique_path = Path(args.critique)
    if not critique_path.exists():
        _log(f"입력 파일 없음: {critique_path}", "error")
        sys.exit(1)

    critique = json.loads(critique_path.read_text(encoding="utf-8"))
    user_fb: dict = {}
    if not args.skip_user:
        user_fb = collect_user_feedback(critique)
    merge_with_auto(critique, user_fb, out_path=Path(args.out))


if __name__ == "__main__":
    main()
