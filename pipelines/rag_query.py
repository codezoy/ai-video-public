"""§ 13.6 — RAG R1 검색: top-k retrieval + MMR(λ=0.5) + layer 필터.

사용:
  python pipelines/rag_query.py "쇼츠 알고리즘 핵심 지표" --k 5
  python pipelines/rag_query.py "콘텐츠 구조" --k 5 --layer L1
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

try:
    from rich.console import Console
    _console = Console(stderr=True)
    def _log(msg: str, level: str = "info") -> None:
        color = {"info": "green", "warning": "yellow", "error": "red", "success": "cyan"}.get(level, "white")
        _console.print(f"[{color}][rag_query][/{color}] {msg}")
except ImportError:
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO)
    def _log(msg: str, level: str = "info") -> None:  # type: ignore[misc]
        getattr(_logging, level, _logging.info)(f"[rag_query] {msg}")

ROOT = Path(os.environ.get("PROJECT_ROOT", Path(__file__).parent.parent))
RAG_DIR = ROOT / "rag"
CHROMA_DIR = RAG_DIR / "chroma"

_raw_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_HOST: str = _raw_host if _raw_host.startswith("http") else f"http://{_raw_host}"
EMBED_MODEL: str = os.getenv("RAG_EMBED_MODEL", "bge-m3")
COLLECTION_NAME: str = os.getenv("RAG_COLLECTION", "ai_video_rag")

MMR_LAMBDA: float = 0.5  # MMR diversity weight


# ── 임베딩 (rag_ingest와 동일 방식) ──────────────────────────────────────────

def _embed_one(text: str) -> list[float]:
    import urllib.request
    payload = json.dumps({"model": EMBED_MODEL, "input": [text]}).encode()
    req = urllib.request.Request(
        f"{OLLAMA_HOST}/api/embed",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = json.loads(resp.read())
    embeddings = body.get("embeddings", [])
    if not embeddings:
        raise ValueError(f"Ollama embed returned empty: {body}")
    return list(embeddings[0])


# ── Chroma 컬렉션 ─────────────────────────────────────────────────────────────

def _get_collection() -> Any:
    import chromadb
    from chromadb import EmbeddingFunction, Documents, Embeddings  # type: ignore[import]

    class OllamaEmbedder(EmbeddingFunction):  # type: ignore[misc]
        def __call__(self, input: Documents) -> Embeddings:  # type: ignore[override]
            import urllib.request
            texts = list(input)
            payload = json.dumps({"model": EMBED_MODEL, "input": texts}).encode()
            req = urllib.request.Request(
                f"{OLLAMA_HOST}/api/embed",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read())
            return [list(e) for e in body.get("embeddings", [])]  # type: ignore[return-value]

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=OllamaEmbedder(),
        metadata={"hnsw:space": "cosine"},
    )


# ── 코사인 유사도 ─────────────────────────────────────────────────────────────

def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# ── MMR 재정렬 ────────────────────────────────────────────────────────────────

def _mmr(
    query_emb: list[float],
    candidates: list[dict],
    k: int,
    lam: float = MMR_LAMBDA,
) -> list[dict]:
    """Maximal Marginal Relevance: λ × relevance − (1-λ) × max_similarity_to_selected."""
    selected: list[dict] = []
    remaining = list(candidates)

    while remaining and len(selected) < k:
        best_score = -float("inf")
        best_idx = 0

        for i, cand in enumerate(remaining):
            relevance = _cosine(query_emb, cand["embedding"])
            if selected:
                redundancy = max(_cosine(cand["embedding"], s["embedding"]) for s in selected)
            else:
                redundancy = 0.0
            score = lam * relevance - (1 - lam) * redundancy
            if score > best_score:
                best_score = score
                best_idx = i

        chosen = remaining.pop(best_idx)
        chosen["mmr_score"] = best_score
        selected.append(chosen)

    return selected


# ── 공개 진입점 ───────────────────────────────────────────────────────────────

def query(
    query_text: str,
    k: int = 5,
    layer_filter: str | None = None,
    candidate_multiplier: int = 3,
) -> list[dict]:
    """top-k 검색 + MMR 재정렬.

    Returns: list of {text, source, layer, title, score}
    """
    if not CHROMA_DIR.exists():
        _log("rag/chroma 없음 — rag_ingest.py를 먼저 실행하세요", "warning")
        return []

    try:
        collection = _get_collection()
    except Exception as exc:
        _log(f"Chroma 연결 실패: {exc}", "error")
        return []

    total_docs = collection.count()
    if total_docs == 0:
        _log("컬렉션이 비어 있음 — rag_ingest.py를 먼저 실행하세요", "warning")
        return []

    try:
        query_emb = _embed_one(query_text)
    except Exception as exc:
        _log(f"쿼리 임베딩 실패: {exc}", "error")
        return []

    # 후보를 k의 candidate_multiplier배로 넓게 가져와 MMR에 제공
    n_results = min(k * candidate_multiplier, total_docs)
    where_clause: dict | None = {"layer": layer_filter} if layer_filter else None

    try:
        results = collection.query(
            query_embeddings=[query_emb],
            n_results=n_results,
            where=where_clause,
            include=["documents", "metadatas", "embeddings", "distances"],
        )
    except Exception as exc:
        _log(f"Chroma 쿼리 실패: {exc}", "error")
        return []

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    embs = results.get("embeddings", [[]])[0]
    dists = results.get("distances", [[]])[0]

    candidates = [
        {
            "text": docs[i],
            "source": metas[i].get("source", ""),
            "layer": metas[i].get("layer", ""),
            "title": metas[i].get("title", ""),
            "embedding": list(embs[i]),
            "distance": dists[i],
        }
        for i in range(len(docs))
    ]

    selected = _mmr(query_emb, candidates, k=k)

    output = [
        {
            "text": c["text"],
            "source": c["source"],
            "layer": c["layer"],
            "title": c["title"],
            "score": round(c.get("mmr_score", 0.0), 4),
        }
        for c in selected
    ]

    _log(f"쿼리 완료: {len(output)}개 chunks 반환 (총 DB={total_docs}, layer_filter={layer_filter})")
    return output


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(description="RAG R1 검색")
    p.add_argument("query_text", help="검색할 텍스트")
    p.add_argument("--k", type=int, default=5, help="반환할 청크 수")
    p.add_argument("--layer", choices=["L1", "L2", "L3"], default=None, help="레이어 필터")
    args = p.parse_args()

    results = query(args.query_text, k=args.k, layer_filter=args.layer)
    for i, r in enumerate(results, 1):
        print(f"\n[{i}] [{r['layer']}] {r['title']} (score={r['score']})")
        print(f"    source: {r['source']}")
        print(f"    {r['text'][:200]}{'…' if len(r['text']) > 200 else ''}")


if __name__ == "__main__":
    main()
