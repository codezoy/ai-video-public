"""§ 13.5 — RAG R1 인덱싱: 헤더 단위 chunk + bge-m3(Ollama) embed + Chroma upsert.

증분 방식: rag/manifest.json에 SHA-256 해시를 기록하고 변경된 chunk만 upsert.

사용:
  python pipelines/rag_ingest.py            # L1 + L2 전체 인덱싱
  python pipelines/rag_ingest.py --l1-only  # L1(플레이북) 만
  python pipelines/rag_ingest.py --l2-only  # L2(고득점 섹션) 만
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

try:
    from rich.console import Console
    _console = Console(stderr=True)
    def _log(msg: str, level: str = "info") -> None:
        color = {"info": "green", "warning": "yellow", "error": "red", "success": "cyan"}.get(level, "white")
        _console.print(f"[{color}][rag_ingest][/{color}] {msg}")
except ImportError:
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO)
    def _log(msg: str, level: str = "info") -> None:  # type: ignore[misc]
        getattr(_logging, level, _logging.info)(f"[rag_ingest] {msg}")

ROOT = Path(os.environ.get("PROJECT_ROOT", Path(__file__).parent.parent))
WORK_DIR = Path(os.getenv("WORK_DIR", str(ROOT / "work")))
RAG_DIR = ROOT / "rag"
CHROMA_DIR = RAG_DIR / "chroma"
MANIFEST_PATH = RAG_DIR / "manifest.json"
SOURCES_DIR = RAG_DIR / "sources"

_raw_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_HOST: str = _raw_host if _raw_host.startswith("http") else f"http://{_raw_host}"
EMBED_MODEL: str = os.getenv("RAG_EMBED_MODEL", "bge-m3")
COLLECTION_NAME: str = os.getenv("RAG_COLLECTION", "ai_video_rag")

JUDGE_SCORE_THRESHOLD: float = 4.5  # section average score 기준


# ── Ollama 임베딩 ─────────────────────────────────────────────────────────────

def _embed_batch(texts: list[str]) -> list[list[float]]:
    """bge-m3(Ollama)으로 텍스트 배치를 임베딩한다."""
    payload = json.dumps({"model": EMBED_MODEL, "input": texts}).encode()
    req = urllib.request.Request(
        f"{OLLAMA_HOST}/api/embed",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = json.loads(resp.read())
    embeddings = body.get("embeddings", [])
    if not embeddings:
        raise ValueError(f"Ollama embed returned empty: {body}")
    return [list(e) for e in embeddings]


def _embed_one(text: str) -> list[float]:
    return _embed_batch([text])[0]


# ── Chroma 클라이언트 ──────────────────────────────────────────────────────────

def _get_collection() -> Any:
    """Chroma PersistentClient 및 컬렉션을 반환한다 (없으면 생성)."""
    import chromadb
    from chromadb import EmbeddingFunction, Documents, Embeddings  # type: ignore[import]

    class OllamaEmbedder(EmbeddingFunction):  # type: ignore[misc]
        def __call__(self, input: Documents) -> Embeddings:  # type: ignore[override]
            return _embed_batch(list(input))  # type: ignore[return-value]

    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=OllamaEmbedder(),
        metadata={"hnsw:space": "cosine"},
    )


# ── Manifest 관리 ─────────────────────────────────────────────────────────────

def _load_manifest() -> dict[str, str]:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {}


def _save_manifest(manifest: dict[str, str]) -> None:
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


# ── Chunk 분할 ────────────────────────────────────────────────────────────────

def _split_by_headers(text: str, source_path: str, layer: str) -> list[dict[str, str]]:
    """## / ### 헤더 기준으로 chunk를 분할한다.

    Returns: list of {id, text, source, layer, title}
    """
    parts = re.split(r"\n(?=#{1,3} )", text.strip())
    chunks: list[dict[str, str]] = []
    seen_ids: set[str] = set()

    for part in parts:
        part = part.strip()
        if not part:
            continue
        lines = part.split("\n")
        header_line = lines[0] if lines else ""
        title = re.sub(r"^#{1,3} ", "", header_line).strip()
        body = "\n".join(lines[1:]).strip()

        # 너무 짧은 chunk 스킵 (50자 미만)
        full_text = f"{title}\n{body}" if body else title
        if len(full_text) < 50:
            continue

        chunk_id = _sha256(f"{source_path}::{full_text}")
        # 동일 파일 내 중복 청크 ID 방지
        base_id = chunk_id
        suffix = 0
        while chunk_id in seen_ids:
            suffix += 1
            chunk_id = f"{base_id}_{suffix}"
        seen_ids.add(chunk_id)

        chunks.append({
            "id": chunk_id,
            "text": full_text,
            "source": source_path,
            "layer": layer,
            "title": title,
        })

    return chunks


# ── 레이어 분류 ───────────────────────────────────────────────────────────────

def _layer_of(source_dir_name: str) -> str:
    return {"playbooks": "L1", "past_videos": "L2", "external": "L3"}.get(source_dir_name, "L1")


# ── 인덱싱 로직 ───────────────────────────────────────────────────────────────

def ingest_directory(source_subdir: str, collection: Any, manifest: dict[str, str]) -> int:
    """rag/sources/<source_subdir>/ 의 모든 .md 파일을 인덱싱한다.

    Returns: upserted chunk count
    """
    src_dir = SOURCES_DIR / source_subdir
    if not src_dir.exists():
        _log(f"{src_dir} 없음, 스킵", "warning")
        return 0

    layer = _layer_of(source_subdir)
    upserted = 0
    md_files = sorted(src_dir.glob("**/*.md"))

    _log(f"[{layer}] {source_subdir}/ 에서 {len(md_files)}개 파일 스캔 중…")

    for md_path in md_files:
        try:
            text = md_path.read_text(encoding="utf-8")
        except Exception as exc:
            _log(f"읽기 실패: {md_path.name} — {exc}", "warning")
            continue

        file_hash = _sha256(text)
        manifest_key = str(md_path.resolve())

        # 파일 전체 해시 변경 없으면 스킵
        if manifest.get(manifest_key) == file_hash:
            _log(f"  스킵 (unchanged): {md_path.name}")
            continue

        chunks = _split_by_headers(text, str(md_path.name), layer)
        if not chunks:
            _log(f"  chunk 없음: {md_path.name}", "warning")
            manifest[manifest_key] = file_hash
            continue

        # 임베딩 배치 처리
        texts = [c["text"] for c in chunks]
        try:
            embeddings = _embed_batch(texts)
        except Exception as exc:
            _log(f"  임베딩 실패: {md_path.name} — {exc}", "error")
            continue

        collection.upsert(
            ids=[c["id"] for c in chunks],
            documents=texts,
            embeddings=embeddings,
            metadatas=[
                {"source": c["source"], "layer": c["layer"], "title": c["title"]}
                for c in chunks
            ],
        )
        upserted += len(chunks)
        manifest[manifest_key] = file_hash
        _log(f"  upserted {len(chunks)}개 chunks: {md_path.name}", "success")

    return upserted


def ingest_past_videos(collection: Any, manifest: dict[str, str]) -> int:
    """work/iterations/v*/script.md 를 순회하여 judge 점수 ≥ 4.5 섹션만 추출 후 인덱싱한다.

    critique.json 이 없는 iteration 은 스킵 (재채점 비용 방지).
    """
    iter_base = WORK_DIR / "iterations"
    if not iter_base.exists():
        _log("work/iterations/ 없음, L2 스킵", "warning")
        return 0

    past_dir = SOURCES_DIR / "past_videos"
    past_dir.mkdir(parents=True, exist_ok=True)
    upserted = 0

    for iter_dir in sorted(iter_base.iterdir()):
        if not iter_dir.is_dir():
            continue
        script_path = iter_dir / "script.md"
        critique_path = iter_dir / "critique.json"

        # critique.json 없으면 스킵
        if not script_path.exists() or not critique_path.exists():
            continue

        try:
            critique = json.loads(critique_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        sections_critique: list[dict] = critique.get("sections", [])
        high_score_ids: set[int] = {
            s["id"]
            for s in sections_critique
            if sum(s.get("scores", {}).values()) / max(len(s.get("scores", {})), 1) >= JUDGE_SCORE_THRESHOLD
        }

        if not high_score_ids:
            continue

        script_text = script_path.read_text(encoding="utf-8")
        # 섹션 파싱
        raw_parts = re.split(r"\n(?=#{2,3} )", script_text.strip())
        idx = 1
        for part in raw_parts:
            part = part.strip()
            if not re.match(r"^#{2,3} ", part):
                continue
            if idx not in high_score_ids:
                idx += 1
                continue

            title = re.sub(r"^#{2,3} ", "", part.split("\n")[0]).strip()
            out_name = f"{iter_dir.name}_sec{idx:02d}_{_sha256(part)}.md"
            out_path = past_dir / out_name

            # 파일 저장 (없을 때만)
            if not out_path.exists():
                out_path.write_text(f"## {title}\n\n{part}", encoding="utf-8")

            # 인덱싱
            full_text = f"{title}\n{part}"
            file_hash = _sha256(full_text)
            manifest_key = str(out_path.resolve())

            if manifest.get(manifest_key) != file_hash:
                try:
                    emb = _embed_one(full_text)
                except Exception as exc:
                    _log(f"  L2 임베딩 실패: {out_name} — {exc}", "error")
                    idx += 1
                    continue
                chunk_id = _sha256(f"L2::{out_name}::{full_text}")
                collection.upsert(
                    ids=[chunk_id],
                    documents=[full_text],
                    embeddings=[emb],
                    metadatas=[{"source": out_name, "layer": "L2", "title": title}],
                )
                manifest[manifest_key] = file_hash
                upserted += 1
                _log(f"  L2 upserted: {out_name}", "success")

            idx += 1

    return upserted


# ── 공개 진입점 ───────────────────────────────────────────────────────────────

def run_ingest(l1_only: bool = False, l2_only: bool = False) -> dict[str, int]:
    """전체 인덱싱 실행.

    Returns: {"L1": n, "L2": n, "L3": n, "total": n}
    """
    collection = _get_collection()
    manifest = _load_manifest()
    counts: dict[str, int] = {"L1": 0, "L2": 0, "L3": 0}

    if not l2_only:
        counts["L1"] += ingest_directory("playbooks", collection, manifest)
        counts["L3"] += ingest_directory("external", collection, manifest)

    if not l1_only:
        counts["L2"] += ingest_past_videos(collection, manifest)

    _save_manifest(manifest)
    counts["total"] = sum(counts.values())

    total_in_db = collection.count()
    _log(
        f"인덱싱 완료 — L1={counts['L1']}, L2={counts['L2']}, L3={counts['L3']} "
        f"upserted / DB 총 {total_in_db}개 chunks",
        "success",
    )
    return counts


def main() -> None:
    p = argparse.ArgumentParser(description="RAG R1 인덱싱")
    p.add_argument("--l1-only", action="store_true", help="L1(플레이북) 만 인덱싱")
    p.add_argument("--l2-only", action="store_true", help="L2(고득점 섹션) 만 인덱싱")
    args = p.parse_args()

    result = run_ingest(l1_only=args.l1_only, l2_only=args.l2_only)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
