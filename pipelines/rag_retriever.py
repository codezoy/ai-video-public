"""RAG Retriever — BM25 keyword search, API 호출 없음.

Ollama/Claude/OpenAI 의존 없이 로컬 파일 기반으로 top-K 검색을 수행한다.

검색 소스 우선순위:
  L1 — rag/sources/playbooks/  (플레이북)
  L2 — work/content_adapter/   (과거 Learning Brief / Scene Plan)
  L3 — docs/reports/           (과거 성공 영상 보고서)
  L4 — rag/sources/external/   (기타 문서)

사용:
  from pipelines.rag_retriever import search
  results = search(["Audit PASS", "Visual Fail"], k=5)
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

try:
    from rich.console import Console
    _console = Console(stderr=True)

    def _log(msg: str, level: str = "info") -> None:
        color = {"info": "green", "warning": "yellow", "error": "red", "success": "cyan"}.get(level, "white")
        _console.print(f"[{color}][rag_retriever][/{color}] {msg}")
except ImportError:
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO)

    def _log(msg: str, level: str = "info") -> None:  # type: ignore[misc]
        getattr(_logging, level, _logging.info)(f"[rag_retriever] {msg}")


ROOT = Path(os.environ.get("PROJECT_ROOT", Path(__file__).parent.parent))
WORK_DIR = Path(os.getenv("WORK_DIR", str(ROOT / "work")))
RAG_DIR = ROOT / "rag"
DOCS_DIR = ROOT / "docs"

# BM25 parameters
_K1 = 1.5
_B = 0.75
_MIN_CHUNK_LEN = 30


# ── Tokenizer ─────────────────────────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    """공백/구두점 기준 토큰화 + 소문자. 한글 2글자 이상 bi-gram 포함."""
    text_lower = text.lower()
    words = re.findall(r"[a-z0-9]+|[가-힣]+", text_lower)
    # 한글 단어에서 2-gram 추가 (검색 recall 향상)
    bigrams: list[str] = []
    for w in words:
        if len(w) >= 4 and re.match(r"[가-힣]+", w):
            for i in range(len(w) - 1):
                bigrams.append(w[i:i+2])
    return words + bigrams


# ── Document Loader ───────────────────────────────────────────────────────────

def _layer_of_path(path: Path) -> str:
    parts = path.parts
    if "playbooks" in parts:
        return "L1"
    if "content_adapter" in parts:
        return "L2"
    if "reports" in parts:
        return "L3"
    if "external" in parts:
        return "L4"
    return "L4"


def _load_docs() -> list[dict[str, str]]:
    """검색 소스 디렉토리에서 문서를 로딩한다."""
    sources: list[tuple[str, Path, str]] = [
        ("L1", RAG_DIR / "sources" / "playbooks", "**/*.md"),
        ("L2", WORK_DIR / "content_adapter", "*.json"),
        ("L3", DOCS_DIR / "reports", "*.md"),
        ("L4", RAG_DIR / "sources" / "external", "**/*.md"),
    ]

    docs: list[dict[str, str]] = []
    for layer, base_dir, glob_pat in sources:
        if not base_dir.exists():
            continue
        for fpath in sorted(base_dir.glob(glob_pat)):
            if not fpath.is_file():
                continue
            try:
                raw = fpath.read_text(encoding="utf-8")
            except Exception:
                continue

            if fpath.suffix == ".json":
                # JSON 파일은 텍스트로 평탄화
                try:
                    obj = json.loads(raw)
                    raw = _flatten_json(obj)
                except Exception:
                    pass

            # 헤더 단위 분할
            chunks = _split_chunks(raw, str(fpath.name), layer)
            docs.extend(chunks)

    return docs


def _flatten_json(obj: Any, prefix: str = "") -> str:
    """JSON 객체를 검색 가능한 텍스트로 평탄화한다."""
    lines: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            lines.append(f"{k}: {_flatten_json(v)}")
    elif isinstance(obj, list):
        for item in obj:
            lines.append(_flatten_json(item))
    else:
        return str(obj)
    return "\n".join(lines)


def _split_chunks(text: str, source: str, layer: str) -> list[dict[str, str]]:
    """## / ### 헤더 기준으로 chunk 분할. 헤더 없으면 전체를 하나의 chunk로."""
    parts = re.split(r"\n(?=#{1,3} )", text.strip())
    chunks: list[dict[str, str]] = []

    for part in parts:
        part = part.strip()
        if len(part) < _MIN_CHUNK_LEN:
            continue
        lines = part.split("\n")
        title = re.sub(r"^#{1,3} ", "", lines[0]).strip() if lines else ""
        body = "\n".join(lines[1:]).strip()
        full_text = f"{title}\n{body}" if body else title

        chunks.append({
            "text": full_text,
            "title": title,
            "source": source,
            "layer": layer,
        })

    return chunks if chunks else [{"text": text[:2000], "title": source, "source": source, "layer": layer}]


# ── BM25 ──────────────────────────────────────────────────────────────────────

class BM25:
    def __init__(self, docs: list[dict[str, str]]) -> None:
        self.docs = docs
        self._tokenized = [_tokenize(d["text"]) for d in docs]
        self._df: Counter = Counter()
        for tokens in self._tokenized:
            for t in set(tokens):
                self._df[t] += 1
        self._n = len(docs)
        self._avgdl = (
            sum(len(t) for t in self._tokenized) / max(self._n, 1)
        )

    def _idf(self, term: str) -> float:
        df = self._df.get(term, 0)
        return math.log((self._n - df + 0.5) / (df + 0.5) + 1)

    def score(self, query_tokens: list[str], doc_idx: int) -> float:
        tokens = self._tokenized[doc_idx]
        tf_map = Counter(tokens)
        dl = len(tokens)
        score = 0.0
        for term in query_tokens:
            if term not in tf_map:
                continue
            idf = self._idf(term)
            tf = tf_map[term]
            num = tf * (_K1 + 1)
            denom = tf + _K1 * (1 - _B + _B * dl / max(self._avgdl, 1))
            score += idf * num / denom
        return score

    def search(self, queries: list[str], k: int = 5) -> list[dict[str, Any]]:
        """멀티 쿼리: 각 쿼리 점수를 합산하여 상위 k개 반환."""
        query_tokens: list[str] = []
        for q in queries:
            query_tokens.extend(_tokenize(q))

        scores: list[tuple[float, int]] = []
        for i in range(self._n):
            s = self.score(query_tokens, i)
            if s > 0:
                scores.append((s, i))

        scores.sort(key=lambda x: x[0], reverse=True)
        results: list[dict[str, Any]] = []
        seen_sources: set[str] = set()

        for score, idx in scores[:k * 3]:  # 다양성을 위해 3배 후보
            doc = self.docs[idx]
            key = f"{doc['source']}::{doc['title']}"
            if key in seen_sources:
                continue
            seen_sources.add(key)
            results.append({
                "text": doc["text"][:500],
                "title": doc["title"],
                "source": doc["source"],
                "layer": doc["layer"],
                "score": round(score, 4),
            })
            if len(results) >= k:
                break

        return results


# ── 공개 인터페이스 ───────────────────────────────────────────────────────────

_bm25_cache: BM25 | None = None


def _get_bm25() -> BM25:
    global _bm25_cache
    if _bm25_cache is None:
        docs = _load_docs()
        if not docs:
            _log("검색 소스 없음 — 빈 인덱스", "warning")
            docs = [{"text": "placeholder", "title": "", "source": "", "layer": "L4"}]
        _bm25_cache = BM25(docs)
        _log(f"BM25 인덱스 구축 완료: {len(docs)}개 chunks")
    return _bm25_cache


def invalidate_cache() -> None:
    """인덱스 캐시를 초기화한다 (테스트/재인덱싱용)."""
    global _bm25_cache
    _bm25_cache = None


def search(
    queries: list[str],
    k: int = 5,
    layer_filter: str | None = None,
) -> list[dict[str, Any]]:
    """BM25 multi-query 검색.

    Args:
        queries: 검색 쿼리 리스트
        k: 반환할 결과 수
        layer_filter: L1/L2/L3/L4 필터 (None이면 전체)

    Returns:
        list of {text, title, source, layer, score}
    """
    bm25 = _get_bm25()
    results = bm25.search(queries, k=k * 2)  # 필터 여유분

    if layer_filter:
        results = [r for r in results if r["layer"] == layer_filter]

    return results[:k]


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="RAG Retriever — BM25 검색")
    p.add_argument("queries", nargs="+", help="검색 쿼리")
    p.add_argument("--k", type=int, default=5, help="반환 결과 수")
    p.add_argument("--layer", choices=["L1", "L2", "L3", "L4"], default=None)
    args = p.parse_args()

    results = search(args.queries, k=args.k, layer_filter=args.layer)
    for i, r in enumerate(results, 1):
        print(f"\n[{i}] [{r['layer']}] {r['title']} (score={r['score']})")
        print(f"    source: {r['source']}")
        print(f"    {r['text'][:200]}{'…' if len(r['text']) > 200 else ''}")
