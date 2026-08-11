"""§ 13.7 — RAG R1 프롬프트 주입: top-k chunk를 writer 프롬프트에 삽입.

사용:
  from pipelines.rag_inject import inject_into_writer_prompt
  prompt = inject_into_writer_prompt(prompt, query, k=5)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

try:
    from rich.console import Console
    _console = Console(stderr=True)
    def _log(msg: str, level: str = "info") -> None:
        color = {"info": "green", "warning": "yellow", "error": "red", "success": "cyan"}.get(level, "white")
        _console.print(f"[{color}][rag_inject][/{color}] {msg}")
except ImportError:
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO)
    def _log(msg: str, level: str = "info") -> None:  # type: ignore[misc]
        getattr(_logging, level, _logging.info)(f"[rag_inject] {msg}")

# rag_query 임포트 경로 설정
_PIPELINES_DIR = Path(__file__).parent
if str(_PIPELINES_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINES_DIR))


def _build_rag_block(chunks: list[dict]) -> str:
    """검색된 chunks를 RAG_PROMPT_BLOCK 형식으로 변환한다."""
    lines = [
        "---",
        "## [RAG 참고 자료 — 이하 내용을 참고하되 그대로 복사하지 말 것]",
        "",
    ]
    for i, c in enumerate(chunks, 1):
        layer = c.get("layer", "")
        title = c.get("title", "").strip()
        source = c.get("source", "").strip()
        text = c.get("text", "").strip()
        score = c.get("score", 0.0)

        lines.append(f"### [{i}] [{layer}] {title}")
        lines.append(f"출처: {source} | MMR score: {score}")
        lines.append("")
        lines.append(text)
        lines.append("")

    lines += [
        "---",
        "",
    ]
    return "\n".join(lines)


def inject_into_writer_prompt(prompt: str, query: str, k: int = 5) -> str:
    """RAG 검색 결과를 writer 프롬프트 앞에 삽입한다.

    RAG_ENABLED=0이면 즉시 원본 prompt를 반환한다.
    Chroma가 비어 있거나 오류 발생 시 원본 prompt를 반환한다.
    """
    if os.getenv("RAG_ENABLED", "1") != "1":
        return prompt

    try:
        from rag_query import query as rag_query
    except ImportError:
        try:
            from pipelines.rag_query import query as rag_query  # type: ignore[no-redef]
        except ImportError:
            _log("rag_query 모듈을 찾을 수 없음 — RAG 스킵", "warning")
            return prompt

    try:
        chunks = rag_query(query, k=k)
    except Exception as exc:
        _log(f"RAG 쿼리 실패 — 원본 프롬프트 유지: {exc}", "warning")
        return prompt

    if not chunks:
        _log("RAG: 관련 chunk 없음 — 원본 프롬프트 유지", "warning")
        return prompt

    rag_block = _build_rag_block(chunks)

    _log(
        f"RAG: top-{len(chunks)} chunks injected | "
        + " | ".join(f"[{c['layer']}] {c['title'][:30]}" for c in chunks),
        "success",
    )

    return rag_block + prompt


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="RAG inject 테스트")
    p.add_argument("query", help="검색 쿼리")
    p.add_argument("--k", type=int, default=5)
    args = p.parse_args()

    sample_prompt = "[WRITER PROMPT PLACEHOLDER]\n주어진 섹션을 재생성하세요."
    result = inject_into_writer_prompt(sample_prompt, args.query, k=args.k)
    print(result)
