"""LLM-as-Judge — 대본 섹션을 5축으로 자동 채점한다.

산출물: work/critique.json
참조: 플레이북 v2 섹션 4.1 (자동 채점), 부록 B (Judge 프롬프트 스켈레톤)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

try:
    from rich.console import Console
    _console = Console(stderr=True)
    def _log(msg: str, level: str = "info") -> None:
        color = {"info": "green", "warning": "yellow", "error": "red"}.get(level, "white")
        _console.print(f"[{color}][llm_judge][/{color}] {msg}")
except ImportError:
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO)
    def _log(msg: str, level: str = "info") -> None:  # type: ignore[misc]
        getattr(_logging, level, _logging.info)(f"[llm_judge] {msg}")

ROOT = Path(os.environ.get("PROJECT_ROOT", Path(__file__).parent.parent))
WORK_DIR = Path(os.getenv("WORK_DIR", str(ROOT / "work")))
DEFAULT_CRITIQUE_FILE = WORK_DIR / "critique.json"

# 부록 B 스켈레톤 — 이 상수를 수정하면 DoD 불통과 (문자열 diff 검사 대상)
JUDGE_PROMPT = """당신은 기술 강의 대본 품질 평가 전문가다.
아래 섹션을 5가지 축으로 0~5점 채점하라.

[축 1 — Clarity 정의 명확성]
5점: 추상어·전문용어 뒤에 해설이 있어 30초 내 이해 가능
3점: 정의는 있으나 해설 불충분
0점: 정의 없음 또는 용어만 나열

[축 2 — Breakdown 구성요소 분해]
5점: 2~4개 구성요소로 나뉘고 각각 '왜 별도인지' 설명
3점: 구성요소 나열만 있음
0점: 분해 없음

[축 3 — Concrete 실제 사례]
5점: 이름·숫자·버전·명령어·실패 경험 중 2개 이상 포함
3점: 사례 있으나 추상적
0점: 사례 전무

[축 4 — Flow 흐름 연결]
5점: 이전/다음 섹션과 "~이 해결되지 않으면 ~가 필요하다" 형태 이음말 존재
3점: 단순 전환어만
0점: 독립 나열

[축 5 — Redundancy 중복 방지 (역점수)]
5점: 같은 비유·표현 반복 없음
3점: 1~2회 반복
0점: 3회 이상 반복

[출력 형식 — 반드시 JSON 만]
{"scores":{"clarity":N,"breakdown":N,"concrete":N,"flow":N,"redundancy":N},
 "issues":["문제 요약 1", "문제 요약 2"],
 "needs_regen": true|false }

[섹션 원문]
{{SECTION_TEXT}}"""

_SCORE_AXES = ("clarity", "breakdown", "concrete", "flow", "redundancy")


def _parse_judge_json(text: str) -> dict:
    """LLM 응답에서 JSON 객체를 추출한다. 마크다운 코드 블록 제거 후 파싱."""
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"\s*```$", "", text.strip(), flags=re.MULTILINE)
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    raise ValueError(f"JSON 파싱 실패. LLM 출력 (앞 300자):\n{text[:300]}")


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


def score_section(section_text: str, section_id: int) -> dict:
    """단일 섹션을 LLM(role='judge')으로 5축 채점한다.

    Args:
        section_text: 채점 대상 섹션 전문.
        section_id: 섹션 순번 (1-indexed).

    Returns:
        {
          "scores": {
            "clarity": int,      # 0~5
            "breakdown": int,    # 0~5
            "concrete": int,     # 0~5
            "flow": int,         # 0~5
            "redundancy": int,   # 0~5 (역점수, 5=중복 없음)
          },
          "issues": [str, ...],
          "needs_regen": bool,   # avg<3.0 OR concrete<2 (Python 계산, LLM 값 오버라이드)
        }

    Notes:
        판정 프롬프트는 플레이북 부록 B 스켈레톤을 그대로 사용한다.
        CLI-only 라우터 정책에 따라 gemini_cli → codex_cli 순서로 호출한다.
    """
    try:
        from llm_client import generate  # type: ignore[import]
    except ImportError:
        from pipelines.llm_client import generate  # type: ignore[import]

    prompt = JUDGE_PROMPT.replace("{{SECTION_TEXT}}", section_text)
    _log(f"섹션 {section_id} 채점 중 …")

    last_exc: Exception | None = None
    parsed: dict = {}
    for attempt in range(3):
        try:
            raw = generate(prompt, role="judge")  # type: ignore[arg-type]
            parsed = _parse_judge_json(raw)
            break
        except Exception as exc:
            last_exc = exc
            _log(f"섹션 {section_id} 시도 {attempt + 1}/3 실패: {exc}", "warning")
    else:
        raise RuntimeError(f"섹션 {section_id} 채점 3회 모두 실패: {last_exc}") from last_exc

    scores = {ax: int(parsed.get("scores", {}).get(ax, 0)) for ax in _SCORE_AXES}
    score_values = list(scores.values())
    avg = sum(score_values) / len(score_values) if score_values else 0.0
    needs_regen = avg < 3.0 or scores["concrete"] < 2

    _log(f"섹션 {section_id} 완료: avg={avg:.1f} concrete={scores['concrete']} needs_regen={needs_regen}")

    return {
        "scores": scores,
        "issues": parsed.get("issues", []),
        "needs_regen": needs_regen,
    }


def score_script(
    script_path: Path,
    out_path: Path | None = None,
    iter_dir: Path | None = None,
) -> dict:
    """대본 전체를 섹션별로 파싱 후 병렬(최대 3 동시) 채점하고 critique.json으로 저장한다.

    Args:
        script_path: work/script.md 경로.
        out_path: 기본 출력 경로 (기본: work/critique.json).
        iter_dir: 이터레이션 디렉토리 (예: work/iterations/v2).
                  지정 시 iter_dir/critique.json 에도 함께 저장한다.

    Returns:
        {
          "overall": float,
          "sections": [{"id", "title", "scores", "issues", "needs_regen"}, ...],
        }
    """
    out_file = out_path or DEFAULT_CRITIQUE_FILE
    script_text = script_path.read_text(encoding="utf-8")
    sections = _parse_sections(script_text)

    if not sections:
        _log("섹션을 찾을 수 없습니다. ## 또는 ### 헤더가 있는지 확인하세요.", "error")
        sys.exit(1)

    _log(f"섹션 {len(sections)}개 파싱 완료, 병렬 채점 시작 (max_workers=3) …")

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_to_sec = {
            executor.submit(score_section, s["text"], s["id"]): s
            for s in sections
        }
        for future in as_completed(future_to_sec):
            sec = future_to_sec[future]
            try:
                scored = future.result()
            except Exception as exc:
                _log(f"섹션 {sec['id']} 채점 실패: {exc}", "error")
                sys.exit(1)
            results.append({
                "id": sec["id"],
                "title": sec["title"],
                **scored,
            })

    results.sort(key=lambda x: x["id"])

    all_avgs: list[float] = []
    for r in results:
        vals = list(r["scores"].values())
        all_avgs.append(sum(vals) / len(vals) if vals else 0.0)
    overall = round(sum(all_avgs) / len(all_avgs), 2) if all_avgs else 0.0

    critique: dict = {"overall": overall, "sections": results}
    serialized = json.dumps(critique, ensure_ascii=False, indent=2)

    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(serialized, encoding="utf-8")
    _log(f"저장 완료: {out_file} (overall={overall}  섹션 수={len(results)})")

    if iter_dir is not None:
        iter_critique = iter_dir / "critique.json"
        iter_dir.mkdir(parents=True, exist_ok=True)
        iter_critique.write_text(serialized, encoding="utf-8")
        _log(f"이터레이션 저장 완료: {iter_critique}")

    return critique


def main() -> None:
    p = argparse.ArgumentParser(
        prog="llm_judge.py",
        description="LLM-as-Judge — work/script.md 를 5축 채점해 work/critique.json을 생성한다.",
    )
    p.add_argument("--script", required=True, metavar="FILE", help="입력 script.md 경로")
    p.add_argument("--out", default=str(DEFAULT_CRITIQUE_FILE), metavar="FILE", help="출력 critique.json 경로")
    p.add_argument("--iter-dir", default=None, metavar="DIR", help="이터레이션 디렉토리 (예: work/iterations/v2). 지정 시 해당 경로에도 저장.")
    args = p.parse_args()

    script_path = Path(args.script)
    if not script_path.exists():
        _log(f"입력 파일 없음: {script_path}", "error")
        sys.exit(1)

    iter_dir = Path(args.iter_dir) if args.iter_dir else None
    score_script(script_path, out_path=Path(args.out), iter_dir=iter_dir)


if __name__ == "__main__":
    main()
