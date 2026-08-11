"""Content Adapter — Raw Input → RAG Retrieval → Learning Brief + Scene Plan.

Rule-based MVP (LLM 호출 없음).
입력: Markdown 보고서 (inputs/report.md 또는 임의 .md 파일)
출력: work/content_adapter/learning_brief.json
       work/content_adapter/scene_plan.json

파이프라인:
  Raw Input → Query Builder → BM25 RAG Retrieval → Learning Brief → Scene Plan

이운규식 7단 구조:
  Scene 1  WHY (Hook)
  Scene 2  사례 (Example)
  Scene 3  깨달음 (Insight)
  Scene 4  개념 (Concept)
  Scene 5  적용 (Application)
  Scene 6  정리 (Summary)

사용:
  python pipelines/content_adapter.py --input inputs/report.md --topic "AI 파이프라인"
  python pipelines/content_adapter.py --input docs/reports/TASK-*.md --topic "자막 오너 단일화"
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

try:
    from rich.console import Console
    _console = Console(stderr=True)

    def _log(msg: str, level: str = "info") -> None:
        color = {"info": "green", "warning": "yellow", "error": "red", "success": "cyan"}.get(level, "white")
        _console.print(f"[{color}][content_adapter][/{color}] {msg}")
except ImportError:
    logging.basicConfig(level=logging.INFO)

    def _log(msg: str, level: str = "info") -> None:  # type: ignore[misc]
        getattr(logging, level, logging.info)(f"[content_adapter] {msg}")


ROOT = Path(os.environ.get("PROJECT_ROOT", Path(__file__).parent.parent))
WORK_DIR = Path(os.getenv("WORK_DIR", str(ROOT / "work")))
OUTPUT_DIR = WORK_DIR / "content_adapter"

_MAX_KEY_POINTS: int = int(os.getenv("CONTENT_ADAPTER_MAX_KEY_POINTS", "20"))
_MAX_CONCEPTS: int   = int(os.getenv("CONTENT_ADAPTER_MAX_CONCEPTS",   "20"))

# 이운규식 7단 매핑
_SCENE_STRUCTURE = [
    {"purpose": "hook",    "narration_hint": "질문형으로 시작, 시청자 공감 유발"},
    {"purpose": "example", "narration_hint": "구체 사례 설명, 숫자/Before-After 강조"},
    {"purpose": "insight", "narration_hint": "깨달음 전달, 짧고 강렬하게"},
    {"purpose": "concept", "narration_hint": "개념 정의, 천천히 명확하게"},
    {"purpose": "apply",   "narration_hint": "실행 기준 제시, 시청자 행동 유발"},
    {"purpose": "summary", "narration_hint": "핵심 3가지 정리, 마무리 톤"},
]

_VISUAL_TYPE_BY_PURPOSE = {
    "hook":    "single_text",
    "example": "compare_two",
    "insight": "single_text",
    "concept": "bullet_list",
    "apply":   "bullet_list",
    "summary": "bullet_list",
}

_DURATION_WEIGHT_BY_PURPOSE = {
    "hook":    2,
    "example": 3,
    "insight": 2,
    "concept": 3,
    "apply":   2,
    "summary": 1,
}

# 메트릭 정규식: "16.1% 단축", "3배 빠름", "120~230원"
_METRIC_RE = re.compile(
    r"(?:"
    r"\d+(?:\.\d+)?%[^\s,]*"           # 16.1%
    r"|[\d,]+(?:\.\d+)?(?:배|초|분|원|개|회|ms|KB|MB|GB)"  # 3배, 120원
    r"|[\d,]+~[\d,]+[^\s,]{0,6}"        # 120~230원
    r")"
)

# WHY Hook 패턴: 제목/헤더에서 찾기
_WHY_KEYWORDS = ["왜", "문제", "실패", "반복", "오류", "고장", "이유", "원인", "해결"]


def _detect_input_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in (".md", ".markdown"):
        return "markdown_report"
    if suffix == ".pdf":
        return "pdf_paper"
    if suffix in (".txt",):
        return "plain_text"
    return "unknown"


def _parse_headers(text: str) -> list[dict[str, Any]]:
    """## / ### 헤더 단위로 섹션 분할."""
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for line in text.splitlines():
        m = re.match(r"^(#{1,4})\s+(.+)$", line)
        if m:
            if current:
                sections.append(current)
            level = len(m.group(1))
            current = {"level": level, "title": m.group(2).strip(), "lines": []}
        elif current is not None:
            current["lines"].append(line)

    if current:
        sections.append(current)
    return sections


def _extract_bullets(text: str) -> list[str]:
    """- / * 불릿 포인트 추출."""
    bullets = []
    for line in text.splitlines():
        m = re.match(r"^\s*[-*]\s+(.+)$", line)
        if m:
            content = m.group(1).strip()
            if len(content) > 5:  # 너무 짧은 항목 제외
                bullets.append(content)
    return bullets


def _extract_metrics(text: str) -> list[dict[str, str]]:
    """숫자+단위 메트릭 추출. 원문 섹션 정보 포함."""
    metrics = []
    seen: set[str] = set()
    for line in text.splitlines():
        for match in _METRIC_RE.finditer(line):
            val = match.group(0)
            if val not in seen:
                seen.add(val)
                # 해당 줄 전체를 컨텍스트로 사용
                ctx = line.strip()
                if len(ctx) > 100:
                    ctx = ctx[:100] + "..."
                metrics.append({"type": "metric", "text": ctx, "source_section": "auto"})
    return metrics


def _extract_comparisons(text: str) -> list[dict[str, str]]:
    """Before/After 패턴 추출."""
    comparisons = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if re.search(r"before|after|기존|변경|이전|이후", line, re.IGNORECASE):
            ctx = " / ".join(l.strip() for l in lines[max(0,i-1):i+3] if l.strip())
            if ctx:
                comparisons.append({"type": "comparison", "text": ctx[:120], "source_section": "auto"})
            if len(comparisons) >= 3:
                break
    return comparisons


def _build_why_hook(topic: str, sections: list[dict[str, Any]], bullets: list[str]) -> tuple[str, str]:
    """WHY Hook 및 core_question 생성 — topic(main_topic) 기준 고정.

    section title은 주제를 교체하지 않고 context 보강으로만 사용한다.
    """
    # topic 자체가 WHY/질문 패턴이면 그대로 활용 (가장 흔한 케이스)
    is_question_topic = "?" in topic or any(kw in topic for kw in _WHY_KEYWORDS)
    if is_question_topic:
        why_hook = topic if topic.endswith("?") else f"{topic}?"
        core_q = f"{topic}에 대한 핵심 원인과 해결 방향은 무엇인가?"
        return why_hook, core_q

    # 섹션에서 WHY 키워드 발견 시 — topic 교체 금지, context 보강만
    for sec in sections:
        for kw in _WHY_KEYWORDS:
            if kw in sec["title"]:
                why_hook = f"왜 {topic}인가? ({sec['title']} 사례 포함)"
                core_q = f"{topic}: 핵심 원리와 실제 사례"
                return why_hook, core_q

    # 불릿에서 문제 찾기 — topic 포장 유지
    for bullet in bullets[:5]:
        for kw in ["문제", "실패", "오류", "안됨", "발생"]:
            if kw in bullet:
                short = bullet[:30]
                why_hook = f"왜 {topic}을 이해해야 할까요? ({short} 사례)"
                core_q = f"{topic}에서 {short}의 원인은 무엇인가?"
                return why_hook, core_q

    # 기본 패턴
    why_hook = f"왜 {topic}을 이해해야 할까요?"
    core_q = f"{topic}의 핵심 원리는 무엇인가?"
    return why_hook, core_q


def _infer_audience(sections: list[dict[str, Any]], bullets: list[str]) -> str:
    """대상 청중 추정."""
    text = " ".join(s["title"] for s in sections) + " ".join(bullets[:10])
    if any(kw in text for kw in ["파이프라인", "자동화", "LLM", "AI", "Python"]):
        return "AI 자동화 시스템을 만드는 개발자"
    if any(kw in text for kw in ["마케팅", "광고", "SNS", "콘텐츠"]):
        return "디지털 마케터"
    if any(kw in text for kw in ["스타트업", "창업", "사업", "비즈니스"]):
        return "스타트업 창업자 또는 기획자"
    return "IT 분야 학습자"


def _map_section_to_purpose(sections: list[dict[str, Any]]) -> dict[str, str]:
    """섹션 제목을 이운규식 7단 목적에 매핑."""
    mapping: dict[str, str] = {}
    purpose_keywords = {
        "hook":    ["개요", "배경", "문제", "왜", "현황", "목표"],
        "example": ["사례", "예시", "실제", "테스트", "결과", "비교"],
        "insight": ["분석", "원인", "이유", "인사이트", "발견", "깨달"],
        "concept": ["개념", "정의", "구조", "아키텍처", "원리", "방법"],
        "apply":   ["적용", "구현", "수정", "변경", "해결", "방안"],
        "summary": ["정리", "요약", "결론", "다음", "향후", "마무리"],
    }

    for sec in sections:
        title_lower = sec["title"].lower()
        for purpose, keywords in purpose_keywords.items():
            if any(kw in sec["title"] for kw in keywords):
                mapping[purpose] = sec["title"]
                break

    return mapping


def build_queries(
    topic: str,
    sections: list[dict[str, Any]],
    bullets: list[str],
) -> list[str]:
    """Query Builder — 검색 쿼리 생성.

    topic과 주요 섹션·불릿에서 BM25 검색에 활용할 쿼리를 생성한다.
    """
    queries: list[str] = [topic]

    # WHY 키워드 변형 추가 (이미 포함된 경우 중복 생성 방지)
    for kw in _WHY_KEYWORDS:
        if kw in topic and not topic.startswith(kw):
            queries.append(f"{kw} {topic}")
            break

    # 섹션 제목에서 핵심 토큰 추출
    for sec in sections[:4]:
        title = sec["title"].strip()
        if title and title != topic and len(title) > 3:
            queries.append(title)

    # 불릿 상위 3개를 쿼리로 활용
    for b in bullets[:3]:
        short = b[:40].strip()
        if short and short not in queries:
            queries.append(short)

    _log(f"[RAG_QUERY] query_count={len(queries)}")
    for i, q in enumerate(queries, 1):
        _log(f"  [{i}] {q}")

    return queries


def retrieve_rag_context(queries: list[str], k: int = 5) -> list[dict[str, Any]]:
    """RAG Retrieval — BM25 기반 top-K 검색.

    rag_retriever 모듈을 사용하며, 실패 시 빈 리스트를 반환한다.
    """
    try:
        import sys as _sys
        _pipelines_dir = str(Path(__file__).parent)
        if _pipelines_dir not in _sys.path:
            _sys.path.insert(0, _pipelines_dir)
        from rag_retriever import search as _bm25_search, invalidate_cache

        invalidate_cache()  # 최신 파일 반영
        results = _bm25_search(queries, k=k)
    except Exception as exc:
        _log(f"RAG Retrieval 실패 — 건너뜀: {exc}", "warning")
        return []

    sources = list({r["source"] for r in results})
    _log(
        f"[RAG_RETRIEVE] query_count={len(queries)} retrieved={len(results)}"
    )
    _log(f"  sources: {sources}")

    return results


def _critique_learning_brief(brief: dict[str, Any]) -> dict[str, Any]:
    """Strategy C placeholder — MVP rule-based; LLM 버전에서 확장."""
    if not brief.get("why_hook"):
        brief["why_hook"] = f"왜 {brief['topic']}이 중요할까요?"
    if len(brief.get("key_points", [])) < 3:
        _log("key_points가 3개 미만 — 불릿 추가 보완 필요", "warning")
    return brief


def strategy_c_critique(brief: dict[str, Any]) -> dict[str, Any]:
    """Strategy C — Content Adapter Critique.

    Learning Brief 품질을 검사하고 PASS/REGENERATE를 반환한다.

    검사 항목:
      1. WHY Hook 충분한가
      2. Topic Drift 없는가
      3. Evidence 부족한가
      4. 사례 다양성 부족한가
    """
    topic = brief.get("main_topic") or brief.get("topic", "")
    issues: list[str] = []

    # 1. WHY Hook 검사
    why_hook = brief.get("why_hook", "")
    if not why_hook or len(why_hook) < 5:
        issues.append("WHY Hook 없음")
    elif not any(kw in why_hook for kw in _WHY_KEYWORDS + ["?", "왜", "어떻게"]):
        issues.append(f"WHY Hook 약함: {why_hook!r}")

    # 2. Topic Drift 검사
    topic_tokens = {t for t in re.split(r"[\s?!,.]", topic) if len(t) > 1}
    core_q = brief.get("core_question", "")
    if topic_tokens and not any(t in core_q for t in topic_tokens):
        issues.append(f"core_question에 topic 토큰 없음: {core_q!r}")

    # 3. Evidence 검사
    evidence = brief.get("evidence", [])
    if len(evidence) == 0:
        issues.append("Evidence 없음")

    # 4. 사례 다양성 검사
    key_points = brief.get("key_points", [])
    if len(key_points) < 2:
        issues.append(f"key_points 부족: {len(key_points)}개")

    status = "PASS" if not issues else "REGENERATE"
    _log(f"[STRATEGY_C] {status}")
    for issue in issues:
        _log(f"  ↳ {issue}", "warning")

    return {
        "audit": "STRATEGY_C",
        "status": status,
        "issue_count": len(issues),
        "issues": issues,
    }


def rag_audit(brief: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    """RAG_AUDIT — retrieved_contexts와 rag_sources 존재 여부 검사.

    PASS 조건:
      retrieved_contexts > 0 OR 소스 문서가 아직 없는 경우 (초기 실행)
      rag_sources > 0 OR 소스 문서가 아직 없는 경우
    """
    retrieved = brief.get("retrieved_contexts", [])
    sources = plan.get("rag_sources", [])
    issues: list[str] = []

    if not retrieved:
        issues.append("retrieved_contexts == 0 (소스 없거나 검색 미매칭)")

    if not sources:
        issues.append("rag_sources == 0")

    status = "PASS" if not issues else "WARN"
    _log(f"[RAG_AUDIT] {status} (retrieved={len(retrieved)}, rag_sources={len(sources)})")
    for issue in issues:
        _log(f"  ↳ {issue}", "warning")

    return {
        "audit": "RAG_AUDIT",
        "status": status,
        "retrieved_count": len(retrieved),
        "source_count": len(sources),
        "issues": issues,
    }


def build_learning_brief(
    input_path: Path,
    topic: str,
    text: str,
    sections: list[dict[str, Any]],
    retrieved_contexts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    all_text = text
    bullets = _extract_bullets(all_text)
    metrics = _extract_metrics(all_text)
    comparisons = _extract_comparisons(all_text)
    why_hook, core_q = _build_why_hook(topic, sections, bullets)
    audience = _infer_audience(sections, bullets)
    section_map = _map_section_to_purpose(sections)

    # key_points: 불릿 중 의미 있는 것 (상한: CONTENT_ADAPTER_MAX_KEY_POINTS)
    key_points_all = [b for b in bullets if len(b) > 10]
    if len(key_points_all) > _MAX_KEY_POINTS:
        _log(f"[TRUNCATION-WARNING] key_points {len(key_points_all)}개 → {_MAX_KEY_POINTS}개로 절단 (CONTENT_ADAPTER_MAX_KEY_POINTS={_MAX_KEY_POINTS})", "warning")
    key_points = key_points_all[:_MAX_KEY_POINTS]
    if not key_points and sections:
        sections_all = [s["title"] for s in sections]
        if len(sections_all) > _MAX_KEY_POINTS:
            _log(f"[TRUNCATION-WARNING] key_points(fallback) {len(sections_all)}개 → {_MAX_KEY_POINTS}개로 절단", "warning")
        key_points = sections_all[:_MAX_KEY_POINTS]

    # concepts: 대문자/영어+한국어 혼합 용어 (상한: CONTENT_ADAPTER_MAX_CONCEPTS)
    concepts: list[dict[str, str]] = []
    concept_re = re.compile(r"\b([A-Z][A-Za-z]+(?:\s[A-Z][a-z]+)*|[A-Z]{2,})\b")
    seen_concepts: set[str] = set()
    for line in all_text.splitlines():
        for m in concept_re.finditer(line):
            name = m.group(0)
            if name not in seen_concepts and len(name) > 2:
                seen_concepts.add(name)
                ctx = line.strip()[:30]
                concepts.append({"name": name, "definition": ctx})
            if len(concepts) >= _MAX_CONCEPTS:
                break
        if len(concepts) >= _MAX_CONCEPTS:
            break
    if len(concepts) >= _MAX_CONCEPTS:
        _log(f"[TRUNCATION-WARNING] concepts 상한 {_MAX_CONCEPTS}개 도달 — 추가 개념 수집 중단 (CONTENT_ADAPTER_MAX_CONCEPTS={_MAX_CONCEPTS})", "warning")

    # evidence 합치기
    evidence: list[dict[str, str]] = []
    evidence.extend(metrics[:4])
    evidence.extend(comparisons[:2])

    # do_not_distort
    do_not_distort = [
        "원본 문서에 없는 수치 생성 금지",
        "확인되지 않은 성공 주장 금지",
        "원문 사례를 일반화하여 과장 금지",
    ]

    brief: dict[str, Any] = {
        "$schema": "content_adapter/learning_brief_v1",
        "main_topic": topic,
        "topic": topic,
        "input_type": _detect_input_type(input_path),
        "input_source": str(input_path),
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "target_audience": audience,
        "core_question": core_q,
        "why_hook": why_hook,
        "key_points": key_points,
        "evidence": evidence,
        "examples": [
            {
                "name": ex["text"][:40] if len(ex["text"]) > 40 else ex["text"],
                "before": None,
                "after": None,
                "lesson": "원문 사례 참조",
            }
            for ex in comparisons[:2]
        ],
        "concepts": concepts,
        "do_not_distort": do_not_distort,
        "section_map": section_map,
        "retrieved_contexts": retrieved_contexts or [],
    }

    return _critique_learning_brief(brief)


def build_scene_plan(
    brief: dict[str, Any],
    target_duration: int = 90,
    rag_sources: list[str] | None = None,
) -> dict[str, Any]:
    """Learning Brief → 이운규식 6단 Scene Plan.

    main_topic은 모든 scene 제목의 기준. evidence는 message/visual_hint에만 사용.
    """
    key_points = brief.get("key_points", [])
    evidence = brief.get("evidence", [])
    examples = brief.get("examples", [])
    section_map = brief.get("section_map", {})
    main_topic = brief.get("main_topic") or brief.get("topic", "")
    topic = main_topic  # alias for backward compat
    why_hook = brief.get("why_hook", "")
    core_q = brief.get("core_question", "")

    scene_count = 6  # 이운규식 6단 기본

    def _title(s: str, max_len: int = 20) -> str:
        return s[:max_len] if len(s) > max_len else s

    scenes: list[dict[str, Any]] = []

    for idx, template in enumerate(_SCENE_STRUCTURE):
        purpose = template["purpose"]
        narration_hint = template["narration_hint"]
        visual_type = _VISUAL_TYPE_BY_PURPOSE[purpose]
        duration_weight = _DURATION_WEIGHT_BY_PURPOSE[purpose]
        evidence_refs: list[int] = []

        if purpose == "hook":
            # topic이 이미 "왜"로 시작하면 그대로 사용
            hook_title = topic if topic.startswith("왜") else f"왜 {topic}인가?"
            title = _title(hook_title)
            message = why_hook
            visual_hint = f"핵심 질문 텍스트: {core_q[:40]}"

        elif purpose == "example":
            # scene 제목은 반드시 main_topic 기반 (evidence 텍스트로 교체 금지)
            title = _title(f"{main_topic} — 실제 사례")
            if evidence:
                ev = evidence[0]
                message = ev["text"][:60]
                evidence_refs = [0]
                if examples:
                    visual_type = "compare_two"
                    visual_hint = f"Before: 문제 상황 / After: 해결 결과"
                else:
                    visual_type = "metric_highlight"
                    visual_hint = f"수치 강조: {ev['text'][:40]}"
            else:
                message = key_points[0] if key_points else f"{main_topic}의 실제 사례"
                visual_hint = "Before/After 비교"

        elif purpose == "insight":
            insight = key_points[1] if len(key_points) > 1 else (key_points[0] if key_points else "핵심 깨달음")
            title = _title(f"{main_topic} 핵심 인사이트")
            message = insight[:60]
            visual_hint = f"강조 텍스트: {insight[:40]}"

        elif purpose == "concept":
            concept_points = key_points[2:5] if len(key_points) >= 3 else key_points
            title = _title(f"{main_topic} 개념 정리")
            message = concept_points[0][:60] if concept_points else f"{main_topic} 핵심 원리"
            visual_type = "bullet_list"
            visual_hint = "\n".join(f"• {p[:35]}" for p in concept_points[:3])
            if len(evidence) > 1:
                evidence_refs = list(range(min(2, len(evidence))))

        elif purpose == "apply":
            apply_points = key_points[3:6] if len(key_points) >= 4 else key_points[-2:]
            title = _title(f"{main_topic} 적용 기준")
            message = apply_points[0][:60] if apply_points else f"{main_topic} 적용 방법"
            visual_type = "bullet_list"
            visual_hint = "\n".join(f"• {p[:35]}" for p in apply_points[:3])

        elif purpose == "summary":
            title = _title(f"{main_topic} 핵심 정리")
            message = f"{why_hook} — 답: {key_points[0][:40] if key_points else '원칙을 지켜라'}"
            visual_type = "bullet_list"
            visual_hint = "\n".join(f"• {p[:35]}" for p in key_points[:3])

        else:
            title = _title(topic)
            message = topic
            visual_hint = ""

        # 원문 섹션명 참조
        source_section = section_map.get(purpose, "")

        scene: dict[str, Any] = {
            "scene_id": idx + 1,
            "purpose": purpose,
            "title": title,
            "message": message,
            "visual_type": visual_type,
            "visual_hint": visual_hint,
            "narration_hint": narration_hint,
            "evidence_refs": evidence_refs,
            "duration_weight": duration_weight,
            "source_section": source_section,
        }
        scenes.append(scene)

    return {
        "$schema": "content_adapter/scene_plan_v1",
        "main_topic": main_topic,
        "topic": topic,
        "target_duration": target_duration,
        "scene_count": scene_count,
        "structure": "이운규식_7단",
        "scenes": scenes,
        "rag_sources": rag_sources or [],
    }


def audit_topic_drift(
    main_topic: str,
    brief: dict[str, Any],
    plan: dict[str, Any],
) -> dict[str, Any]:
    """TOPIC_AUDIT: main_topic이 brief/plan 전반에 유지되는지 검사.

    PASS: issue_count == 0
    FAIL: issue_count > 0
    """
    issues: list[str] = []

    # 1. main_topic 필드 일치
    if brief.get("main_topic") != main_topic:
        issues.append(f"learning_brief.main_topic mismatch: {brief.get('main_topic')!r}")
    if plan.get("main_topic") != main_topic:
        issues.append(f"scene_plan.main_topic mismatch: {plan.get('main_topic')!r}")

    # 2. core_question이 main_topic 토큰을 포함하는지
    topic_tokens = {t for t in re.split(r"[\s?!,.]", main_topic) if len(t) > 1}
    core_q = brief.get("core_question", "")
    if topic_tokens and not any(t in core_q for t in topic_tokens):
        issues.append(f"core_question에 main_topic 토큰 없음: {core_q!r}")

    # 3. non-example scene 제목에 main_topic 토큰이 있는지
    for scene in plan.get("scenes", []):
        if scene.get("purpose") == "example":
            continue  # example은 사례 중심이므로 완화
        title = scene.get("title", "")
        combined = title + " " + scene.get("message", "")
        if topic_tokens and not any(t in combined for t in topic_tokens if len(t) > 2):
            issues.append(
                f"Scene {scene['scene_id']} ({scene['purpose']}): "
                f"main_topic 토큰 없음 — title={title!r}"
            )

    return {
        "audit": "TOPIC_AUDIT",
        "main_topic": main_topic,
        "status": "PASS" if not issues else "FAIL",
        "issue_count": len(issues),
        "issues": issues,
    }


def run(input_path: Path, topic: str, target_duration: int = 90) -> tuple[Path, Path]:
    if not input_path.exists():
        _log(f"입력 파일 없음: {input_path}", "error")
        sys.exit(1)

    _log(f"입력 로드: {input_path}")
    text = input_path.read_text(encoding="utf-8")
    _log(f"  {len(text):,}자")

    sections = _parse_headers(text)
    _log(f"  섹션 수: {len(sections)}")

    # ── RAG: Query Builder → Retrieval ───────────────────────────────────────
    bullets_for_query = _extract_bullets(text)
    queries = build_queries(topic, sections, bullets_for_query)
    retrieved_contexts = retrieve_rag_context(queries, k=5)
    rag_sources = list({r["source"] for r in retrieved_contexts})

    # ── Learning Brief + Scene Plan ──────────────────────────────────────────
    brief = build_learning_brief(input_path, topic, text, sections, retrieved_contexts)
    plan = build_scene_plan(brief, target_duration, rag_sources)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    brief_path = OUTPUT_DIR / "learning_brief.json"
    plan_path = OUTPUT_DIR / "scene_plan.json"

    topic_audit = audit_topic_drift(topic, brief, plan)
    plan["topic_audit"] = topic_audit

    # ── Strategy C Critique ──────────────────────────────────────────────────
    strategy_c = strategy_c_critique(brief)
    plan["strategy_c"] = strategy_c

    # ── RAG Audit ────────────────────────────────────────────────────────────
    r_audit = rag_audit(brief, plan)
    plan["rag_audit"] = r_audit

    brief_path.write_text(json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8")
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    _log(f"learning_brief.json → {brief_path}", "success")
    _log(f"scene_plan.json    → {plan_path}", "success")
    _log(f"scenes: {plan['scene_count']} / target_duration: {plan['target_duration']}s", "success")

    t_level = "success" if topic_audit["status"] == "PASS" else "warning"
    _log(f"TOPIC_AUDIT: {topic_audit['status']} (issues={topic_audit['issue_count']})", t_level)
    for issue in topic_audit["issues"]:
        _log(f"  ↳ {issue}", "warning")

    s_level = "success" if strategy_c["status"] == "PASS" else "warning"
    _log(f"STRATEGY_C: {strategy_c['status']}", s_level)

    r_level = "success" if r_audit["status"] == "PASS" else "warning"
    _log(f"RAG_AUDIT: {r_audit['status']}", r_level)

    return brief_path, plan_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Content Adapter — Markdown → Learning Brief + Scene Plan")
    parser.add_argument("--input", required=True, help="입력 Markdown 파일 경로")
    parser.add_argument("--topic", required=True, help="영상 주제 (짧은 명사형)")
    parser.add_argument("--duration", type=int, default=90, help="목표 영상 길이 (초, 기본 90)")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = ROOT / input_path

    run(input_path, args.topic, args.duration)


if __name__ == "__main__":
    main()
